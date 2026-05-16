@echo off
cd /d "%~dp0\..\pwa"
echo Serveur PWA local sur http://localhost:8765
echo (CTRL+C pour arreter)
start "" cmd /c "python -m http.server 8765"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8765/"
pause
