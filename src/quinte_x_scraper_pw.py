"""
QUINTE-X — Scraper Playwright (avec rendu JS).

Remplace `quinte_x_scraper.py` (urllib) pour les pages nécessitant JS — typiquement
les fiches `/cheval/{slug}/run/{hash}` qui chargent stats couples + historique courses en JS.

Pipeline :
  1. Lit `urls_fiches_{date}.json`
  2. Lance Chromium headless une fois, charge les N fiches en réutilisant le contexte
  3. Pour chaque cheval : page.inner_text("body") = équivalent de get_page_text
  4. Sauvegarde dans `fiches_raw/{slug}_{hash}.txt`

Utilisation :
    python quinte_x_scraper_pw.py --date YYYY-MM-DD [--wait 2000]
"""

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright


HERE = Path(__file__).parent
BASE_URL = "https://www.paris-turf.com"


def setup_logger(target_date: str) -> logging.Logger:
    logs_dir = HERE / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"quinte_x_{target_date}.log"

    logger = logging.getLogger("quinte_x_scraper_pw")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def slug_and_hash(href: str) -> tuple[str, str]:
    parts = [p for p in href.split("/") if p]
    return parts[1] if len(parts) >= 2 else "", parts[-1] if parts else ""


def scrape_all(target_date: str, logger: logging.Logger,
               wait_ms: int = 2000, force: bool = False) -> dict:
    urls_path = HERE / f"urls_fiches_{target_date}.json"
    if not urls_path.exists():
        logger.error(f"URLs manquantes : {urls_path.name}")
        sys.exit(1)

    urls = json.loads(urls_path.read_text(encoding="utf-8"))
    fiches_dir = HERE / "fiches_raw"
    fiches_dir.mkdir(exist_ok=True)

    n_total = len(urls.get("fiches", []))
    n_ok = n_skip = n_err = 0

    logger.info(f"Scraping Playwright : {n_total} fiches pour {urls.get('course','?')}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            locale="fr-FR",
        )
        page = context.new_page()

        for entry in urls.get("fiches", []):
            num = entry["numero"]
            nom = entry["nom"]
            href = entry["href"]
            slug, hash_id = slug_and_hash(href)
            out_path = fiches_dir / f"{slug}_{hash_id}.txt"

            if out_path.exists() and not force:
                # Vérifier la qualité : si la fiche existante n'a pas "Avec ce jockey", on la rescrape
                if "Avec ce jockey" in out_path.read_text(encoding="utf-8"):
                    logger.info(f"#{num:>2} {nom:<24} → déjà OK, skip")
                    n_skip += 1
                    continue

            url = BASE_URL + href
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(wait_ms)
                text = page.inner_text("body")
                header = f"URL: {url}\nDate capture: {target_date}\n---\n"
                out_path.write_text(header + text, encoding="utf-8")
                size_kb = out_path.stat().st_size / 1024
                logger.info(f"#{num:>2} {nom:<24} → OK ({size_kb:.0f} KB)")
                n_ok += 1
            except Exception as e:
                logger.error(f"#{num} {nom} → {type(e).__name__}: {e}")
                n_err += 1

        browser.close()

    logger.info(f"Bilan : {n_ok} OK | {n_skip} skip | {n_err} erreurs")
    return {"ok": n_ok, "skip": n_skip, "err": n_err}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=str(date.today()))
    p.add_argument("--wait", type=int, default=2000, help="Wait ms après chargement")
    p.add_argument("--force", action="store_true", help="Rescraper même si fiche existe")
    args = p.parse_args()

    logger = setup_logger(args.date)
    logger.info(f"=== QUINTE-X Scraper Playwright — {args.date} ===")
    try:
        scrape_all(args.date, logger, wait_ms=args.wait, force=args.force)
    except Exception as e:
        logger.exception(f"Échec : {e}")
        sys.exit(2)
