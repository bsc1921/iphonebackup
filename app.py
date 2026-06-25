import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", Path.home() / "iphone_backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job store: job_id -> {"status", "output", "error", "started_at", "finished_at"}
jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_command(cmd: list[str], job_id: str) -> None:
    """Run *cmd* in a background thread and record results in *jobs*."""
    with _jobs_lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        with _jobs_lock:
            jobs[job_id]["output"] = result.stdout
            jobs[job_id]["error"] = result.stderr
            jobs[job_id]["returncode"] = result.returncode
            jobs[job_id]["status"] = "success" if result.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        with _jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "Command timed out after 3600 seconds."
    except FileNotFoundError as exc:
        with _jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"Executable not found: {exc}"
    finally:
        with _jobs_lock:
            jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


def _start_job(cmd: list[str], label: str) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "label": label,
            "status": "queued",
            "output": "",
            "error": "",
            "returncode": None,
            "started_at": None,
            "finished_at": None,
        }
    thread = threading.Thread(target=_run_command, args=(cmd, job_id), daemon=True)
    thread.start()
    return job_id


def _list_devices() -> list[dict]:
    """Return a list of connected devices as ``[{"udid": ..., "name": ...}]``."""
    try:
        result = subprocess.run(
            ["idevice_id", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        udids = [u.strip() for u in result.stdout.splitlines() if u.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices = []
    for udid in udids:
        name = _device_name(udid)
        devices.append({"udid": udid, "name": name})
    return devices


def _device_name(udid: str) -> str:
    try:
        result = subprocess.run(
            ["ideviceinfo", "-u", udid, "-k", "DeviceName"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or udid
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return udid


def _device_info(udid: str) -> dict:
    fields = [
        "DeviceName",
        "ProductType",
        "ProductVersion",
        "SerialNumber",
        "UniqueDeviceID",
        "PhoneNumber",
        "ModelNumber",
        "HardwareModel",
        "CPUArchitecture",
        "TotalDiskCapacity",
        "TotalDataCapacity",
        "TotalDataAvailable",
    ]
    info: dict[str, str] = {}
    for field in fields:
        try:
            result = subprocess.run(
                ["ideviceinfo", "-u", udid, "-k", field],
                capture_output=True,
                text=True,
                timeout=10,
            )
            value = result.stdout.strip()
            info[field] = value if result.returncode == 0 else "N/A"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            info[field] = "N/A"
    return info


def _list_backups() -> list[dict]:
    backups = []
    if not BACKUP_DIR.exists():
        return backups
    for entry in sorted(BACKUP_DIR.iterdir()):
        if entry.is_dir():
            mtime = entry.stat().st_mtime
            backups.append(
                {
                    "udid": entry.name,
                    "path": str(entry),
                    "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    ),
                }
            )
    return backups


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    devices = _list_devices()
    backups = _list_backups()
    recent_jobs = sorted(
        jobs.values(),
        key=lambda j: j.get("started_at") or "",
        reverse=True,
    )[:10]
    return render_template(
        "index.html",
        devices=devices,
        backups=backups,
        jobs=recent_jobs,
        backup_dir=str(BACKUP_DIR),
    )


@app.route("/devices")
def devices():
    return jsonify(_list_devices())


@app.route("/device/<udid>")
def device_info(udid: str):
    info = _device_info(udid)
    return render_template("device.html", udid=udid, info=info)


@app.route("/backup", methods=["POST"])
def backup():
    udid = request.form.get("udid", "").strip()
    if not udid:
        return "No device selected.", 400

    dest = str(BACKUP_DIR)
    cmd = ["idevicebackup2", "-u", udid, "backup", "--full", dest]
    job_id = _start_job(cmd, f"Backup {udid[:8]}…")
    return redirect(url_for("job_status", job_id=job_id))


@app.route("/restore", methods=["POST"])
def restore():
    udid = request.form.get("udid", "").strip()
    if not udid:
        return "No device selected.", 400

    backup_path = BACKUP_DIR / udid
    if not backup_path.exists():
        return f"No backup found for device {udid}.", 404

    cmd = ["idevicebackup2", "-u", udid, "restore", "--system", "--settings", str(BACKUP_DIR)]
    job_id = _start_job(cmd, f"Restore {udid[:8]}…")
    return redirect(url_for("job_status", job_id=job_id))


@app.route("/jobs")
def job_list():
    all_jobs = sorted(
        jobs.values(),
        key=lambda j: j.get("started_at") or "",
        reverse=True,
    )
    return render_template("jobs.html", jobs=all_jobs)


@app.route("/jobs/<job_id>")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        return "Job not found.", 404
    return render_template("job.html", job=job)


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
