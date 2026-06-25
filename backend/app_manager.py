import subprocess
from typing import Dict, List
from device_detector import run_cmd


def list_apps(udid: str) -> Dict:
    r = run_cmd(["ideviceinstaller", "-u", udid, "-l", "-o", "list_all"], timeout=30)
    if not r["ok"]:
        return {"ok": False, "apps": [], "error": r["stderr"]}

    apps = []
    for line in r["stdout"].splitlines():
        line = line.strip()
        if not line or line.startswith("Total:") or line.startswith("CFBundleIdentifier"):
            continue
        parts = line.split(",", 2)
        if len(parts) >= 2:
            bundle_id = parts[0].strip()
            version   = parts[1].strip() if len(parts) > 1 else ""
            name      = parts[2].strip().strip('"') if len(parts) > 2 else bundle_id
            apps.append({"bundle_id": bundle_id, "version": version, "name": name})

    return {"ok": True, "apps": apps, "count": len(apps)}


def uninstall_app(udid: str, bundle_id: str) -> Dict:
    r = run_cmd(["ideviceinstaller", "-u", udid, "-U", bundle_id], timeout=30)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def install_app(udid: str, ipa_path: str) -> Dict:
    r = run_cmd(["ideviceinstaller", "-u", udid, "-i", ipa_path], timeout=120)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}
