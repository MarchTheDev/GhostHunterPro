# Ghost Hunter Pro

Ghost Hunter Pro is a Windows-focused desktop tool for finding and cleaning leftover game files.

It supports two main workflows:

- **Home**: search for a specific game by name or Steam AppID and inspect known leftover paths.
- **Library**: scan the PC for known leftover folders tied to AppIDs and browse them in a visual grid.

## Features

- Search a game by **name** or **Steam AppID**
- Search suggestions while typing
- Detect common leftover locations in:
  - AppData (Roaming / Local / LocalLow)
  - Documents / My Games / Public Documents
  - Saved Games / ProgramData / Temp
  - NVIDIA leftover entries
  - Steam userdata / shadercache / workshop / compatdata
  - Crack leftover folders such as:
    - STAR
    - CODEX
    - RUNE
    - OnlineFix
    - EMPRESS
    - GSE Saves
    - SmartSteamEmu
    - Goldberg SteamEmu Saves
    - ALI213
- Library view with:
  - game cards
  - archive / restore
  - per-game modal details
  - delete selected / delete all
- Persistent **Recent Hunts** history
- Persistent **Archive** state
- Open a leftover folder directly in Explorer

## Project structure

```text
ghost_hunter.py                 # thin launcher
build_exe.bat                  # build Windows EXE with PyInstaller
run.bat                        # easy launcher for local testing
requirements.txt               # Python dependency list

ghosthunter_app/
├── __init__.py
├── app.py                     # app startup / pywebview window
├── backend.py                 # JS API exposed to the UI
├── config.py                  # constants, paths, app data locations
├── file_ops.py                # delete/open path logic
├── scanner.py                 # leftover detection logic
├── steam_api.py               # Steam API + caching
├── storage.py                 # state/history persistence + migration
├── utils.py                   # shared helpers
└── ui/
    └── ghost_hunter_ui.html   # desktop web-style UI
```

## Requirements

- Python 3.10+
- Windows recommended
- Dependency:

```bash
pip install pywebview
```

## Running locally

### Option 1: command line

```bash
python ghost_hunter.py
```

### Option 2: Windows batch launcher

Double-click:

- `run.bat`

## Building an EXE for sharing

Use:

- `build_exe.bat`

It will install build dependencies and generate a single-file Windows executable using PyInstaller.

### Manual build command

```bash
python -m pip install pywebview pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "GhostHunterPro" --add-data "ghosthunter_app\ui\ghost_hunter_ui.html;ghosthunter_app\ui" ghost_hunter.py
```

The EXE will be created in:

```text
dist/GhostHunterPro.exe
```

## Sharing with other people

After building, you can share:

- `dist/GhostHunterPro.exe`

Recommended extras to share together:

- a short `README.md`
- a changelog if you want version notes

## Persistence

The app stores its persistent data inside:

```text
%APPDATA%\GhostHunterPro
```

This includes:

- archive state
- recent hunt history
- Steam metadata cache

The refactor also attempts to migrate older cache/state files from the previous flat-file version automatically.

## Safety note

Ghost Hunter Pro tries to protect obvious system-level folders, but you should still verify paths before deleting anything.

## Notes for maintenance

If you need to troubleshoot specific parts:

- **Steam lookups / suggestions** → `ghosthunter_app/steam_api.py`
- **scan logic** → `ghosthunter_app/scanner.py`
- **delete/open path logic** → `ghosthunter_app/file_ops.py`
- **history/archive persistence** → `ghosthunter_app/storage.py`
- **frontend UI** → `ghosthunter_app/ui/ghost_hunter_ui.html`
