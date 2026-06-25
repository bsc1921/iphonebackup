from device_detector import run_cmd
from typing import Dict


def get_developer_mode(udid: str) -> Dict:
    """Get current developer mode status."""
    r = run_cmd(["idevicedevmodectl", "-u", udid, "status"], timeout=10)
    enabled = "enabled" in r["stdout"].lower() or "true" in r["stdout"].lower()
    return {"ok": r["ok"], "enabled": enabled, "raw": r["stdout"] or r["stderr"]}


def enable_developer_mode(udid: str) -> Dict:
    """Enable developer mode (iOS 16+). Device will prompt to confirm."""
    r = run_cmd(["idevicedevmodectl", "-u", udid, "enable"], timeout=15)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def disable_developer_mode(udid: str) -> Dict:
    """Disable developer mode."""
    r = run_cmd(["idevicedevmodectl", "-u", udid, "disable"], timeout=15)
    return {"ok": r["ok"], "message": r["stdout"] or r["stderr"]}


def mount_developer_image(udid: str) -> Dict:
    """Mount developer disk image — required for screenshot on iOS 17+."""
    # Try auto-mount first
    r = run_cmd(["ideviceimagemounter", "-u", udid, "--list"], timeout=15)
    if "PersonalizedImageMounted" in r["stdout"] or "DeveloperDiskImage" in r["stdout"]:
        return {"ok": True, "message": "Developer image already mounted", "mounted": True}

    # Try to auto-mount using Xcode image if available
    r2 = run_cmd(["ideviceimagemounter", "-u", udid, "-t", "Developer"], timeout=30)
    return {
        "ok": r2["ok"],
        "message": r2["stdout"] or r2["stderr"],
        "mounted": r2["ok"],
    }


def list_mounted_images(udid: str) -> Dict:
    """List currently mounted disk images."""
    r = run_cmd(["ideviceimagemounter", "-u", udid, "--list"], timeout=10)
    return {"ok": r["ok"], "images": r["stdout"], "error": r["stderr"]}
