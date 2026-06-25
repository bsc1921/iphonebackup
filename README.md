# iPhone Backup Manager

Local web app for iPhone backup, restore, and device tools using `libimobiledevice` and `idevicebackup2`.

## Deploy to another machine

From the staging folder, run:

```powershell
.\deploy.ps1 -TargetPath "D:\Apps\iPhoneManager"
```

Optional flags:

```powershell
.\deploy.ps1 `
  -TargetPath "D:\Apps\iPhoneManager" `
  -ConfigDir "D:\Data\iPhoneManager\config" `
  -InstallService `
  -Clean
```

What `deploy.ps1` does:

1. Copies the app bundle to the target folder
2. Writes `environment.ps1` with `IPHONE_MANAGER_CONFIG_DIR`
3. Seeds `%ConfigDir%\config.json` from `config.example.json` if missing
4. Creates a Python virtual environment in the target
5. Creates `Start-iPhoneManager.bat` for the deployed machine
6. Optionally installs the Windows service

After deployment:

```text
D:\Apps\iPhoneManager\Start-iPhoneManager.bat
```

Then open `http://127.0.0.1:5055` and complete the setup wizard.

## Staging vs deployment

The project folder is intended to be a **portable staging bundle**. When you deploy to another machine:

1. Copy the app folder to the target PC or server
2. Start the app
3. Complete the **first-run setup wizard**
4. Provide the backup path, tool path, and network settings for that machine

Nothing machine-specific should be committed into the repo. Runtime settings are stored in a local config file outside git.

## Config file location

Priority order:

1. `IPHONE_MANAGER_CONFIG` — full path to `config.json`
2. `IPHONE_MANAGER_CONFIG_DIR` — directory containing `config.json`
3. `backend/config.json` — default for local development

The Windows service installer stores config here:

```text
%APPDATA%\iPhoneManager\config.json
```

That keeps staging/deployment files separate from live machine settings.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_service.py
```

Or from the project root:

```bash
start.bat
```

Open:

```text
http://127.0.0.1:5055
```

On first launch, the setup wizard will ask you to:

- Choose a backup location
- Test that the folder is writable
- Confirm `libimobiledevice` tools are available
- Optionally configure network access and an API token

## Environment overrides

| Variable | Purpose |
|----------|---------|
| `IPHONE_MANAGER_CONFIG` | Full path to config file |
| `IPHONE_MANAGER_CONFIG_DIR` | Directory for config file |
| `IPHONE_MANAGER_BACKUP_ROOT` | Override backup path |
| `IPHONE_MANAGER_LIB_PATH` | Override tools folder |
| `IPHONE_MANAGER_HOST` | Bind address |
| `IPHONE_MANAGER_PORT` | HTTP port |
| `IPHONE_MANAGER_API_TOKEN` | API token |
| `IPHONE_MANAGER_BIND_ALL=1` | Listen on all interfaces |

## Security defaults

- Binds to `127.0.0.1` until setup enables network access
- Refuses `0.0.0.0` without an API token
- Setup validates backup/log paths before saving
- API routes require `X-API-Key` when a token is configured

Generate a token manually:

```bash
cd backend
python generate_token.py
```

## Windows service

Run as Administrator:

```powershell
.\install_service.ps1
```

The service uses:

- `backend/run_service.py`
- `%APPDATA%\iPhoneManager\config.json`
- Auto-detected `libimobiledevice*` folder in the project directory

## Project layout

```text
iphone-backup-manager-mvp/
  backend/
    app.py
    config.py
    setup_validator.py
    config.example.json
    run_service.py
  ui/
  logs/
  backups/
```

## Notes

- Uses Apple's official local backup service
- Restore is destructive
- Pause/resume is disabled on Windows
