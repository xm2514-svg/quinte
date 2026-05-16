"""quinte.py — Point d'entrée unique. Alias de quinte_x_run.py.
Lance le pipeline complet (scrape + parse + algo + top5) en une commande.

Usage :
    python quinte.py            # Quinté+ d'aujourd'hui
    python quinte.py --demain   # Quinté+ de demain
"""

if __name__ == "__main__":
    from quinte_x_run import run, afficher_top5, setup_logger
    import argparse, sys
    from datetime import date, timedelta

    p = argparse.ArgumentParser()
    p.add_argument("--demain", action="store_true")
    args = p.parse_args()

    target = date.today() + (timedelta(days=1) if args.demain else timedelta(days=0))
    logger = setup_logger(str(target))
    try:
        data = run(args.demain, logger)
        afficher_top5(data)

        # Génère le rendu HTML pour visualisation immédiate
        from pathlib import Path
        import json, subprocess, sys as _sys
        here = Path(__file__).parent
        gen = here / "render_html.py"
        if gen.exists():
            subprocess.run([_sys.executable, str(gen)], check=False)

        # Push automatique sur GitHub (si setup_github.bat a déjà été lancé une fois)
        push = here / "push_github.py"
        if push.exists() and (here / ".git").exists():
            subprocess.run([_sys.executable, str(push)], check=False)

        sys.exit(0)
    except Exception as e:
        logger.exception(f"ÉCHEC : {e}")
        sys.exit(2)
