"""Central configuration and path resolution for iPhone Backup Manager."""

from __future__ import annotations

import json
import os
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent


def get_config_path() -> Path:
    explicit = os.environ.get("IPHONE_MANAGER_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    config_dir = os.environ.get("IPHONE_MANAGER_CONFIG_DIR", "").strip()
    if config_dir:
        return Path(config_dir).expanduser() / "config.json"

    return BACKEND_DIR / "config.json"


CONFIG_PATH = get_config_path()

DEFAULTS: Dict[str, Any] = {
    "setup_complete": False,
    "host": "127.0.0.1",
    "port": 5055,
    "bind_all_interfaces": False,
    "api_token": "",
    "backup_root": "",
    "log_file": "",
    "default_full_backup": True,
    "device_label_prefix": "iphone",
    "allow_encryption_command": True,
    "libimobiledevice_path": "",
    "compute_backup_sizes": False,
    "cors_origins": [],
}

PUBLIC_KEYS = {
    "setup_complete",
    "host",
    "port",
    "bind_all_interfaces",
    "backup_root",
    "log_file",
    "default_full_backup",
    "device_label_prefix",
    "allow_encryption_command",
    "libimobiledevice_path",
    "compute_backup_sizes",
    "cors_origins",
}

MUTABLE_KEYS = PUBLIC_KEYS | {"api_token"}


def _merge_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(DEFAULTS)
    merged.update(raw)
    return merged


def load_config(*, include_secrets: bool = False) -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = _merge_defaults(raw)
    else:
        cfg = deepcopy(DEFAULTS)

    env_token = os.environ.get("IPHONE_MANAGER_API_TOKEN", "").strip()
    if env_token:
        cfg["api_token"] = env_token

    if os.environ.get("IPHONE_MANAGER_BIND_ALL", "").lower() in ("1", "true", "yes"):
        cfg["bind_all_interfaces"] = True

    env_backup = os.environ.get("IPHONE_MANAGER_BACKUP_ROOT", "").strip()
    if env_backup:
        cfg["backup_root"] = env_backup

    if not include_secrets:
        return public_config(cfg)
    return cfg


def public_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = cfg or load_config(include_secrets=True)
    public = {key: source.get(key, DEFAULTS.get(key)) for key in PUBLIC_KEYS}
    public["api_token_set"] = bool((source.get("api_token") or "").strip())
    public["config_path"] = str(CONFIG_PATH)
    return public


def is_setup_complete(cfg: Optional[Dict[str, Any]] = None) -> bool:
    source = cfg or load_config(include_secrets=True)
    if not source.get("setup_complete"):
        return False
    return bool(str(source.get("backup_root") or "").strip())


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = load_config(include_secrets=True)
    for key, value in updates.items():
        if key in MUTABLE_KEYS:
            current[key] = value

    if "backup_root" in updates and "log_file" not in updates:
        root = str(current["backup_root"]).rstrip("\\/")
        if root:
            current["log_file"] = f"{root}/logs/backup-manager.log"

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return public_config(current)


def resolve_path(path_value: str) -> Path:
    if not str(path_value or "").strip():
        raise ValueError("Path is required")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def get_bind_host(cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or load_config(include_secrets=True)
    env_host = os.environ.get("IPHONE_MANAGER_HOST", "").strip()
    if env_host:
        return env_host
    if cfg.get("bind_all_interfaces"):
        return "0.0.0.0"
    return str(cfg.get("host") or DEFAULTS["host"])


def get_port(cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = cfg or load_config(include_secrets=True)
    env_port = os.environ.get("IPHONE_MANAGER_PORT", "").strip()
    if env_port:
        return int(env_port)
    return int(cfg.get("port") or DEFAULTS["port"])


def get_api_token(cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or load_config(include_secrets=True)
    return str(cfg.get("api_token") or "").strip()


def find_libimobiledevice_path(cfg: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    env_path = os.environ.get("IPHONE_MANAGER_LIB_PATH", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path.resolve()

    cfg = cfg or load_config(include_secrets=True)
    configured = str(cfg.get("libimobiledevice_path") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            return path.resolve()

    for candidate in sorted(PROJECT_ROOT.glob("libimobiledevice*")):
        if not candidate.is_dir():
            continue
        if (candidate / "idevice_id.exe").exists() or (candidate / "idevice_id").exists():
            return candidate.resolve()
    return None


def setup_environment() -> Optional[Path]:
    lib_path = find_libimobiledevice_path()
    if lib_path:
        current = os.environ.get("PATH", "")
        lib_str = str(lib_path)
        if lib_str not in current.split(os.pathsep):
            os.environ["PATH"] = lib_str + os.pathsep + current
    return lib_path


def validate_runtime_config(cfg: Optional[Dict[str, Any]] = None) -> None:
    cfg = cfg or load_config(include_secrets=True)
    bind_host = get_bind_host(cfg)
    token = get_api_token(cfg)
    if bind_host == "0.0.0.0" and not token:
        raise SystemExit(
            "Refusing to listen on 0.0.0.0 without api_token. "
            "Complete setup and provide an API token before exposing the app on your network."
        )


def generate_api_token() -> str:
    return secrets.token_urlsafe(32)
