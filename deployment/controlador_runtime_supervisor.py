from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_MT5_WAIT_SECONDS = 180
DEFAULT_MT5_PREFLIGHT_TIMEOUT_SECONDS = 20
DEFAULT_RESTART_DELAY_SECONDS = 10
DEFAULT_MAX_RESTARTS_PER_HOUR = 6
DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/api/health"
DEFAULT_STARTUP_HEALTH_TIMEOUT_SECONDS = 120
DEFAULT_HEALTH_POLL_SECONDS = 10
DEFAULT_HEALTH_FAILURE_THRESHOLD = 3
DEFAULT_STATUS_WRITE_RETRIES = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupervisorProcessLock:
    """Prevent overlapping controller supervisors on Windows Task Scheduler restarts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None
        self._windows = sys.platform == "win32"

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure the lock file has one byte before opening it for byte-range locking.
        if not self.path.exists():
            try:
                self.path.write_bytes(b"0")
            except FileExistsError:
                pass
        elif self.path.stat().st_size == 0:
            try:
                self.path.write_bytes(b"0")
            except OSError:
                pass

        self.handle = self.path.open("r+b")
        try:
            self.handle.seek(0)
            if self._windows:
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, ImportError):
            try:
                self.handle.close()
            finally:
                self.handle = None
            return False

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if self._windows:
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            pass
        finally:
            self.handle.close()
            self.handle = None



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
        startup_health_timeout_seconds: int = DEFAULT_STARTUP_HEALTH_TIMEOUT_SECONDS,
        health_poll_seconds: int = DEFAULT_HEALTH_POLL_SECONDS,
        health_failure_threshold: int = DEFAULT_HEALTH_FAILURE_THRESHOLD,
    ) -> None:
        self.project_root = project_root.resolve()
        self.python_exe = python_exe
        self.runtime_dir = runtime_dir.resolve()
        self.mt5_wait_seconds = mt5_wait_seconds
        self.restart_delay_seconds = restart_delay_seconds
        self.max_restarts_per_hour = max_restarts_per_hour
        self.health_url = health_url
        self.startup_health_timeout_seconds = startup_health_timeout_seconds
        self.health_poll_seconds = health_poll_seconds
        self.health_failure_threshold = health_failure_threshold

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

    def _atomic_write_text(self, path: Path, content: str) -> None:
        """Write a runtime file atomically and tolerate short Windows sharing races."""
        last_error: OSError | None = None
        for attempt in range(DEFAULT_STATUS_WRITE_RETRIES):
            temporary = path.with_name(
                f"{path.name}.{os.getpid()}.{attempt}.tmp"
            )
            try:
                temporary.write_text(content, encoding="utf-8")
                os.replace(temporary, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.2)
            finally:
                try:
                    temporary.unlink()
                except OSError:
                    pass
        if last_error is not None:
            raise last_error

    def _write_status(self, state: str, reason: str) -> None:
        payload = {
            "component": "controlador",
            "state": state,
            "reason": reason,
            "observed_at": utc_now(),
            "restart_count_last_hour": len(self.restart_times),
        }
        self._atomic_write_text(
            self.status_path,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

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
        self._atomic_write_text(
            self.restart_history_path,
            json.dumps(values, ensure_ascii=False),
        )

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

    def _start_app(self) -> subprocess.Popen[str]:
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

        return self.child

    def _stop_existing_controller(self) -> bool:
        """Stop only an existing app.py that owns the configured health port."""
        if sys.platform != "win32":
            return False
        try:
            port = urlparse(self.health_url).port
            if port is None:
                return False
            pid_query = (
                f"(Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
                "| Select-Object -First 1 -ExpandProperty OwningProcess)"
            )
            pid_result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", pid_query],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            pid_text = (pid_result.stdout or "").strip()
            if not pid_text.isdigit():
                return False
            pid = int(pid_text)
            command_query = (
                f"(Get-CimInstance Win32_Process -Filter "
                f"'ProcessId = {pid}' | Select-Object -ExpandProperty CommandLine)"
            )
            command_result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command_query],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            command_line = (command_result.stdout or "").strip()
            if "app.py" not in command_line or str(self.project_root) not in command_line:
                self._log(
                    f"Health port {port} pertence ao PID {pid}, mas o processo "
                    "não foi reconhecido como o app.py deste projeto; não será encerrado."
                )
                return False
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            self._log(f"Instância existente app.py encerrada para recuperação (PID {pid}).")
            return True
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._log(f"Não foi possível encerrar instância existente com segurança: {exc!r}")
            return False

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
        supervisor_lock = SupervisorProcessLock(self.runtime_dir / "controlador-supervisor.lock")
        if not supervisor_lock.acquire():
            self._log("Outro supervisor do Controlador já está ativo; esta instância será encerrada sem criar um segundo supervisor.")
            return 0
        self._log("Supervisor Python do Controlador iniciado.")

        final_state = "STOPPED"
        final_reason = "Supervisor finalizado."

        try:
            while not self.stop_path.exists():
                self._prune_restart_history()

                # MT5 readiness is deliberately not a prerequisite for HTTP availability.
                # The controller must come up independently; execution gates fail closed
                # until the MT5/runtime safety state is actually healthy.
                self._write_status(
                    "STARTING",
                    "Iniciando o Controlador; prontidão MT5 é monitorada separadamente pelos gates de execução.",
                )

                # If an already-running controller survived a task restart,
                # keep supervising the existing runtime instead of spawning a second one.
                if self._health_check():
                    self._log(
                        "Controlador já responde no endpoint de health; "
                        "nenhuma segunda instância será criada."
                    )
                    self._write_status("HEALTHY", "Instância existente detectada.")
                    health_failures = 0
                    while not self.stop_path.exists():
                        time.sleep(self.health_poll_seconds)
                        if self._health_check():
                            health_failures = 0
                            continue
                        health_failures += 1
                        self._log(
                            f"Falha de health do Controlador já existente "
                            f"({health_failures}/{self.health_failure_threshold})."
                        )
                        if health_failures >= self.health_failure_threshold:
                            self._log(
                                "Instância existente permanece viva mas sem health; "
                                "será encerrada para recuperação."
                            )
                            self._write_status(
                                "RECOVERING",
                                "Instância existente perdeu health de forma persistente.",
                            )
                            if not self._stop_existing_controller():
                                self._log(
                                    "Instância existente não pôde ser encerrada com segurança; "
                                    "supervisor será encerrado para evitar segunda instância."
                                )
                                final_state = "FAILED"
                                final_reason = "EXISTING_CONTROLLER_UNSAFE_TO_STOP"
                                self._write_status(final_state, final_reason)
                                return 1
                            break
                    if self.stop_path.exists():
                        break
                    continue

                self._log("Iniciando app.py sob supervisão Python.")
                self._write_status(
                    "STARTING",
                    "Processo app.py iniciado; aguardando health.",
                )

                child = self._start_app()
                startup_deadline = time.monotonic() + self.startup_health_timeout_seconds
                healthy = False

                while time.monotonic() < startup_deadline and not self.stop_path.exists():
                    exit_code = child.poll()
                    if exit_code is not None:
                        self._log(f"Controlador finalizado com código de saída {exit_code}.")
                        break
                    if self._health_check():
                        healthy = True
                        self._write_status("HEALTHY", "Controlador responde ao health.")
                        self._log("Controlador confirmou health; supervisão contínua iniciada.")
                        break
                    time.sleep(2)

                if self.stop_path.exists():
                    break

                if child.poll() is None and not healthy:
                    self._log(
                        "Controlador não confirmou health dentro da janela de inicialização; "
                        "processo será encerrado para recuperação."
                    )
                    self._write_status(
                        "RECOVERING",
                        "Processo ativo, mas health não respondeu durante a inicialização.",
                    )
                    self._stop_child()
                elif child.poll() is not None:
                    exit_code = child.returncode

                if child.poll() is None and healthy:
                    health_failures = 0
                    while not self.stop_path.exists():
                        time.sleep(self.health_poll_seconds)
                        if self._health_check():
                            health_failures = 0
                            continue
                        health_failures += 1
                        self._log(
                            f"Falha de health do Controlador "
                            f"({health_failures}/{self.health_failure_threshold})."
                        )
                        if health_failures >= self.health_failure_threshold:
                            self._log(
                                "Controlador permanece vivo mas sem health; "
                                "encerrando processo para recuperação."
                            )
                            self._write_status(
                                "RECOVERING",
                                "Processo ativo, mas health permaneceu indisponível.",
                            )
                            self._stop_child()
                            break

                    if self.stop_path.exists():
                        break

                    exit_code = child.poll()
                    if exit_code is None:
                        self._stop_child()
                    exit_code = child.returncode
                    self._log(
                        f"Controlador finalizado após perda de health; "
                        f"código de saída {exit_code}."
                    )

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
            supervisor_lock.release()
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
    parser.add_argument("--startup-health-timeout-seconds", type=int, default=DEFAULT_STARTUP_HEALTH_TIMEOUT_SECONDS)
    parser.add_argument("--health-poll-seconds", type=int, default=DEFAULT_HEALTH_POLL_SECONDS)
    parser.add_argument("--health-failure-threshold", type=int, default=DEFAULT_HEALTH_FAILURE_THRESHOLD)
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
        startup_health_timeout_seconds=args.startup_health_timeout_seconds,
        health_poll_seconds=args.health_poll_seconds,
        health_failure_threshold=args.health_failure_threshold,
    )
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
