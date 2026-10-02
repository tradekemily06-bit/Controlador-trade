from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_MT5_WAIT_SECONDS = 180
DEFAULT_MT5_PREFLIGHT_TIMEOUT_SECONDS = 20
DEFAULT_RESTART_DELAY_SECONDS = 10
DEFAULT_MAX_RESTARTS_PER_HOUR = 6
DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/api/health"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ControllerRuntimeSupervisor:
    """Python equivalent of the Windows Controller supervisor.

    This layer supervises startup only. It never authorizes execution and
    delegates the actual runtime safety gates to app.py/core.
    """

    def __init__(
        self,
        project_root: Path,
        python_exe: str,
        runtime_dir: Path,
        mt5_wait_seconds: int = DEFAULT_MT5_WAIT_SECONDS,
        restart_delay_seconds: int = DEFAULT_RESTART_DELAY_SECONDS,
        max_restarts_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR,
        health_url: str = DEFAULT_HEALTH_URL,
    ) -> None:
        self.project_root = project_root.resolve()
        self.python_exe = python_exe
        self.runtime_dir = runtime_dir.resolve()
        self.mt5_wait_seconds = mt5_wait_seconds
        self.restart_delay_seconds = restart_delay_seconds
        self.max_restarts_per_hour = max_restarts_per_hour
        self.health_url = health_url

        self.log_path = self.runtime_dir / "controlador-startup.log"
        self.status_path = self.runtime_dir / "controlador-supervisor-status.json"
        self.stop_path = self.runtime_dir / "controlador.supervisor.stop"
        self.restart_history_path = (
            self.runtime_dir / "controlador-supervisor-restart-history.json"
        )
        self.restart_times: deque[datetime] = deque()
        self.child: subprocess.Popen[str] | None = None

    def prepare(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._load_restart_history()

    def _log(self, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")

    def _write_status(self, state: str, reason: str) -> None:
        payload = {
            "component": "controlador",
            "state": state,
            "reason": reason,
            "observed_at": utc_now(),
            "restart_count_last_hour": len(self.restart_times),
        }
        temporary = self.status_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.status_path)

    def _load_restart_history(self) -> None:
        if not self.restart_history_path.is_file():
            return
        try:
            values = json.loads(self.restart_history_path.read_text(encoding="utf-8"))
            if not isinstance(values, list):
                return
            now = datetime.now(timezone.utc)
            for value in values:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed >= now - timedelta(hours=1):
                    self.restart_times.append(parsed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.restart_times.clear()

    def _save_restart_history(self) -> None:
        values = [value.astimezone(timezone.utc).isoformat() for value in self.restart_times]
        temporary = self.restart_history_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(values, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.restart_history_path)

    def _prune_restart_history(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        while self.restart_times and self.restart_times[0] < cutoff:
            self.restart_times.popleft()

    def _health_check(self) -> bool:
        try:
            with urllib.request.urlopen(self.health_url, timeout=2) as response:
                if response.status != 200:
                    return False
                body = response.read()
                if not body:
                    return False
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return False
                return isinstance(payload, dict)
        except (OSError, urllib.error.URLError):
            return False

    def _mt5_demo_ready(self) -> bool:
        code = (
            "import MetaTrader5 as mt5; "
            "from execution.mt5_demo_runtime_preflight import run_preflight; "
            "result = run_preflight(mt5); "
            "raise SystemExit(0 if result.available and result.demo else 1)"
        )
        deadline = time.monotonic() + self.mt5_wait_seconds

        while time.monotonic() < deadline and not self.stop_path.exists():
            try:
                completed = subprocess.run(
                    [self.python_exe, "-c", code],
                    cwd=self.project_root,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=DEFAULT_MT5_PREFLIGHT_TIMEOUT_SECONDS,
                )
                if completed.returncode == 0:
                    return True
                detail = (completed.stdout or completed.stderr or "").strip()
                self._log(
                    "Pré-verificação DEMO retornou código "
                    f"{completed.returncode}."
                    + (f" Detalhe: {detail}" if detail else "")
                )
            except subprocess.TimeoutExpired:
                self._log(
                    "Pré-verificação DEMO excedeu "
                    f"{DEFAULT_MT5_PREFLIGHT_TIMEOUT_SECONDS}s; nova tentativa."
                )
            except OSError as exc:
                self._log(
                    f"Não foi possível executar o Python do preflight: {exc!r}."
                )
            time.sleep(5)

        return False

    def _start_app(self) -> int:
        log_handle = self.log_path.open("a", encoding="utf-8")
        try:
            self.child = subprocess.Popen(
                [self.python_exe, "-u", str(self.project_root / "app.py")],
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            log_handle.close()

        return self.child.wait()

    def _stop_child(self) -> None:
        if self.child is None or self.child.poll() is not None:
            return
        try:
            self.child.terminate()
            self.child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait(timeout=5)

    def run(self) -> int:
        self.prepare()
        self._log("Supervisor Python do Controlador iniciado.")

        final_state = "STOPPED"
        final_reason = "Supervisor finalizado."

        try:
            while not self.stop_path.exists():
                self._prune_restart_history()

                self._write_status(
                    "STARTING",
                    "Pré-verificação DEMO antes de iniciar o Controlador.",
                )
                demo_ready = self._mt5_demo_ready()

                if demo_ready:
                    self._log("MT5 DEMO confirmado; Controlador pode iniciar.")
                else:
                    self._log(
                        "MT5 DEMO não confirmado; Controlador será iniciado, "
                        "mas os gates de execução continuam responsáveis pelo bloqueio."
                    )

                # If an already-running controller survived a task restart,
                # keep supervising the existing runtime instead of spawning a second one.
                if self._health_check():
                    self._log(
                        "Controlador já responde no endpoint de health; "
                        "nenhuma segunda instância será criada."
                    )
                    self._write_status("HEALTHY", "Instância existente detectada.")
                    time.sleep(10)
                    continue

                self._log("Iniciando app.py sob supervisão Python.")
                self._write_status(
                    "STARTING",
                    "Processo app.py iniciado; aguardando health.",
                )

                exit_code = self._start_app()
                self._log(f"Controlador finalizado com código de saída {exit_code}.")

                if self.stop_path.exists():
                    break

                self._prune_restart_history()
                if len(self.restart_times) >= self.max_restarts_per_hour:
                    self._log(
                        f"Limite de reinícios atingido ({self.max_restarts_per_hour}/h). "
                        "Controlador permanece parado."
                    )
                    final_state = "FAILED"
                    final_reason = "RESTART_LIMIT_EXCEEDED"
                    self._write_status(final_state, final_reason)
                    return 1

                self.restart_times.append(datetime.now(timezone.utc))
                self._save_restart_history()
                self._write_status(
                    "RECOVERING",
                    f"Controlador terminou com código {exit_code}; "
                    "nova tentativa após backoff.",
                )
                time.sleep(self.restart_delay_seconds)

        except KeyboardInterrupt:
            self._log("Parada solicitada pelo operador.")
            final_state = "STOPPED"
            final_reason = "INTERRUPTED"
        except Exception as exc:
            self._log(f"Falha no supervisor Python: {exc!r}")
            final_state = "FAILED"
            final_reason = "SUPERVISOR_EXCEPTION"
            self._write_status(final_state, final_reason)
            return 1
        finally:
            self._stop_child()
            if self.stop_path.exists():
                self._log("Parada controlada solicitada pelo marcador do runtime.")
                try:
                    self.stop_path.unlink()
                except OSError:
                    pass
            self._write_status(final_state, final_reason)

        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supervisor Python do Controlador Trading.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--mt5-wait-seconds", type=int, default=DEFAULT_MT5_WAIT_SECONDS)
    parser.add_argument(
        "--restart-delay-seconds",
        type=int,
        default=DEFAULT_RESTART_DELAY_SECONDS,
    )
    parser.add_argument(
        "--max-restarts-per-hour",
        type=int,
        default=DEFAULT_MAX_RESTARTS_PER_HOUR,
    )
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    supervisor = ControllerRuntimeSupervisor(
        project_root=Path(args.project_root),
        python_exe=args.python_exe,
        runtime_dir=Path(args.runtime_dir),
        mt5_wait_seconds=args.mt5_wait_seconds,
        restart_delay_seconds=args.restart_delay_seconds,
        max_restarts_per_hour=args.max_restarts_per_hour,
        health_url=args.health_url,
    )
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
