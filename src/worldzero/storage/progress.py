"""Run progress reporting.

A suite run takes hours, and until now nothing recorded that one was alive: a
job that died left an empty log and an unchanged output directory, which looks
exactly like a job still working. Progress is therefore written to a small JSON
file that is updated in place, so "is it running" is answerable without
attaching to the process.

Staleness is what actually distinguishes the two cases. A live run refreshes
``updated_utc``; a dead one stops, and anything that has not been touched for
longer than a few update intervals is reported as stale rather than running.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: A run that has not refreshed for this long is presumed dead rather than busy.
STALE_AFTER_SECONDS = 120.0

#: How often the background thread touches the file. Liveness has to be
#: reported on its own schedule: a single world can run for minutes, so a file
#: refreshed only when work completes makes a healthy job look stale.
HEARTBEAT_SECONDS = 15.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Progress:
    status: str = "starting"
    """starting | running | finished | failed"""
    pid: int = field(default_factory=os.getpid)
    host: str = field(default_factory=socket.gethostname)
    python: str = field(default_factory=platform.python_version)
    started_utc: str = field(default_factory=_utc)
    updated_utc: str = field(default_factory=_utc)
    command: str = ""
    phase: str = ""
    experiment: str = ""
    label: str = ""
    seed: int = 0
    step: int = 0
    max_steps: int = 0
    population: int = 0
    runs_done: int = 0
    runs_total: int = 0
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProgressReporter:
    """Writes a progress file, replacing it atomically on every update.

    Atomic replace matters: a reader polling the file must never catch it
    half-written and conclude the run is broken.
    """

    def __init__(
        self,
        path: str | Path | None,
        *,
        command: str = "",
        min_interval: float = 2.0,
        heartbeat: float = HEARTBEAT_SECONDS,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.min_interval = min_interval
        self.heartbeat = heartbeat
        self.progress = Progress(command=command)
        self._started = time.perf_counter()
        self._last_write = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.write(force=True)

    def start_heartbeat(self) -> None:
        if self.path is None or self.heartbeat <= 0 or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._beat, daemon=True, name="wz-heartbeat")
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _beat(self) -> None:
        while not self._stop.wait(self.heartbeat):
            # Reporting must never take the run down with it.
            try:
                self.write(force=True)
            except OSError:
                continue

    def update(self, *, force: bool = False, **fields: Any) -> None:
        for key, value in fields.items():
            if hasattr(self.progress, key):
                setattr(self.progress, key, value)
        self.write(force=force)

    def run_finished(self) -> None:
        self.progress.runs_done += 1
        self.write(force=True)

    def finish(self, status: str = "finished", error: str | None = None) -> None:
        self.progress.status = status
        self.progress.error = error
        self.write(force=True)

    def write(self, *, force: bool = False) -> None:
        if self.path is None:
            return
        with self._lock:
            now = time.perf_counter()
            if not force and now - self._last_write < self.min_interval:
                return
            self._last_write = now

            self.progress.updated_utc = _utc()
            self.progress.elapsed_seconds = round(now - self._started, 2)
            self.progress.eta_seconds = self._eta()

            # Write beside the target then replace, so a poller never sees a
            # partially written file.
            temporary = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(self.progress.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
            )
            self._replace(temporary)

    def _replace(self, temporary: Path, attempts: int = 5) -> None:
        """Windows refuses to replace a file another handle has open, so a
        reader polling the status can collide with a write. Retry briefly, then
        drop this update: a missed refresh is recoverable, a crashed run is not.
        """
        assert self.path is not None
        for attempt in range(attempts):
            try:
                os.replace(temporary, self.path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    temporary.unlink(missing_ok=True)
                    return
                time.sleep(0.02 * (attempt + 1))

    def _eta(self) -> float | None:
        done, total = self.progress.runs_done, self.progress.runs_total
        if not total or not done or done >= total:
            return None
        rate = self.progress.elapsed_seconds / done
        return round(rate * (total - done), 1)

    def __enter__(self) -> ProgressReporter:
        self.progress.status = "running"
        self.write(force=True)
        self.start_heartbeat()
        return self

    def __exit__(self, exc_type, exc, _traceback) -> None:
        self.stop_heartbeat()
        if exc_type is None:
            self.finish("finished")
        else:
            self.finish("failed", f"{exc_type.__name__}: {exc}")


def read_progress(path: str | Path) -> dict[str, Any]:
    """Load a progress file and classify liveness from its own timestamp."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    updated = datetime.fromisoformat(data["updated_utc"])
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    data["seconds_since_update"] = round(age, 1)

    if data.get("status") == "running" and age > STALE_AFTER_SECONDS:
        # The process stopped refreshing without recording an outcome, which is
        # what a killed or crashed run looks like from the outside.
        data["status"] = "stale"
        data["error"] = data.get("error") or (
            f"no update for {age:.0f}s; the process is probably gone"
        )
    data["alive"] = data.get("status") in {"starting", "running"}
    return data


def format_progress(data: dict[str, Any]) -> str:
    lines = [
        f"status   : {data.get('status')}"
        + (f"  ({data['error']})" if data.get("error") else ""),
        f"command  : {data.get('command') or '-'}",
        f"pid      : {data.get('pid')} on {data.get('host')}",
        f"started  : {data.get('started_utc')}",
        f"updated  : {data.get('updated_utc')}  ({data.get('seconds_since_update')}s ago)",
    ]
    if data.get("phase"):
        lines.append(f"phase    : {data['phase']}")
    if data.get("runs_total"):
        lines.append(f"runs     : {data.get('runs_done')}/{data.get('runs_total')}")
    if data.get("max_steps"):
        lines.append(
            f"step     : {data.get('step')}/{data.get('max_steps')}  "
            f"pop {data.get('population')}"
        )
    lines.append(f"elapsed  : {data.get('elapsed_seconds')}s")
    if data.get("eta_seconds") is not None:
        lines.append(f"eta      : {data['eta_seconds']}s")
    return "\n".join(lines)


def serve(path: str | Path, port: int, *, host: str = "127.0.0.1") -> None:
    """Expose the progress file over HTTP. Blocks until interrupted.

    Read-only and loopback by default: this reports on a local simulation, and
    binding it more widely would expose run internals for no benefit.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    target = Path(path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            if self.path not in ("/", "/status", "/healthz"):
                self.send_error(404)
                return
            try:
                data = read_progress(target)
            except FileNotFoundError:
                data = {"status": "unknown", "alive": False, "error": f"no such file: {target}"}
            except json.JSONDecodeError as exc:
                data = {"status": "unknown", "alive": False, "error": f"unreadable: {exc}"}

            body = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
            # /healthz answers with a status code so a watchdog needs no parsing.
            code = 200 if (self.path != "/healthz" or data.get("alive")) else 503
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: Any) -> None:
            return

    server = HTTPServer((host, port), Handler)
    print(f"serving {target} at http://{host}:{port}/  (/status, /healthz)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
