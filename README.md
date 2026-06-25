# iPhone Backup Manager

A local web application for backing up, restoring, and inspecting iPhones using [`libimobiledevice`](https://libimobiledevice.org/) and `idevicebackup2`.

---

## Features

- 📋 **Dashboard** — see all connected devices and existing backups at a glance.
- 💾 **Backup** — start a full backup of any connected iPhone with one click.
- ♻️ **Restore** — restore a device from an existing backup.
- 🔍 **Device Info** — view detailed hardware and software information for any connected device.
- 📊 **Job tracking** — every backup/restore operation runs in the background; watch live status and full output logs.

---

## Prerequisites

Install `libimobiledevice` (provides `idevice_id`, `ideviceinfo`, `idevicebackup2`):

```bash
# macOS (Homebrew)
brew install libimobiledevice

# Ubuntu / Debian
sudo apt install libimobiledevice-utils
```

Python 3.10+ is required.

---

## Installation

```bash
git clone https://github.com/bsc1921/iphonebackup.git
cd iphonebackup
pip install -r requirements.txt
```

---

## Running

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

Connect your iPhone via USB and tap **Trust** when prompted. The device will appear on the dashboard.

### Environment variables

| Variable     | Default                    | Description                              |
|-------------|----------------------------|------------------------------------------|
| `BACKUP_DIR` | `~/iphone_backups`         | Directory where backups are stored       |

```bash
BACKUP_DIR=/Volumes/Backup/iphone python app.py
```

---

## Development

### Running tests

```bash
pip install -r requirements.txt pytest
python -m pytest test_app.py -v
```

---

## Project structure

```
iphonebackup/
├── app.py              # Flask application
├── requirements.txt    # Python dependencies
├── test_app.py         # Unit & integration tests
├── templates/
│   ├── base.html
│   ├── index.html      # Dashboard
│   ├── device.html     # Device info page
│   ├── job.html        # Single job status
│   └── jobs.html       # All jobs list
└── static/
    └── css/
        └── style.css
```
