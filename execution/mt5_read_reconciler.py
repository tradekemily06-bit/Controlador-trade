from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
        self._context_provider = context_provider
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
            identity = MT5ReconciliationIdentity(
                request_id=request_id.strip(),
                symbol=str(context["symbol"]).strip(),
                side=str(context["side"]).upper().replace("COMPRA", "BUY").replace("VENDA", "SELL"),
                amount=float(context["amount"]),
                correlation=str(context["correlation"]).strip(),
                magic=int(context["magic"]),
            )
        except (KeyError, TypeError, ValueError):
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        if identity.request_id != request_id.strip():
            return self._negative(request_id.strip(), ReconciliationOutcome.QUERY_FAILED)
        return self.resolve(identity)

    def resolve(self, identity: MT5ReconciliationIdentity) -> RealReconciliationObservation:
        """Resolve an already-persisted identity; never dispatches."""
        if not self._valid_identity(identity):
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        candidates: list[MT5HistoryCandidate] = []
        try:
            deals = self._deals_query(
                symbol=identity.symbol,
                correlation=identity.correlation,
                magic=identity.magic,
            )
            orders = self._orders_query(
                symbol=identity.symbol,
                correlation=identity.correlation,
                magic=identity.magic,
            )
        except Exception:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        if deals is None or orders is None:
            return self._negative(identity.request_id, ReconciliationOutcome.QUERY_FAILED)

        for raw in list(deals) + list(orders):
            candidate = self._normalize(raw, identity)
            if candidate is not None:
                candidates.append(candidate)

        # A deal is the execution identity. Matching order records are
        # supporting evidence for that same deal and must not create a second
        # execution candidate. Distinct deals remain ambiguous.
        deals = [c for c in candidates if c.kind is ExternalIdentityKind.DEAL]
        if deals:
            unique = {c.ticket: c for c in deals}
            if len(unique) != 1:
                return self._negative(identity.request_id, ReconciliationOutcome.AMBIGUOUS)
            candidate = next(iter(unique.values()))
            return self._executed(identity, candidate)

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
        if not math.isclose(float(amount), identity.amount, rel_tol=0.0, abs_tol=1e-9):
            return None
        if not isinstance(correlation, str) or correlation.strip() != identity.correlation:
            return None
        if not isinstance(magic, int) or isinstance(magic, bool) or magic != identity.magic:
            return None

        observed_at = getattr(raw, "observed_at", None)
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
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

    def _executed(self, identity: MT5ReconciliationIdentity, candidate: MT5HistoryCandidate):
        return self._evidence.issue(
            request_id=identity.request_id,
            executed=True,
            external_id=candidate.ticket,
            observed_at=candidate.observed_at,
            source=self.source,
            outcome=ReconciliationOutcome.EXECUTED,
            external_id_kind=ExternalIdentityKind.DEAL,
            provider=candidate.provider,
            account_id=candidate.account_id,
            symbol=candidate.symbol,
            side=candidate.side,
            amount=candidate.amount,
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
