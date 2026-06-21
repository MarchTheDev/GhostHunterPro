from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Ghost Hunter Pro"
APP_VERSION = "2.3.2"
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("APPDATA", str(BASE_DIR))) / "GhostHunterPro"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / "ghosthunter_state.json"
STEAM_CACHE_FILE = DATA_DIR / "ghosthunter_appcache.json"
LOG_FILE = DATA_DIR / "ghosthunter_debug.log"

LEGACY_STATE_FILE = Path.home() / ".ghost_hunter_state.json"
LEGACY_STEAM_CACHE_FILE = Path.home() / ".ghost_hunter_steam_cache.json"

UI_PATH = BASE_DIR / "ghosthunter_app" / "ui" / "ghost_hunter_ui.html"

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

DEFAULT_STATE = {
    "archived_appids": [],
    "search_history": [],
}
