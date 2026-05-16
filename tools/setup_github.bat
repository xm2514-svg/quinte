@echo off
REM ============================================================
REM QUINTE — Init repo Git local + push initial (avec token securise)
REM A LANCER UNE SEULE FOIS depuis XAVPRO\quinte\
REM
REM Prerequis :
REM   1. Repo "quinte" cree sur github.com/xm2514-svg (public ou prive)
REM   2. .github_token present (lu auto depuis config-sentinel.txt)
REM   3. Git installe + git config user.name / user.email
REM ============================================================

cd /d "%~dp0"
echo Repertoire courant : %CD%

REM 1. Verifie le token
if not exist ".github_token" (
    echo [ERREUR] .github_token manquant. Lance d'abord :
    echo   python -c "from pathlib import Path; import re; t=Path('../../config-sentinel.txt'); s=t.read_text(encoding='utf-16'); m=re.search(r'GitHub token = ([A-Za-z0-9_]+)', s); Path('.github_token').write_text(m.group(1))"
    pause
    exit /b 1
)

REM 2. Init repo si pas deja fait
if not exist ".git" (
    echo [1/4] git init...
    git init
    git branch -M main
) else (
    echo [1/4] Repo Git deja initialise.
)

REM 3. .gitignore (important pour ne JAMAIS commit le token)
echo [2/4] Creation .gitignore...
(
echo .github_token
echo __pycache__/
echo *.pyc
echo .pytest_cache/
echo logs/
echo fiches_raw/
echo fiches_cache/
echo raw_paristurf_*.txt
echo raw_fiche_*.txt
echo golden_backup/
) > .gitignore

REM 4. Premier commit + push (le push_github.py s'occupe du token)
echo [3/4] Premier commit + push (Python gere le token)...
python push_github.py

echo [4/4] Termine.
echo.
echo URL raw du JSON :
echo   https://raw.githubusercontent.com/xm2514-svg/quinte/main/data/quinte_x_top5.json
echo.
echo Pour activer GitHub Pages (HTML accessible via URL) :
echo   1. https://github.com/xm2514-svg/quinte/settings/pages
echo   2. Source : Deploy from a branch
echo   3. Branch : main / (root)
echo   4. Save
echo.
echo Apres 30s ton site sera sur :
echo   https://xm2514-svg.github.io/quinte/
pause
