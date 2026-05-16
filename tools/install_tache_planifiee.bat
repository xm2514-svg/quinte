@echo off
set BASE=%~dp0\..
set SCRIPT=%BASE%\quinte.py
schtasks /Delete /TN "QUINTE" /F >nul 2>&1
schtasks /Create /TN "QUINTE" /SC DAILY /ST 09:00 /TR "python \"%SCRIPT%\"" /F
if %ERRORLEVEL% EQU 0 (
  echo OK - tache QUINTE planifiee chaque jour a 9h00.
  echo Pour lancer maintenant : schtasks /Run /TN QUINTE
) else (
  echo ECHEC - lance ce .bat en mode Administrateur.
)
pause
