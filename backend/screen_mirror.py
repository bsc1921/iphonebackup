import subprocess
import threading
import base64
import time
import os
import tempfile
from typing import Optional

_mirror_active = False
_mirror_lock = threading.Lock()
_latest_frame: Optional[str] = None  # base64 PNG
_mirror_fps = 0.0
_mirror_error = ""


def get_mirror_state() -> dict:
    return {
        "active": _mirror_active,
        "frame": _latest_frame,
        "fps": round(_mirror_fps, 1),
        "error": _mirror_error,
    }


def start_mirror(udid: str, interval: float = 0.25) -> dict:
    global _mirror_active
    with _mirror_lock:
        if _mirror_active:
            return {"ok": True, "message": "Already running"}
        _mirror_active = True

    threading.Thread(target=_capture_loop, args=(udid, interval), daemon=True).start()
    return {"ok": True, "message": "Mirror started"}


def stop_mirror() -> dict:
    global _mirror_active, _latest_frame, _mirror_error
    _mirror_active = False
    _latest_frame = None
    _mirror_error = ""
    return {"ok": True, "message": "Mirror stopped"}


def _capture_loop(udid: str, interval: float):
    global _mirror_active, _latest_frame, _mirror_fps, _mirror_error

    tmp_fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(tmp_fd)
    frame_times = []

    while _mirror_active:
        t0 = time.time()
        try:
            r = subprocess.run(
                ["idevicescreenshot", "-u", udid, tmp],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0 and os.path.exists(tmp):
                with open(tmp, "rb") as f:
                    _latest_frame = base64.b64encode(f.read()).decode()
                os.remove(tmp)
                _mirror_error = ""
            else:
                _mirror_error = r.stderr.decode(errors="ignore").strip() or "Screenshot failed"
        except subprocess.TimeoutExpired:
            _mirror_error = "Screenshot timed out"
        except Exception as e:
            _mirror_error = str(e)

        elapsed = time.time() - t0
        frame_times.append(elapsed)
        if len(frame_times) > 10:
            frame_times.pop(0)
        avg = sum(frame_times) / len(frame_times)
        _mirror_fps = 1.0 / avg if avg > 0 else 0

        sleep = max(0, interval - elapsed)
        time.sleep(sleep)

    if os.path.exists(tmp):
        os.remove(tmp)
