from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Ghost Hunter Pro"
APP_VERSION = "2.3.4"
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
DOWNLOADS_DIR = Path.home() / "Downloads" / "GhostHunterPro"

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# Update / release configuration
PUBLISHER = "GhostHunterPro"
APP_EXE_NAME = "GhostHunterPro.exe"
INSTALLER_BASENAME = "GhostHunterPro-Setup"
PORTABLE_BASENAME = "GhostHunterPro-Portable"

# Fill these when you publish releases on GitHub.
UPDATE_REPO_OWNER = "MarchTheDev"
UPDATE_REPO_NAME = "GhostHunterPro-GUI"

GITHUB_REPO_URL = (
    f"https://github.com/{UPDATE_REPO_OWNER}/{UPDATE_REPO_NAME}"
    if UPDATE_REPO_OWNER and UPDATE_REPO_NAME else ""
)
UPDATE_CHECK_URL = (
    f"https://api.github.com/repos/{UPDATE_REPO_OWNER}/{UPDATE_REPO_NAME}/releases/latest"
    if UPDATE_REPO_OWNER and UPDATE_REPO_NAME else ""
)

DEFAULT_STATE = {
    "archived_appids": [],
    "search_history": [],
}
