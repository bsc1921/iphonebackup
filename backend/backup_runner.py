import json
import signal
import subprocess
import threading
import queue
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config import load_config, resolve_path


def log_line(message: str) -> None:
    config = load_config(include_secrets=True)
    log_target = str(config.get("log_file") or "").strip()
    if not log_target:
        return
    log_file = resolve_path(log_target)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def get_backup_destination(device_name: str, udid: str) -> Path:
    config = load_config(include_secrets=True)
    backup_root_value = str(config.get("backup_root") or "").strip()
    if not backup_root_value:
        raise RuntimeError("Backup location is not configured. Complete setup first.")
    backup_root = resolve_path(backup_root_value)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in device_name.strip()) or "iphone"
    today = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    destination = backup_root / f"{safe_name}_{udid[:8]}_{today}"
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def find_last_backup(device_name: str, udid: str) -> Optional[Path]:
    """Return the most recent backup folder for this device, or None."""
    config = load_config(include_secrets=True)
    backup_root_value = str(config.get("backup_root") or "").strip()
    if not backup_root_value:
        return None
    backup_root = resolve_path(backup_root_value)
    if not backup_root.exists():
        return None
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in device_name.strip()) or "iphone"
    prefix = f"{safe_name}_{udid[:8]}_"
    matches = sorted(
        [p for p in backup_root.iterdir() if p.is_dir() and p.name.startswith(prefix)],
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    return matches[0] if matches else None


CATEGORY_KEYWORDS = {
    "Photos": [
        "DCIM", "PhotoData", "Media", "photo", "image", "camera",
        ".jpg", ".heic", ".png", ".mov", ".mp4", ".gif", ".jpeg",
        "CameraRollDomain", "MediaDomain", "thumbnails", "burst",
    ],
    "Messages": [
        "sms", "message", "chat", "voicemail", "call_history",
        "3d0d7e5fb2ce288813306e4d4636395e047a3d28",
        "imessage", "facetime", "callhistory", "ChatStorage",
        "com.apple.MobileSMS", "com.apple.facetime",
    ],
    "Apps": [
        "AppDomain", "app-", ".app", "Library/Application",
        "com.apple.AppStore", "iTunesMetadata", "Payload",
        "PluginKitPlugin", "SysContainerDomain", "SysSharedContainerDomain",
    ],
    "Contacts": [
        "AddressBook", "contact", "com.apple.MobileAddressBook",
        "AddressBookImages", "ab.db",
    ],
    "Health": [
        "Health", "pedometer", "workout", "com.apple.health",
        "com.apple.HealthKit", "healthdb", "stepcount",
    ],
    "Notes": [
        "Notes", "com.apple.mobilenotes", "NoteStore",
    ],
    "Calendar": [
        "Calendar", "com.apple.mobilecal", "datebook", "reminder",
        "com.apple.reminders",
    ],
    "Safari": [
        "Safari", "com.apple.mobilesafari", "Bookmarks", "History.db",
        "browser", "TopSites",
    ],
    "Settings": [
        "HomeDomain", "RootDomain", "SystemPreferencesDomain",
        "ManagedPreferencesDomain", "WirelessDomain", "KeychainDomain",
        "preferences", "plist", "com.apple.preferences",
    ],
    "Mail": [
        "Mail", "com.apple.mobilemail", "Envelope Index", "mailboxes",
    ],
}

def classify_line(line: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in line.lower():
                return category
    return "Other"


def _categorize_from_manifest(backup_path: str) -> Optional[Dict]:
    """Read Manifest.db from the backup folder and categorize files by domain."""
    import sqlite3
    import glob

    # Find Manifest.db — it's inside a UDID subfolder
    pattern = os.path.join(backup_path, "*", "Manifest.db")
    matches = glob.glob(pattern)
    if not matches:
        # Try directly in backup_path
        direct = os.path.join(backup_path, "Manifest.db")
        if os.path.exists(direct):
            matches = [direct]
    if not matches:
        return None

    cats = {"Photos": 0, "Messages": 0, "Apps": 0, "Contacts": 0,
            "Health": 0, "Notes": 0, "Calendar": 0, "Safari": 0,
            "Settings": 0, "Mail": 0, "Other": 0}
    try:
        conn = sqlite3.connect(matches[0])
        cur = conn.cursor()
        cur.execute("SELECT domain, relativePath FROM Files")
        for domain, path in cur.fetchall():
            line = f"{domain} {path or ''}"
            cat = classify_line(line)
            cats[cat] = cats.get(cat, 0) + 1
        conn.close()
    except Exception:
        return None
    return cats


def get_backup_file_count(udid: str, destination: str) -> int:
    """Run idevicebackup2 info to get total file count before backup starts."""
    try:
        r = subprocess.run(
            ["idevicebackup2", "-u", udid, "info"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        for line in r.stdout.splitlines():
            # "Number of files: 12345"
            if "Number of files" in line or "Files to backup" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    val = parts[1].strip().replace(",", "")
                    if val.isdigit():
                        return int(val)
    except Exception:
        pass
    return 0


def parse_progress_from_log(line: str) -> Optional[int]:
    """Parse percentage from idevicebackup2 progress bar lines like:
    [====  ] 81% (19.0 MB/23.5 MB)
    """
    match = re.search(r'\]\s+(\d+)%', line)
    if match:
        return min(int(match.group(1)), 99)
    return None


def parse_progress(line: str) -> Optional[int]:
    # "Sending file 45 of 1234" — most accurate, use live total
    match = re.search(r'(\d+)\s+of\s+(\d+)', line)
    if match:
        current = int(match.group(1))
        total   = int(match.group(2))
        if total > 0:
            return min(int((current / total) * 100), 99)
    # Fallback: explicit % in line
    match = re.search(r'(\d+)\s*%', line)
    if match:
        return min(int(match.group(1)), 99)
    return None


def parse_file_counts(line: str):
    """Return (current, total) file counts from a 'X of Y' line, or (None, None)."""
    match = re.search(r'(\d+)\s+of\s+(\d+)', line)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


# ── Backup state ──────────────────────────────────────────────────────────────
_backup_process: Optional[subprocess.Popen] = None
_backup_paused = False
_progress_state = {
    "running": False, "paused": False, "percent": 0, "current_file": "",
    "category": "Other",
    "categories": {"Photos": 0, "Messages": 0, "Apps": 0, "Contacts": 0, "Health": 0, "Notes": 0, "Calendar": 0, "Safari": 0, "Settings": 0, "Mail": 0, "Other": 0},
    "log": [], "done": False, "ok": None, "destination": "", "error": "",
}
_progress_lock = threading.Lock()
_sse_queue: queue.Queue = queue.Queue()


def get_progress_state() -> Dict:
    with _progress_lock:
        return dict(_progress_state)


def stop_backup() -> Dict:
    global _backup_process
    if _backup_process and _backup_process.poll() is None:
        _backup_process.terminate()
        log_line("Backup stopped by user.")
        with _progress_lock:
            _progress_state.update({"running": False, "done": True, "ok": False, "error": "Stopped by user"})
        _sse_queue.put("done")
        return {"ok": True, "message": "Backup stopped."}
    return {"ok": False, "message": "No active backup."}


def pause_backup() -> Dict:
    global _backup_process, _backup_paused
    if os.name == "nt":
        return {"ok": False, "message": "Pause is not supported on Windows."}
    if _backup_process and _backup_process.poll() is None:
        if not _backup_paused:
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SuspendThread(
                    ctypes.windll.kernel32.OpenThread(0x0002, False, _backup_process.pid)
                )
            else:
                _backup_process.send_signal(signal.SIGSTOP)
            _backup_paused = True
            with _progress_lock:
                _progress_state["paused"] = True
            _sse_queue.put("update")
            log_line("Backup paused by user.")
            return {"ok": True, "message": "Backup paused."}
    return {"ok": False, "message": "No active backup."}


def resume_backup() -> Dict:
    global _backup_process, _backup_paused
    if _backup_process and _backup_process.poll() is None and _backup_paused:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.ResumeThread(
                ctypes.windll.kernel32.OpenThread(0x0002, False, _backup_process.pid)
            )
        else:
            _backup_process.send_signal(signal.SIGCONT)
        _backup_paused = False
        with _progress_lock:
            _progress_state["paused"] = False
        _sse_queue.put("update")
        log_line("Backup resumed by user.")
        return {"ok": True, "message": "Backup resumed."}
    return {"ok": False, "message": "No paused backup."}


def _reset_state(destination: str):
    global _backup_paused
    _backup_paused = False
    with _progress_lock:
        _progress_state.update({
            "running": True, "paused": False, "percent": 0, "current_file": "",
            "mode": "Full",
            "category": "Other",
            "files_sent": 0, "total_files": 0,
            "categories": {"Photos": 0, "Messages": 0, "Apps": 0, "Contacts": 0, "Health": 0, "Notes": 0, "Calendar": 0, "Safari": 0, "Settings": 0, "Mail": 0, "Other": 0},
            "log": [], "done": False, "ok": None, "destination": destination, "error": "",
        })


def _update_progress(percent: Optional[int], line: str, category: str, files_sent: int = 0, total_files: int = 0):
    with _progress_lock:
        if percent is not None:
            _progress_state["percent"] = percent
        if files_sent > 0:
            _progress_state["files_sent"] = files_sent
        if total_files > 0:
            _progress_state["total_files"] = total_files
        _progress_state["current_file"] = line[:120]
        _progress_state["category"] = category
        _progress_state["categories"][category] += 1
        _progress_state["log"].append(line[:200])
        if len(_progress_state["log"]) > 200:
            _progress_state["log"] = _progress_state["log"][-200:]
    _sse_queue.put("update")


def run_backup_streaming(udid: str, device_name: str = "iPhone", full: bool = False, network: bool = False):
    global _backup_process

    try:
        last_backup = find_last_backup(device_name, udid)
        is_full = full or (last_backup is None)
        if is_full or last_backup is None:
            destination = get_backup_destination(device_name, udid)
        else:
            destination = last_backup
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    # Auto-detect: full only if no previous backup exists for this device

    _reset_state(str(destination))
    with _progress_lock:
        _progress_state["mode"] = ("WiFi " if network else "") + ("Full" if is_full else "Incremental")

    cmd = ["idevicebackup2"]
    if network:
        cmd.append("-n")
    cmd += ["-u", udid, "backup"]
    if is_full:
        cmd.append("--full")
    cmd.append(str(destination))
    log_line(f"Starting {'full' if is_full else 'incremental'} backup: {' '.join(cmd)}")

    def _run():
        global _backup_process
        try:
            _backup_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            for line in _backup_process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                percent = parse_progress_from_log(line)
                category = classify_line(line)
                sent, total = parse_file_counts(line)
                _update_progress(percent, line, category, files_sent=sent or 0, total_files=total or 0)
                log_line(line)

            _backup_process.wait()
            rc = _backup_process.returncode
            with _progress_lock:
                _progress_state["running"] = False
                _progress_state["done"] = True
                _progress_state["ok"] = rc == 0
                _progress_state["percent"] = 100 if rc == 0 else _progress_state["percent"]
                if rc != 0 and not _progress_state["error"]:
                    _progress_state["error"] = f"Process exited with code {rc}"
            # Categorize from Manifest.db after successful backup
            if rc == 0:
                cats = _categorize_from_manifest(str(destination))
                if cats:
                    with _progress_lock:
                        _progress_state["categories"] = cats
            _sse_queue.put("done")
            log_line(f"Backup finished. Return code: {rc}")
        except FileNotFoundError:
            msg = "idevicebackup2 not found. Install libimobiledevice first."
            with _progress_lock:
                _progress_state.update({"running": False, "done": True, "ok": False, "error": msg})
            _sse_queue.put("done")
            log_line(msg)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "destination": str(destination)}


def run_backup(udid: str, device_name: str = "iPhone", full: bool = False, network: bool = False) -> Dict:
    return run_backup_streaming(udid=udid, device_name=device_name, full=full, network=network)


# ── Restore state ─────────────────────────────────────────────────────────────
_restore_process: Optional[subprocess.Popen] = None
_restore_paused = False
_restore_state = {
    "running": False, "paused": False, "percent": 0, "current_file": "",
    "log": [], "done": False, "ok": None, "error": "", "source": "",
}
_restore_lock = threading.Lock()
_restore_queue: queue.Queue = queue.Queue()


def get_restore_state() -> Dict:
    with _restore_lock:
        return dict(_restore_state)


def stop_restore() -> Dict:
    global _restore_process
    if _restore_process and _restore_process.poll() is None:
        _restore_process.terminate()
        log_line("Restore stopped by user.")
        with _restore_lock:
            _restore_state.update({"running": False, "done": True, "ok": False, "error": "Stopped by user"})
        _restore_queue.put("done")
        return {"ok": True, "message": "Restore stopped."}
    return {"ok": False, "message": "No active restore."}


def pause_restore() -> Dict:
    global _restore_process, _restore_paused
    if os.name == "nt":
        return {"ok": False, "message": "Pause is not supported on Windows."}
    if _restore_process and _restore_process.poll() is None and not _restore_paused:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SuspendThread(
                ctypes.windll.kernel32.OpenThread(0x0002, False, _restore_process.pid)
            )
        else:
            _restore_process.send_signal(signal.SIGSTOP)
        _restore_paused = True
        with _restore_lock:
            _restore_state["paused"] = True
        _restore_queue.put("update")
        log_line("Restore paused by user.")
        return {"ok": True, "message": "Restore paused."}
    return {"ok": False, "message": "No active restore."}


def resume_restore() -> Dict:
    global _restore_process, _restore_paused
    if _restore_process and _restore_process.poll() is None and _restore_paused:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.ResumeThread(
                ctypes.windll.kernel32.OpenThread(0x0002, False, _restore_process.pid)
            )
        else:
            _restore_process.send_signal(signal.SIGCONT)
        _restore_paused = False
        with _restore_lock:
            _restore_state["paused"] = False
        _restore_queue.put("update")
        log_line("Restore resumed by user.")
        return {"ok": True, "message": "Restore resumed."}
    return {"ok": False, "message": "No paused restore."}


def resolve_restore_directory(backup_path: Path) -> Path:
    """Return the directory idevicebackup2 expects for restore."""
    markers = ("Manifest.plist", "Info.plist", "Manifest.db")
    if any((backup_path / marker).exists() for marker in markers):
        return backup_path

    for child in backup_path.iterdir():
        if child.is_dir() and any((child / marker).exists() for marker in markers):
            return child
    return backup_path


def run_restore(udid: str, backup_path: str, password: str = "") -> Dict:
    global _restore_process, _restore_paused
    path = Path(backup_path)
    if not path.exists():
        return {"ok": False, "error": f"Backup path not found: {backup_path}"}

    restore_dir = resolve_restore_directory(path)
    if not any((restore_dir / marker).exists() for marker in ("Manifest.plist", "Info.plist", "Manifest.db")):
        return {"ok": False, "error": f"Backup folder does not look valid: {restore_dir}"}

    _restore_paused = False
    with _restore_lock:
        _restore_state.update({
            "running": True, "paused": False, "percent": 0, "current_file": "",
            "log": [], "done": False, "ok": None, "error": "", "source": str(restore_dir),
        })

    cmd = ["idevicebackup2", "-u", udid, "restore", "--system", "--settings"]
    if password:
        cmd += ["--password", password]
    cmd.append(str(restore_dir))
    log_line(f"Starting restore: {' '.join(cmd)}")

    def _run():
        global _restore_process
        try:
            _restore_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            for line in _restore_process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                percent = parse_progress(line)
                with _restore_lock:
                    if percent is not None:
                        _restore_state["percent"] = percent
                    _restore_state["current_file"] = line[:120]
                    _restore_state["log"].append(line[:200])
                    if len(_restore_state["log"]) > 200:
                        _restore_state["log"] = _restore_state["log"][-200:]
                _restore_queue.put("update")
                log_line(line)

            _restore_process.wait()
            rc = _restore_process.returncode
            with _restore_lock:
                _restore_state["running"] = False
                _restore_state["done"] = True
                _restore_state["ok"] = rc == 0
                _restore_state["percent"] = 100 if rc == 0 else _restore_state["percent"]
                if rc != 0 and not _restore_state["error"]:
                    _restore_state["error"] = f"Process exited with code {rc}"
            _restore_queue.put("done")
            log_line(f"Restore finished. Return code: {rc}")
        except FileNotFoundError:
            msg = "idevicebackup2 not found."
            with _restore_lock:
                _restore_state.update({"running": False, "done": True, "ok": False, "error": msg})
            _restore_queue.put("done")
            log_line(msg)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "source": str(restore_dir)}


def _folder_size_gb(path: Path) -> Optional[float]:
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total / (1024 ** 3), 2)
    except OSError:
        return None


def list_backup_history() -> Dict:
    config = load_config(include_secrets=True)
    backup_root_value = str(config.get("backup_root") or "").strip()
    if not backup_root_value:
        return {"ok": True, "backups": []}
    backup_root = resolve_path(backup_root_value)
    backup_root.mkdir(parents=True, exist_ok=True)
    compute_sizes = bool(config.get("compute_backup_sizes"))
    items = []
    for path in sorted(backup_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        item = {
            "name": path.name,
            "path": str(path),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }
        if compute_sizes:
            item["size_gb"] = _folder_size_gb(path)
        items.append(item)
    return {"ok": True, "backups": items}


def enable_encryption(password: str, udid: Optional[str] = None) -> Dict:
    if not password:
        return {"ok": False, "stderr": "Password is required."}
    cmd = ["idevicebackup2"]
    if udid:
        cmd += ["-u", udid]
    cmd += ["encryption", "on", password]
    log_line("Attempting to enable backup encryption.")
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {"ok": process.returncode == 0, "returncode": process.returncode,
                "stdout": process.stdout, "stderr": process.stderr}
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": "idevicebackup2 not found."}


def get_backup_detail(backup_path: str) -> Dict:
    """Read Manifest.db and Info.plist from a backup folder and return full detail."""
    import sqlite3, glob, plistlib

    if not backup_path or not os.path.exists(backup_path):
        return {"ok": False, "error": "Path not found"}

    result = {
        "ok": True, "path": backup_path,
        "device": {}, "categories": {}, "total_files": 0,
        "files_by_category": {},
    }

    # Read Info.plist for device info
    info_path = os.path.join(backup_path, "Info.plist")
    # Also check inside UDID subfolder
    if not os.path.exists(info_path):
        matches = glob.glob(os.path.join(backup_path, "*", "Info.plist"))
        if matches:
            info_path = matches[0]
    if os.path.exists(info_path):
        try:
            with open(info_path, "rb") as f:
                info = plistlib.load(f)
            result["device"] = {
                "name":        info.get("Device Name", ""),
                "product":     info.get("Product Name", ""),
                "ios_version": info.get("Product Version", ""),
                "serial":      info.get("Serial Number", ""),
                "imei":        info.get("IMEI", ""),
                "backup_date": str(info.get("Last Backup Date", "")),
                "encrypted":   info.get("IsEncrypted", False),
            }
        except Exception:
            pass

    # Read Manifest.db for file breakdown
    manifest = os.path.join(backup_path, "Manifest.db")
    if not os.path.exists(manifest):
        matches = glob.glob(os.path.join(backup_path, "*", "Manifest.db"))
        if matches:
            manifest = matches[0]

    if os.path.exists(manifest):
        try:
            conn = sqlite3.connect(manifest)
            cur = conn.cursor()
            cur.execute("SELECT domain, relativePath, flags, file FROM Files")
            rows = cur.fetchall()
            conn.close()

            cats = {"Photos": [], "Messages": [], "Apps": [], "Contacts": [],
                    "Health": [], "Notes": [], "Calendar": [], "Safari": [],
                    "Settings": [], "Mail": [], "Other": []}

            for domain, path, flags, _ in rows:
                line = f"{domain} {path or ''}"
                cat  = classify_line(line)
                # Only show files (flags=1), not directories (flags=2)
                if flags == 1 and path:
                    cats[cat].append({"domain": domain, "path": path})

            result["total_files"] = sum(len(v) for v in cats.values())
            result["categories"]  = {k: len(v) for k, v in cats.items()}
            # Return first 100 files per category for preview
            result["files_by_category"] = {k: v[:100] for k, v in cats.items() if v}
        except Exception as e:
            result["manifest_error"] = str(e)

    return result

