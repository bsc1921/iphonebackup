import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

from config import setup_environment, find_libimobiledevice_path
from app import main

if __name__ == "__main__":
    lib_path = setup_environment()
    print(f"libimobiledevice path: {lib_path or 'not found'}", flush=True)
    main()
