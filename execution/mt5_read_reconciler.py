from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Callable, Iterable

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.real_reconciliation import (
    ExternalIdentityKind,
    RealReconciliationEvidenceBoundary,
    RealReconciliationObservation,
    ReconciliationOutcome,
)


@dataclass(frozen=True)
class MT5ReconciliationIdentity:
    request_id: str
    symbol: str
    side: str
    amount: float
    correlation: str
    magic: int


@dataclass(frozen=True)
class MT5HistoryCandidate:
    ticket: str
    kind: ExternalIdentityKind
    symbol: str
    side: str
    amount: float
    correlation: str
    magic: int
    provider: str
    account_id: str
    observed_at: datetime
    order_ticket: str | None = None
    position_id: str | None = None


class MT5ReadOnlyReconciler:
    """Read-only MT5 resolver. It never calls order_send/order_check.

    The query functions are injected so the reconciliation policy can be tested
    without requiring a live terminal. A production transport must provide
    bounded history queries; this class intentionally never performs an
    unbounded scan.
    """

    source = "mt5-read-only-reconciler"

    def __init__(
        self,
        *,
        adapter: ICMarketsMT5DemoAdapter,
        account_id: str,
        provider: str = "ic-markets-mt5",
        deals_query: Callable[..., Iterable[Any] | None],
        orders_query: Callable[..., Iterable[Any] | None],
        context_provider: Callable[[str], dict[str, object] | None] | None = None,
        lookback_seconds: int = 86400,
        lookahead_seconds: int = 300,
    ) -> None:
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("account_id obrigatório")
        if not callable(deals_query) or not callable(orders_query):
            raise ValueError("consultas de histórico obrigatórias")
        self._adapter = adapter
        self._account_id = account_id.strip()
        self._provider = provider.strip().lower()
        self._deals_query = deals_query
        self._orders_query = orders_query
        if not isinstance(lookback_seconds, int) or isinstance(lookback_seconds, bool) or lookback_seconds <= 0:
            raise ValueError("lookback_seconds inválido")
        if not isinstance(lookahead_seconds, int) or isinstance(lookahead_seconds, bool) or lookahead_seconds < 0:
            raise ValueError("lookahead_seconds inválido")
        self._context_provider = context_provider
        self._lookback = timedelta(seconds=lookback_seconds)
        self._lookahead = timedelta(seconds=lookahead_seconds)
        self._evidence = RealReconciliationEvidenceBoundary._internal()

    def lookup(self, request_id: str) -> RealReconciliationObservation:
        if not isinstance(request_id, str) or not request_id.strip():
            return self._evidence.issue(
                request_id=request_id,
                executed=False,
                external_id=None,
                observed_at=datetime.now(timezone.utc),
                source=self.source,
                provider=self._provider,
                account_id=self._account_id,
                outcome=ReconciliationOutcome.QUERY_FAILED,
                provider_capability=self._evidence.provider_capability,
            )
        if self._context_provider is None:
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        try:
            context = self._context_provider(request_id.strip())
        except Exception:
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        if not isinstance(context, dict):
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        try:
            persisted_request_id = context.get("request_id")
            if persisted_request_id != request_id.strip():
                return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
            recovery = context.get("recovery_identity")
            if not isinstance(recovery, dict):
                return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
            identity = MT5ReconciliationIdentity(
                request_id=request_id.strip(),
                symbol=str(recovery["symbol"]).strip(),
                side=str(recovery["side"]).upper().replace("COMPRA", "BUY").replace("VENDA", "SELL"),
                amount=float(recovery["amount"]),
                correlation=str(recovery["correlation"]).strip(),
                magic=int(recovery["magic"]),
            )
        except (KeyError, TypeError, ValueError):
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        if identity.request_id != request_id.strip():
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        reserved_raw = context.get("reserved_at")
        try:
            reserved_at = datetime.fromisoformat(str(reserved_raw))
        except (TypeError, ValueError):
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        if reserved_at.tzinfo is None or reserved_at.utcoffset() is None:
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        return self.resolve(identity, reserved_at=reserved_at)

    def resolve(self, identity: MT5ReconciliationIdentity, *, reserved_at: datetime | None = None) -> RealReconciliationObservation:
        """Resolve an already-persisted identity; never dispatches."""
        if not self._valid_identity(identity):
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        candidates: list[MT5HistoryCandidate] = []
        if reserved_at is None or reserved_at.tzinfo is None or reserved_at.utcoffset() is None:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)
        date_from = reserved_at - self._lookback
        date_to = datetime.now(timezone.utc) + self._lookahead
        if date_to <= date_from:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)
        try:
            deals = self._deals_query(
                date_from=date_from,
                date_to=date_to,
                symbol=identity.symbol,
                correlation=identity.correlation,
                magic=identity.magic,
                account_id=self._account_id,
            )
            orders = self._orders_query(
                date_from=date_from,
                date_to=date_to,
                symbol=identity.symbol,
                correlation=identity.correlation,
                magic=identity.magic,
                account_id=self._account_id,
            )
        except Exception:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        if deals is None or orders is None:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        for raw in list(deals) + list(orders):
            candidate = self._normalize(raw, identity)
            if candidate is None:
                continue
            # Never trust a transport to honor the requested bounded window.
            # An old matching execution must not close a fresh UNKNOWN request.
            if candidate.observed_at < date_from or candidate.observed_at > date_to:
                continue
            candidates.append(candidate)

        # A market request may be filled by multiple deals. Distinct deals
        # are not automatically ambiguous when they all belong to exactly one
        # order: the order ticket is then the aggregate execution identity.
        deals = [c for c in candidates if c.kind is ExternalIdentityKind.DEAL]
        if deals:
            unique = {c.ticket: c for c in deals}
            deals = list(unique.values())
            groups: dict[str, list[MT5HistoryCandidate]] = {}
            ungrouped: list[MT5HistoryCandidate] = []
            for candidate in deals:
                if candidate.order_ticket is None or not str(candidate.order_ticket).strip():
                    ungrouped.append(candidate)
                else:
                    groups.setdefault(str(candidate.order_ticket), []).append(candidate)
            if len(groups) + len(ungrouped) > 1:
                return self._negative(identity.request_id, ReconciliationOutcome.AMBIGUOUS)
            if len(groups) == 1 and not ungrouped:
                group = next(iter(groups.values()))
                total = sum(item.amount for item in group)
                if math.isclose(total, identity.amount, rel_tol=0.0, abs_tol=1e-9):
                    aggregate = group[0]
                    return self._executed(
                        identity,
                        aggregate,
                        external_id=str(aggregate.order_ticket),
                        external_id_kind=ExternalIdentityKind.ORDER,
                    )
                if total < identity.amount:
                    return self._negative(identity.request_id, ReconciliationOutcome.NOT_VISIBLE_YET)
                return self._negative(identity.request_id, ReconciliationOutcome.AMBIGUOUS)
            if len(ungrouped) == 1:
                candidate = ungrouped[0]
                if math.isclose(candidate.amount, identity.amount, rel_tol=0.0, abs_tol=1e-9):
                    return self._executed(identity, candidate)
                if candidate.amount < identity.amount:
                    return self._negative(identity.request_id, ReconciliationOutcome.NOT_VISIBLE_YET)
                return self._negative(identity.request_id, ReconciliationOutcome.AMBIGUOUS)

        orders = [c for c in candidates if c.kind is ExternalIdentityKind.ORDER]
        if len(orders) == 1:
            # An order without a deal is not proof of execution. It is delayed
            # visibility / pending broker state, never EXECUTED.
            return self._negative(identity.request_id, ReconciliationOutcome.NOT_VISIBLE_YET)
        if len(orders) > 1:
            return self._negative(identity.request_id, ReconciliationOutcome.AMBIGUOUS)
        return self._negative(identity.request_id, ReconciliationOutcome.NOT_FOUND)

    @staticmethod
    def _valid_identity(identity: MT5ReconciliationIdentity) -> bool:
        return (
            isinstance(identity, MT5ReconciliationIdentity)
            and bool(identity.request_id.strip())
            and bool(identity.symbol.strip())
            and identity.side in {"BUY", "SELL"}
            and math.isfinite(identity.amount)
            and identity.amount > 0
            and bool(identity.correlation.strip())
            and isinstance(identity.magic, int)
            and not isinstance(identity.magic, bool)
        )

    def _normalize(self, raw: Any, identity: MT5ReconciliationIdentity) -> MT5HistoryCandidate | None:
        kind = getattr(raw, "external_id_kind", None)
        if isinstance(kind, str):
            try:
                kind = ExternalIdentityKind(kind)
            except ValueError:
                return None
        if kind not in {ExternalIdentityKind.DEAL, ExternalIdentityKind.ORDER}:
            return None

        ticket = getattr(raw, "ticket", None)
        symbol = getattr(raw, "symbol", None)
        side = getattr(raw, "side", None)
        amount = getattr(raw, "volume", None)
        correlation = getattr(raw, "comment", None)
        magic = getattr(raw, "magic", None)
        if not isinstance(ticket, (int, str)) or not str(ticket).strip():
            return None
        if not isinstance(symbol, str) or symbol.strip() != identity.symbol:
            return None
        if not isinstance(side, str) or side.upper() != identity.side:
            return None
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(float(amount)):
            return None
        if float(amount) <= 0 or float(amount) > identity.amount + 1e-9:
            return None
        if not isinstance(correlation, str) or correlation.strip() != identity.correlation:
            return None
        if not isinstance(magic, int) or isinstance(magic, bool) or magic != identity.magic:
            return None

        observed_at = getattr(raw, "observed_at", None)
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return None
        raw_account_id = getattr(raw, "account_id", None)
        if raw_account_id is not None and str(raw_account_id).strip() != self._account_id:
            return None
        return MT5HistoryCandidate(
            ticket=str(ticket),
            kind=kind,
            symbol=symbol.strip(),
            side=side.upper(),
            amount=float(amount),
            correlation=correlation.strip(),
            magic=magic,
            provider=self._provider,
            account_id=self._account_id,
            observed_at=observed_at,
            order_ticket=getattr(raw, "order_ticket", None),
            position_id=getattr(raw, "position_id", None),
        )

    def _executed(
        self,
        identity: MT5ReconciliationIdentity,
        candidate: MT5HistoryCandidate,
        *,
        external_id: str | None = None,
        external_id_kind: ExternalIdentityKind = ExternalIdentityKind.DEAL,
    ):
        return self._evidence.issue(
            request_id=identity.request_id,
            executed=True,
            external_id=external_id or candidate.ticket,
            observed_at=candidate.observed_at,
            source=self.source,
            outcome=ReconciliationOutcome.EXECUTED,
            external_id_kind=external_id_kind,
            provider=candidate.provider,
            account_id=candidate.account_id,
            symbol=candidate.symbol,
            side=candidate.side,
            amount=identity.amount,
            correlation=candidate.correlation,
            provider_capability=self._evidence.provider_capability,
        )

    def _negative(self, request_id: str, outcome: ReconciliationOutcome):
        return self._evidence.issue(
            request_id=request_id,
            executed=False,
            external_id=None,
            observed_at=datetime.now(timezone.utc),
            source=self.source,
            outcome=outcome,
            provider=self._provider,
            account_id=self._account_id,
            provider_capability=self._evidence.provider_capability,
        )
