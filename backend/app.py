import json
import os
import secrets
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from flask_cors import CORS

from config import (
    PROJECT_ROOT,
    load_config,
    public_config,
    save_config,
    get_bind_host,
    get_port,
    get_api_token,
    setup_environment,
    validate_runtime_config,
    find_libimobiledevice_path,
    is_setup_complete,
    generate_api_token,
)
from setup_validator import validate_setup
from device_detector import check_tools, list_devices, get_device_info, get_pairing_status
from backup_runner import (
    run_backup, enable_encryption, list_backup_history, get_backup_detail,
    get_progress_state, _sse_queue,
    stop_backup, pause_backup, resume_backup,
    run_restore, get_restore_state, _restore_queue,
    stop_restore, pause_restore, resume_restore,
)
from app_manager import list_apps, install_app, uninstall_app
from screen_mirror import start_mirror, stop_mirror, get_mirror_state
from diagnostics import get_battery_health, get_crash_reports, restart_device, shutdown_device, get_sleep_log
from afc_browser import afc_list, afc_info, afc_mkdir, afc_remove
from developer_mode import get_developer_mode, enable_developer_mode, disable_developer_mode, mount_developer_image, list_mounted_images
from location_spoof import set_location, stop_location, get_location_state
from syslog_stream import start_syslog, stop_syslog, get_syslog_state, syslog_generator

setup_environment()

UI_DIR = PROJECT_ROOT / "ui"

app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="")
app.config["JSON_AS_ASCII"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

cfg = load_config(include_secrets=True)
cors_origins = cfg.get("cors_origins") or []
if cors_origins:
    CORS(app, origins=cors_origins, supports_credentials=False)


def _extract_api_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    header_token = request.headers.get("X-API-Key", "").strip()
    if header_token:
        return header_token
    if request.path.endswith("/stream"):
        return request.args.get("api_key", "").strip()
    return ""


def _is_local_request() -> bool:
    return request.remote_addr in ("127.0.0.1", "::1")


def _auth_required() -> bool:
    if not request.path.startswith("/api/"):
        return False
    if request.path in ("/api/health", "/api/setup/status"):
        return False
    if request.path.startswith("/api/setup/"):
        return False
    return True


def _setup_required() -> bool:
    if not request.path.startswith("/api/"):
        return False
    if request.path in ("/api/health", "/api/setup/status"):
        return False
    if request.path.startswith("/api/setup/"):
        return False
    return not is_setup_complete()


@app.before_request
def enforce_setup_complete():
    if not _setup_required():
        return None
    return jsonify({
        "ok": False,
        "error": "Setup required",
        "setup_required": True,
    }), 503


@app.before_request
def enforce_api_auth():
    if not _auth_required():
        return None

    expected = get_api_token()
    if not expected:
        if _is_local_request():
            return None
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    provided = _extract_api_token()
    if not provided or not secrets.compare_digest(provided, expected):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return None


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/api/health")
def health():
    cfg = load_config(include_secrets=True)
    cfg_public = public_config(cfg)
    lib_path = find_libimobiledevice_path(cfg)
    return jsonify({
        "ok": True,
        "setup_complete": is_setup_complete(cfg),
        "tools": check_tools(),
        "config": cfg_public,
        "libimobiledevice_path": str(lib_path) if lib_path else None,
        "bind_host": get_bind_host(cfg),
        "port": get_port(cfg),
    })


@app.route("/api/setup/status")
def setup_status():
    cfg = load_config(include_secrets=True)
    return jsonify({
        "ok": True,
        "setup_complete": is_setup_complete(cfg),
        "config": public_config(cfg),
        "detected_libimobiledevice_path": str(find_libimobiledevice_path(cfg) or ""),
    })


@app.route("/api/setup/validate", methods=["POST"])
def setup_validate_route():
    payload = request.get_json(force=True)
    result = validate_setup(payload)
    return jsonify(result), 200 if result["ok"] else 400


@app.route("/api/setup/complete", methods=["POST"])
def setup_complete_route():
    payload = request.get_json(force=True)
    result = validate_setup(payload)
    if not result["ok"]:
        return jsonify(result), 400

    backup_check = next(item for item in result["checks"] if item["name"] == "backup_root")
    lib_check = next(item for item in result["checks"] if item["name"] == "libimobiledevice")

    updates = {
        "setup_complete": True,
        "backup_root": payload.get("backup_root", "").strip(),
        "log_file": backup_check.get("log_file", ""),
        "libimobiledevice_path": payload.get("libimobiledevice_path", "").strip(),
        "host": payload.get("host", "127.0.0.1"),
        "port": int(payload.get("port") or 5055),
        "bind_all_interfaces": bool(payload.get("bind_all_interfaces")),
        "compute_backup_sizes": bool(payload.get("compute_backup_sizes")),
    }

    token = str(payload.get("api_token") or "").strip()
    if token:
        updates["api_token"] = token
    elif updates["bind_all_interfaces"]:
        updates["api_token"] = generate_api_token()

    saved = save_config(updates)
    setup_environment()
    response = {
        "ok": True,
        "config": saved,
        "checks": result["checks"],
        "restart_required": updates["bind_all_interfaces"] or updates.get("port") != get_port(),
    }
    if updates["bind_all_interfaces"] and token == "" and updates.get("api_token"):
        response["generated_api_token"] = updates["api_token"]
    return jsonify(response)


@app.route("/api/config", methods=["GET"])
def get_config_route():
    return jsonify(public_config())


@app.route("/api/config", methods=["POST"])
def save_config_route():
    payload = request.get_json(force=True)
    allowed = {
        "backup_root", "log_file", "default_full_backup", "host", "port",
        "bind_all_interfaces", "libimobiledevice_path", "compute_backup_sizes",
        "cors_origins", "api_token", "setup_complete",
    }
    updates = {key: payload[key] for key in allowed if key in payload}
    if not updates:
        return jsonify({"ok": False, "error": "No valid settings provided"}), 400

    if "backup_root" in updates:
        backup_check = validate_setup({
            **updates,
            "bind_all_interfaces": updates.get("bind_all_interfaces", False),
            "api_token": updates.get("api_token", get_api_token()),
        })
        backup_result = next((item for item in backup_check["checks"] if item["name"] == "backup_root"), None)
        if not backup_result or not backup_result["ok"]:
            message = backup_result["message"] if backup_result else "Invalid backup location"
            return jsonify({"ok": False, "error": message, "checks": backup_check["checks"]}), 400
        updates["log_file"] = backup_result.get("log_file", updates.get("log_file", ""))

    merged = {**load_config(include_secrets=True), **updates}
    if merged.get("bind_all_interfaces") and not (merged.get("api_token") or "").strip():
        return jsonify({
            "ok": False,
            "error": "Set api_token before enabling bind_all_interfaces.",
        }), 400

    saved = save_config(updates)
    setup_environment()
    return jsonify({"ok": True, "config": saved})


@app.route("/api/devices")
def devices():
    return jsonify(list_devices())


@app.route("/api/devices/wifi")
def devices_wifi():
    return jsonify(list_devices(network=True))


@app.route("/api/devices/<udid>")
def device_detail(udid):
    network = request.args.get("network", "false").lower() == "true"
    return jsonify(get_device_info(udid, network=network))


@app.route("/api/devices/<udid>/pair")
def device_pair(udid):
    network = request.args.get("network", "false").lower() == "true"
    return jsonify(get_pairing_status(udid, network=network))


@app.route("/api/backup", methods=["POST"])
def backup():
    payload = request.get_json(force=True)
    udid = payload.get("udid")
    if not udid:
        return jsonify({"ok": False, "error": "Missing udid"}), 400
    full = bool(payload.get("full", False))
    incremental = bool(payload.get("incremental", False))
    network = bool(payload.get("wifi", False))
    if incremental:
        full = False
    return jsonify(run_backup(
        udid=udid,
        device_name=payload.get("device_name", "iPhone"),
        full=full,
        network=network,
    ))


@app.route("/api/backup/progress")
def backup_progress():
    return jsonify(get_progress_state())


@app.route("/api/backup/stream")
def backup_stream():
    def generate():
        timeout = 3600
        start = time.time()
        while time.time() - start < timeout:
            try:
                _sse_queue.get(timeout=10)
            except Exception:
                yield "data: {\"heartbeat\": true}\n\n"
                continue
            state = get_progress_state()
            yield f"data: {json.dumps(state)}\n\n"
            if state.get("done"):
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "close"},
    )


