from __future__ import annotations

from threading import Event, Thread
from typing import Any

from execution.execution_ledger import ExecutionLedgerStatus


class TimedExitWorker:
    """Supervised, durable best-effort DEMO exit worker; never runs on module import."""

    def __init__(self, service: Any, operational_runtime: Any, *, poll_seconds: float = 1.0) -> None:
        if poll_seconds < 0.25 or poll_seconds > 60:
            raise ValueError("poll_seconds deve estar entre 0.25 e 60")
        self.service = service
        self.runtime = operational_runtime
        self.poll_seconds = poll_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        thread = Thread(target=self._run, name="controlador-demo-timed-exit", daemon=True)
        self._thread = thread
        try:
            thread.start()
        except BaseException:
            # A failed Thread.start() must not leave an unstarted Thread object
            # behind: stop() cannot join a thread that never started.
            self._thread = None
            self._stop.set()
            raise

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=timeout)
        if thread.is_alive():
            # Do not report shutdown complete while a worker may still access MT5.
            # The API's finally block must retain RuntimeProcessLock in this case.
            raise RuntimeError(
                "worker de saída temporizada ainda está ativo; exclusividade do runtime deve ser mantida"
            )
        self._thread = None

    def run_once(self) -> int:
        store = getattr(self.runtime, "timed_exits", None)
        if store is None:
            return 0
        processed = 0
        for schedule in store.due():
            processed += 1
            try:
                identity = self.runtime.execution_ledger.record_for(schedule.request_id)
                if (
                    identity is None
                    or identity.status not in (
                        ExecutionLedgerStatus.ACCEPTED,
                        ExecutionLedgerStatus.RECONCILED_EXECUTED,
                    )
                    or identity.cycle_id != schedule.cycle_id
                    or identity.external_id != schedule.external_id
                    or identity.account_fingerprint != schedule.account_fingerprint
                ):
                    store.block(schedule.request_id, message="identidade persistida divergiu do agendamento; fechamento automático bloqueado")
                    continue

                # Always reconcile first. On restart this also recovers a close
                # that may have been sent just before the prior process stopped.
                observation = self.service.reconcile_mt5_position_close(
                    cycle_id=schedule.cycle_id,
                    external_id=schedule.external_id,
                )
                state = str(observation.get("state", "UNKNOWN")).upper()
                if state == "CLOSED":
                    store.mark_closed(schedule.request_id, message="MT5 confirmou que a posição DEMO está encerrada")
                    continue
                if state != "OPEN":
                    store.retry_later(
                        schedule.request_id,
                        message=f"estado MT5 inconclusivo ({state}); nova consulta somente leitura será tentada",
                        delay_seconds=30,
                    )
                    continue

                close_result = self.service.close_mt5_position(
                    cycle_id=schedule.cycle_id,
                    external_id=schedule.external_id,
                )
                if getattr(close_result, "accepted", False) is True:
                    store.mark_closed(
                        schedule.request_id,
                        message="fechamento DEMO enviado e ausência da posição confirmada pelo adaptador MT5",
                    )
                else:
                    store.retry_later(
                        schedule.request_id,
                        message=f"fechamento não confirmado: {getattr(close_result, 'message', 'resultado desconhecido')}",
                        delay_seconds=30,
                    )
            except Exception as exc:
                try:
                    store.retry_later(
                        schedule.request_id,
                        message=f"saída temporizada inconclusiva ({type(exc).__name__}); reconciliação será repetida",
                        delay_seconds=30,
                    )
                except Exception:
                    # Preserve the worker: the persistent schedule remains due
                    # and will be retried after a process restart.
                    pass
        return processed

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                # A worker fault must not terminate the supervised API process.
                pass
            self._stop.wait(self.poll_seconds)
