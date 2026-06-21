@echo off
cd /d "%~dp0"
python -m pip install pywebview pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "GhostHunterPro" --add-data "ghosthunter_app\ui\ghost_hunter_ui.html;ghosthunter_app\ui" ghost_hunter.py
pause
