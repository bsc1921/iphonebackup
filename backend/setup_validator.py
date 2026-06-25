"""Validate deployment paths during first-run setup."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import find_libimobiledevice_path, resolve_path
from device_detector import check_tools, run_cmd

REQUIRED_TOOLS = ("idevice_id", "ideviceinfo", "idevicebackup2")


def _check(name: str, ok: bool, message: str, **extra: Any) -> Dict[str, Any]:
    result = {"name": name, "ok": ok, "message": message}
    result.update(extra)
    return result


def validate_backup_root(path_value: str) -> Dict[str, Any]:
    if not str(path_value or "").strip():
        return _check("backup_root", False, "Backup location is required.")

    try:
        path = resolve_path(path_value.strip())
    except Exception as exc:
        return _check("backup_root", False, f"Invalid path: {exc}")

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _check("backup_root", False, f"Cannot create backup folder: {exc}", path=str(path))

    probe = path / f".write-test-{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return _check(
            "backup_root",
            False,
            f"Folder exists but is not writable: {exc}",
            path=str(path),
        )

    log_dir = path / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_probe = log_dir / f".write-test-{uuid.uuid4().hex}"
        log_probe.write_text("ok", encoding="utf-8")
        log_probe.unlink()
    except OSError as exc:
        return _check(
            "backup_root",
            False,
            f"Backup folder is writable, but log folder is not: {exc}",
            path=str(path),
        )

    return _check(
        "backup_root",
        True,
        "Backup location is reachable and writable.",
        path=str(path),
        log_file=str(log_dir / "backup-manager.log"),
    )


def _tool_names_in_dir(directory: Path) -> List[str]:
    suffix = ".exe" if os.name == "nt" else ""
    names = []
    for tool in REQUIRED_TOOLS:
        if (directory / f"{tool}{suffix}").exists() or shutil.which(str(directory / tool)):
            names.append(tool)
    return names


def validate_libimobiledevice(path_value: str = "") -> Dict[str, Any]:
    candidate: Optional[Path] = None
    configured = str(path_value or "").strip()

    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            from config import PROJECT_ROOT

            candidate = PROJECT_ROOT / candidate
        if not candidate.exists():
            return _check(
                "libimobiledevice",
                False,
                f"Tools folder not found: {candidate}",
            )
    else:
        candidate = find_libimobiledevice_path()

    if not candidate:
        return _check(
            "libimobiledevice",
            False,
            "libimobiledevice tools were not found. Provide a tools folder or add them to PATH.",
        )

    found = _tool_names_in_dir(candidate)
    missing = [tool for tool in REQUIRED_TOOLS if tool not in found]
    if missing:
        return _check(
            "libimobiledevice",
            False,
            f"Missing tools in {candidate}: {', '.join(missing)}",
            path=str(candidate),
            missing=missing,
        )

    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(candidate) + os.pathsep + original_path
    try:
        tools = check_tools()
    finally:
        os.environ["PATH"] = original_path

    unavailable = [tool for tool in REQUIRED_TOOLS if not tools.get(tool)]
    if unavailable:
        return _check(
            "libimobiledevice",
            False,
            f"Tools present but not runnable: {', '.join(unavailable)}",
            path=str(candidate),
        )

    return _check(
        "libimobiledevice",
        True,
        "Required iPhone tools are available.",
        path=str(candidate),
        tools=tools,
    )


def validate_network_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    bind_all = bool(payload.get("bind_all_interfaces"))
    token = str(payload.get("api_token") or "").strip()
    if bind_all and not token:
        return _check(
            "network",
            False,
            "An API token is required before exposing the app on your network.",
        )
    return _check("network", True, "Network settings are valid.")


def validate_setup(payload: Dict[str, Any]) -> Dict[str, Any]:
    checks = [
        validate_backup_root(payload.get("backup_root", "")),
        validate_libimobiledevice(payload.get("libimobiledevice_path", "")),
        validate_network_settings(payload),
    ]
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "checks": checks}
