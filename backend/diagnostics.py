import shutil
import tempfile
from typing import Dict

from device_detector import run_cmd


def get_battery_health(udid: str) -> Dict:
    r = run_cmd(["idevicediagnostics", "-u", udid, "diagnostics", "All"], timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"]}

    data = {}
    for line in r["stdout"].splitlines():
        line = line.strip()
        if "BatteryCurrentCapacity" in line:
            data["level"] = _extract_value(line)
        elif "BatteryIsCharging" in line:
            data["charging"] = _extract_value(line)
        elif "ExternalConnected" in line:
            data["plugged"] = _extract_value(line)
        elif "FullChargeCapacity" in line:
            data["full_capacity"] = _extract_value(line)
        elif "DesignCapacity" in line:
            data["design_capacity"] = _extract_value(line)
        elif "CycleCount" in line:
            data["cycle_count"] = _extract_value(line)
        elif "Temperature" in line and "battery" not in line.lower():
            data["temperature"] = _extract_value(line)

    try:
        health = round(int(data["full_capacity"]) / int(data["design_capacity"]) * 100, 1)
        data["health_pct"] = health
    except Exception:
        data["health_pct"] = None

    return {"ok": True, "battery": data}


def get_sleep_log(udid: str) -> Dict:
    r = run_cmd(["idevicediagnostics", "-u", udid, "mobilegestalt", "SleepWakeFailureString"], timeout=15)
    return {"ok": r["ok"], "log": r["stdout"] or r["stderr"]}


def get_crash_reports(udid: str) -> Dict:
    tmp = tempfile.mkdtemp(prefix="iphone-manager-crashes-")
    try:
        r = run_cmd(["idevicecrashreport", "-u", udid, "-e", tmp], timeout=30)
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"], "reports": []}

        reports = []
        for name in os.listdir(tmp):
            fpath = os.path.join(tmp, name)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                reports.append({"name": name, "size_kb": round(size / 1024, 1)})

        return {"ok": True, "reports": sorted(reports, key=lambda x: x["name"], reverse=True)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restart_device(udid: str) -> Dict:
    r = run_cmd(["idevicediagnostics", "-u", udid, "restart"], timeout=10)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def shutdown_device(udid: str) -> Dict:
    r = run_cmd(["idevicediagnostics", "-u", udid, "shutdown"], timeout=10)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def _extract_value(line: str) -> str:
    if ":" in line:
        return line.split(":", 1)[1].strip()
    if "=" in line:
        return line.split("=", 1)[1].strip()
    return line.strip()