@app.route("/api/backup/stop", methods=["POST"])
def backup_stop():
    return jsonify(stop_backup())


@app.route("/api/backup/pause", methods=["POST"])
def backup_pause():
    return jsonify(pause_backup())


@app.route("/api/backup/resume", methods=["POST"])
def backup_resume():
    return jsonify(resume_backup())


@app.route("/api/restore", methods=["POST"])
def restore():
    payload = request.get_json(force=True)
    udid = payload.get("udid")
    backup_path = payload.get("backup_path")
    if not udid or not backup_path:
        return jsonify({"ok": False, "error": "Missing udid or backup_path"}), 400
    return jsonify(run_restore(udid=udid, backup_path=backup_path, password=payload.get("password", "")))


@app.route("/api/restore/progress")
def restore_progress():
    return jsonify(get_restore_state())


@app.route("/api/restore/stream")
def restore_stream():
    def generate():
        timeout = 3600
        start = time.time()
        while time.time() - start < timeout:
            try:
                _restore_queue.get(timeout=10)
            except Exception:
                yield "data: {\"heartbeat\": true}\n\n"
                continue
            state = get_restore_state()
            yield f"data: {json.dumps(state)}\n\n"
            if state.get("done"):
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "close"},
    )


@app.route("/api/restore/stop", methods=["POST"])
def restore_stop():
    return jsonify(stop_restore())


@app.route("/api/restore/pause", methods=["POST"])
def restore_pause():
    return jsonify(pause_restore())


@app.route("/api/restore/resume", methods=["POST"])
def restore_resume():
    return jsonify(resume_restore())


@app.route("/api/backups")
def backups():
    return jsonify(list_backup_history())


