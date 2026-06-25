import subprocess
import threading
from typing import Dict, Optional
from device_detector import run_cmd

_location_process: Optional[subprocess.Popen] = None
_location_active = False
_current_location = {"lat": None, "lon": None}


def set_location(udid: str, lat: float, lon: float) -> Dict:
    """Set a spoofed GPS location on the device."""
    global _location_process, _location_active, _current_location

    stop_location(udid)

    r = run_cmd(
        ["idevicesetlocation", "-u", udid, "--", str(lat), str(lon)],
        timeout=10,
    )
    if r["ok"] or "set" in r["stdout"].lower():
        _current_location = {"lat": lat, "lon": lon}
        _location_active = True
        return {"ok": True, "lat": lat, "lon": lon, "message": "Location set"}
    return {"ok": False, "message": r["stdout"] or r["stderr"]}


def stop_location(udid: str = "") -> Dict:
    """Reset location to real GPS."""
    global _location_process, _location_active, _current_location
    _location_active = False
    _current_location = {"lat": None, "lon": None}
    if udid:
        r = run_cmd(["idevicesetlocation", "-u", udid, "reset"], timeout=10)
        return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}
    return {"ok": True, "message": "Location reset"}


def get_location_state() -> Dict:
    return {
        "active": _location_active,
        "lat": _current_location["lat"],
        "lon": _current_location["lon"],
    }
