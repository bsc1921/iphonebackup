import subprocess
import json
from typing import Dict, List
from device_detector import run_cmd


def afc_list(udid: str, path: str = "/") -> Dict:
    """List files/folders at a given path on the iPhone via AFC."""
    r = run_cmd(["afcclient", "-u", udid, "ls", path], timeout=15)
    if not r["ok"] and r["returncode"] == 127:
        return {"ok": False, "error": "afcclient not found"}
    items = []
    for line in r["stdout"].splitlines():
        line = line.strip()
        if line:
            items.append(line)
    return {"ok": True, "path": path, "items": items, "error": r["stderr"] if not r["ok"] else ""}


def afc_info(udid: str, path: str) -> Dict:
    """Get info about a file or folder."""
    r = run_cmd(["afcclient", "-u", udid, "info", path], timeout=10)
    info = {}
    for line in r["stdout"].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return {"ok": r["ok"], "path": path, "info": info}


def afc_download(udid: str, remote_path: str, local_path: str) -> Dict:
    """Download a file from the iPhone."""
    r = run_cmd(["afcclient", "-u", udid, "pull", remote_path, local_path], timeout=60)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def afc_upload(udid: str, local_path: str, remote_path: str) -> Dict:
    """Upload a file to the iPhone."""
    r = run_cmd(["afcclient", "-u", udid, "push", local_path, remote_path], timeout=60)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def afc_mkdir(udid: str, path: str) -> Dict:
    """Create a directory on the iPhone."""
    r = run_cmd(["afcclient", "-u", udid, "mkdir", path], timeout=10)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def afc_remove(udid: str, path: str) -> Dict:
    """Remove a file or directory on the iPhone."""
    r = run_cmd(["afcclient", "-u", udid, "rm", path], timeout=10)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}
