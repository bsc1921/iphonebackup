import subprocess
import threading
import queue
from typing import Optional

_syslog_process: Optional[subprocess.Popen] = None
_syslog_queue: queue.Queue = queue.Queue(maxsize=500)
_syslog_active = False


def start_syslog(udid: str) -> dict:
    global _syslog_process, _syslog_active
    if _syslog_active:
        return {"ok": True, "message": "Already running"}

    _syslog_active = True
    # Clear old entries
    while not _syslog_queue.empty():
        try:
            _syslog_queue.get_nowait()
        except queue.Empty:
            break

    def _run():
        global _syslog_process, _syslog_active
        try:
            _syslog_process = subprocess.Popen(
                ["idevicesyslog", "-u", udid],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in _syslog_process.stdout:
                if not _syslog_active:
                    break
                line = line.rstrip()
                if line:
                    try:
                        _syslog_queue.put_nowait(line)
                    except queue.Full:
                        try:
                            _syslog_queue.get_nowait()
                            _syslog_queue.put_nowait(line)
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            _syslog_active = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Syslog started"}


def stop_syslog() -> dict:
    global _syslog_process, _syslog_active
    _syslog_active = False
    if _syslog_process and _syslog_process.poll() is None:
        _syslog_process.terminate()
    return {"ok": True, "message": "Syslog stopped"}


def get_syslog_state() -> dict:
    return {"active": _syslog_active}


def syslog_generator():
    """Generator that yields syslog lines for SSE streaming."""
    while _syslog_active:
        try:
            line = _syslog_queue.get(timeout=2)
            yield line
        except queue.Empty:
            yield None  # heartbeat
