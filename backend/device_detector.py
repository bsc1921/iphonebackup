import subprocess
from typing import Dict, List


def run_cmd(args: List[str], timeout: int = 20) -> Dict:
    try:
        completed = subprocess.run(
            args, capture_output=True, timeout=timeout, check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.decode("utf-8", errors="replace").strip(),
            "stderr": completed.stderr.decode("utf-8", errors="replace").strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": f"Not found: {args[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": 124, "stdout": "", "stderr": "Timed out"}


def _info(udid: str, key: str, network: bool = False) -> str:
    cmd = ["ideviceinfo"]
    if network:
        cmd.append("-n")
    cmd += ["-u", udid, "-k", key]
    r = run_cmd(cmd, timeout=10)
    return r["stdout"] if r["ok"] else ""


def _info_domain(udid: str, domain: str, key: str, network: bool = False) -> str:
    cmd = ["ideviceinfo"]
    if network:
        cmd.append("-n")
    cmd += ["-u", udid, "-q", domain, "-k", key]
    r = run_cmd(cmd, timeout=10)
    return r["stdout"] if r["ok"] else ""


def check_tools() -> Dict:
    tools = ["idevice_id", "ideviceinfo", "idevicebackup2", "ideviceinstaller",
             "idevicescreenshot", "idevicediagnostics", "idevicesyslog", "idevicepair"]
    return {t: run_cmd([t, "--help"], timeout=8)["returncode"] != 127 for t in tools}


def list_devices(network: bool = False) -> Dict:
    cmd = ["idevice_id", "-n"] if network else ["idevice_id", "-l"]
    result = run_cmd(cmd, timeout=15)
    if not result["ok"] and result["returncode"] == 127:
        return {"ok": False, "devices": [], "error": "idevice_id not found"}

    udids = [l.strip() for l in result["stdout"].splitlines() if l.strip()]
    devices = [get_device_info(udid, network=network) for udid in udids]
    return {"ok": True, "devices": devices, "mode": "wifi" if network else "usb"}


def get_device_info(udid: str, network: bool = False) -> Dict:
    # Basic
    name         = _info(udid, "DeviceName", network)
    product_type = _info(udid, "ProductType", network)
    ios_version  = _info(udid, "ProductVersion", network)
    build        = _info(udid, "BuildVersion", network)
    serial       = _info(udid, "SerialNumber", network)
    model        = _info(udid, "HardwareModel", network)
    color        = _info(udid, "DeviceColor", network)
    capacity_str = _info(udid, "TotalDiskCapacity", network)
    free_str     = _info(udid, "AvailableDiskCapacity", network)
    # Fallback to media domain if main domain returns empty
    if not capacity_str:
        capacity_str = _info_domain(udid, "com.apple.disk_usage", "TotalDiskCapacity", network)
    if not free_str:
        free_str = _info_domain(udid, "com.apple.disk_usage", "AvailableDiskCapacity", network)
    phone_number = _info(udid, "PhoneNumber", network)
    imei         = _info(udid, "InternationalMobileEquipmentIdentity", network)
    wifi_mac     = _info(udid, "WiFiAddress", network)
    bt_mac       = _info(udid, "BluetoothAddress", network)

    # Battery via diagnostics domain
    battery_level    = _info_domain(udid, "com.apple.mobile.battery", "BatteryCurrentCapacity", network)
    battery_charging = _info_domain(udid, "com.apple.mobile.battery", "ExternalChargeCapable", network)

    # Storage in GB
    try:
        total_gb = round(int(capacity_str) / (1024 ** 3), 1)
        free_gb  = round(int(free_str) / (1024 ** 3), 1)
        used_gb  = round(total_gb - free_gb, 1)
    except Exception:
        total_gb = free_gb = used_gb = 0

    # Human-readable model name
    model_name = _product_type_to_name(product_type)

    return {
        "udid": udid,
        "name": name or "iPhone",
        "product_type": product_type,
        "model_name": model_name,
        "ios_version": ios_version,
        "build": build,
        "serial": serial,
        "model": model,
        "color": color,
        "phone_number": phone_number,
        "imei": imei,
        "wifi_mac": wifi_mac,
        "bt_mac": bt_mac,
        "network": network,
        "battery_level": int(battery_level) if battery_level.isdigit() else None,
        "battery_charging": battery_charging.lower() == "true" if battery_charging else False,
        "storage": {
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "used_pct": round((used_gb / total_gb * 100) if total_gb else 0, 1),
        },
    }


def get_pairing_status(udid: str, network: bool = False) -> Dict:
    cmd = ["idevicepair"]
    if network:
        cmd.append("-n")
    cmd += ["-u", udid, "validate"]
    r = run_cmd(cmd, timeout=10)
    return {"ok": r["ok"], "status": r["stdout"] or r["stderr"]}


def _product_type_to_name(pt: str) -> str:
    mapping = {
        "iPhone17,4": "iPhone 16 Plus",    "iPhone17,3": "iPhone 16",
        "iPhone17,2": "iPhone 16 Pro Max",  "iPhone17,1": "iPhone 16 Pro",
        "iPhone16,2": "iPhone 15 Pro Max", "iPhone16,1": "iPhone 15 Pro",
        "iPhone15,5": "iPhone 15 Plus",    "iPhone15,4": "iPhone 15",
        "iPhone15,3": "iPhone 14 Pro Max", "iPhone15,2": "iPhone 14 Pro",
        "iPhone14,8": "iPhone 14 Plus",    "iPhone14,7": "iPhone 14",
        "iPhone14,6": "iPhone SE (3rd gen)","iPhone14,5": "iPhone 13",
        "iPhone14,4": "iPhone 13 mini",    "iPhone14,3": "iPhone 13 Pro Max",
        "iPhone14,2": "iPhone 13 Pro",     "iPhone13,4": "iPhone 12 Pro Max",
        "iPhone13,3": "iPhone 12 Pro",     "iPhone13,2": "iPhone 12",
        "iPhone13,1": "iPhone 12 mini",    "iPhone12,8": "iPhone SE (2nd gen)",
        "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,3": "iPhone 11 Pro",
        "iPhone12,1": "iPhone 11",         "iPhone11,8": "iPhone XR",
        "iPhone11,6": "iPhone XS Max",     "iPhone11,4": "iPhone XS Max",
        "iPhone11,2": "iPhone XS",         "iPhone10,6": "iPhone X",
        "iPhone10,3": "iPhone X",          "iPhone10,2": "iPhone 8 Plus",
        "iPhone10,1": "iPhone 8",          "iPhone9,4": "iPhone 7 Plus",
        "iPhone9,2": "iPhone 7 Plus",      "iPhone9,3": "iPhone 7",
        "iPhone9,1": "iPhone 7",
    }
    return mapping.get(pt, pt)
