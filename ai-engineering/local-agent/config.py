import os
import json

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".aied-agent")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "vps_url": "http://77.237.239.69:8001",
    "ws_url": "ws://77.237.239.69:8001/ws/agent",
    "token": "",
    "user_id": "",
    "project_folder": "",
}


def ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load():
    ensure_dir()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            merged = {**DEFAULTS, **cfg}
            return merged
    return dict(DEFAULTS)


def save(cfg: dict):
    ensure_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def set_token(token: str):
    cfg = load()
    cfg["token"] = token
    save(cfg)


def set_project_folder(folder: str):
    cfg = load()
    cfg["project_folder"] = folder
    save(cfg)
