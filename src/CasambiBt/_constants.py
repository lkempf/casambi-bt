import os
from pathlib import Path

BASE_PATH = Path(os.getcwd()) / "casambi-bt-store"
BASE_PATH.mkdir(mode=0o700, exist_ok=True)

DEVICE_NAME = "Casambi BT Python"

CASA_UUID = "0000fe4d-0000-1000-8000-00805f9b34fb"
CASA_AUTH_CHAR_UUID = "c9ffde48-ca5a-0001-ab83-8f519b482f77"
