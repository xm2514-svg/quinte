"""quinte.py - Point d'entrée du projet QUINTE.

Lance depuis la racine du projet :
    python quinte.py            # Quinté+ d'aujourd'hui
    python quinte.py --demain   # Quinté+ de demain

Structure projet :
    src/      Code Python (parser, algo, scraper, push, run)
    pwa/      Site web installable (index.html + manifest + sw + data/)
    app/      App Kivy + buildozer (APK Android)
    cache/    Données scrapées + logs + JSON intermédiaires
    docs/     Documentation (bilans, procédures)
    tools/    Scripts utilitaires (setup_github, tester_local, ...)
    golden_backup/  Sauvegardes versionnées
"""

import os
import sys
from pathlib import Path

BASE = Path(__file__).parent.resolve()
SRC = BASE / "src"

# Met src/ dans le PYTHONPATH et CWD = BASE pour que tous les chemins relatifs marchent
sys.path.insert(0, str(SRC))
os.chdir(BASE)

if __name__ == "__main__":
    from quinte_x_run import run, afficher_top5, setup_logger
    import argparse, subprocess
    from datetime import date, timedelta

    p = argparse.ArgumentParser()
    p.add_argument("--demain", action="store_true")
    args = p.parse_args()

    target = date.today() + (timedelta(days=1) if args.demain else timedelta(days=0))
    logger = setup_logger(str(target))

    try:
        data = run(args.demain, logger)
        afficher_top5(data)

        # Rendu HTML
        if (SRC / "render_html.py").exists():
            subprocess.run([sys.executable, str(SRC / "render_html.py")], check=False)

        # Push GitHub si configuré
        if (SRC / "push_github.py").exists() and (BASE / ".git").exists():
            subprocess.run([sys.executable, str(SRC / "push_github.py")], check=False)

        sys.exit(0)
    except Exception as e:
        logger.exception(f"ECHEC : {e}")
        sys.exit(2)