@app.route("/api/backups/detail")
def backup_detail():
    path = request.args.get("path", "")
    return jsonify(get_backup_detail(path))


@app.route("/api/encryption", methods=["POST"])
def encryption():
    payload = request.get_json(force=True)
    cfg = load_config(include_secrets=True)
    if not cfg.get("allow_encryption_command", True):
        return jsonify({"ok": False, "error": "Encryption command disabled in config."}), 403
    result = enable_encryption(password=payload.get("password"), udid=payload.get("udid"))
    return jsonify(result), 200 if result["ok"] else 500


@app.route("/api/apps/<udid>")
def apps(udid):
    return jsonify(list_apps(udid))


@app.route("/api/apps/<udid>/uninstall", methods=["POST"])
def app_uninstall(udid):
    payload = request.get_json(force=True)
    return jsonify(uninstall_app(udid, payload.get("bundle_id", "")))


@app.route("/api/apps/<udid>/install", methods=["POST"])
def app_install(udid):
    payload = request.get_json(force=True)
    return jsonify(install_app(udid, payload.get("ipa_path", "")))


@app.route("/api/mirror/<udid>/start", methods=["POST"])
def mirror_start(udid):
    return jsonify(start_mirror(udid))


@app.route("/api/mirror/stop", methods=["POST"])
def mirror_stop():
    return jsonify(stop_mirror())


@app.route("/api/mirror/stream")
def mirror_stream():
    def generate():
        timeout = 3600
        start = time.time()
        while get_mirror_state()["active"] and time.time() - start < timeout:
            state = get_mirror_state()
            yield f"data: {json.dumps({'frame': state['frame'], 'fps': state['fps'], 'error': state['error']})}\n\n"
            time.sleep(0.2)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "close"},
    )


@app.route("/api/diagnostics/<udid>/battery")
def diag_battery(udid):
    return jsonify(get_battery_health(udid))


@app.route("/api/diagnostics/<udid>/crashes")
def diag_crashes(udid):
    return jsonify(get_crash_reports(udid))


@app.route("/api/diagnostics/<udid>/sleep")
def diag_sleep(udid):
    return jsonify(get_sleep_log(udid))


@app.route("/api/diagnostics/<udid>/restart", methods=["POST"])
def diag_restart(udid):
    return jsonify(restart_device(udid))


@app.route("/api/diagnostics/<udid>/shutdown", methods=["POST"])
def diag_shutdown(udid):
    return jsonify(shutdown_device(udid))


@app.route("/api/afc/<udid>/list")
def afc_list_route(udid):
    path = request.args.get("path", "/")
    return jsonify(afc_list(udid, path))


@app.route("/api/afc/<udid>/info")
def afc_info_route(udid):
    path = request.args.get("path", "/")
    return jsonify(afc_info(udid, path))


@app.route("/api/afc/<udid>/mkdir", methods=["POST"])
def afc_mkdir_route(udid):
    payload = request.get_json(force=True)
    return jsonify(afc_mkdir(udid, payload.get("path", "")))


@app.route("/api/afc/<udid>/remove", methods=["POST"])
def afc_remove_route(udid):
    payload = request.get_json(force=True)
    return jsonify(afc_remove(udid, payload.get("path", "")))


@app.route("/api/developer/<udid>/status")
def dev_status(udid):
    return jsonify(get_developer_mode(udid))


@app.route("/api/developer/<udid>/enable", methods=["POST"])
def dev_enable(udid):
    return jsonify(enable_developer_mode(udid))


@app.route("/api/developer/<udid>/disable", methods=["POST"])
def dev_disable(udid):
    return jsonify(disable_developer_mode(udid))


@app.route("/api/developer/<udid>/mount", methods=["POST"])
def dev_mount(udid):
    return jsonify(mount_developer_image(udid))


@app.route("/api/developer/<udid>/images")
def dev_images(udid):
    return jsonify(list_mounted_images(udid))


@app.route("/api/location/<udid>/set", methods=["POST"])
def location_set(udid):
    payload = request.get_json(force=True)
    return jsonify(set_location(udid, float(payload.get("lat", 0)), float(payload.get("lon", 0))))


@app.route("/api/location/<udid>/stop", methods=["POST"])
def location_stop(udid):
    return jsonify(stop_location(udid))


@app.route("/api/location/state")
def location_state():
    return jsonify(get_location_state())


@app.route("/api/syslog/<udid>/start", methods=["POST"])
def syslog_start(udid):
    return jsonify(start_syslog(udid))


@app.route("/api/syslog/stop", methods=["POST"])
def syslog_stop():
    return jsonify(stop_syslog())


@app.route("/api/syslog/stream")
def syslog_stream_route():
    def generate():
        for line in syslog_generator():
            if line is None:
                yield "data: {\"heartbeat\": true}\n\n"
            else:
                yield f"data: {json.dumps({'line': line})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def create_app():
    return app


def main():
    validate_runtime_config()
    host = get_bind_host(load_config(include_secrets=True))
    port = get_port(load_config(include_secrets=True))
    from waitress import serve

    print(f"Starting iPhone Backup Manager on http://{host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
