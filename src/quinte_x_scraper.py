"""
QUINTE-X — Scraper autonome paris-turf (urllib + BeautifulSoup).

Remplace le scraping manuel via Chrome MCP. Récupère les 14 (ou N) fiches en quelques secondes.

Pipeline :
  1. Lit `urls_fiches_{date}.json` (liste des fiches du Quinté+ du jour)
  2. Pour chaque cheval : HTTP GET + extraction texte façon get_page_text
  3. Sauvegarde dans `fiches_raw/{slug}_{hash}.txt`
  4. Logging dans logs/

Utilisation :
    python quinte_x_scraper.py --date YYYY-MM-DD
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup


HERE = Path(__file__).parent
BASE_URL = "https://www.paris-turf.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


# ----- logging ----------------------------------------------------------------

def setup_logger(target_date: str) -> logging.Logger:
    logs_dir = HERE / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"quinte_x_{target_date}.log"

    logger = logging.getLogger("quinte_x_scraper")
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


# ----- helpers ----------------------------------------------------------------

def fetch_html(url: str, timeout: int = 15) -> str:
    """GET HTTP avec headers humains. Retourne le HTML décodé."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def html_to_text(html: str) -> str:
    """Convertit HTML → texte type get_page_text (lignes propres)."""
    soup = BeautifulSoup(html, "html.parser")
    # Supprime scripts, styles, et menus polluants
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # .get_text avec separator garde la structure ligne par ligne
    text = soup.get_text(separator="\n")
    # Nettoie : compresse multi-newlines et supprime espaces de bord par ligne
    lines = [ln.strip() for ln in text.split("\n")]
    # Compresser les lignes vides consécutives
    out = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
                blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out)


def slug_and_hash(href: str) -> tuple[str, str]:
    """Extrait slug + hash depuis /cheval/{slug}/run/{hash} ou /cheval/{slug}/{hash}."""
    parts = [p for p in href.split("/") if p]
    return parts[1] if len(parts) >= 2 else "", parts[-1] if parts else ""


# ----- pipeline ---------------------------------------------------------------

def scrape_fiches(target_date: str, logger: logging.Logger,
                  delay_s: float = 1.0, max_retries: int = 2) -> dict:
    urls_path = HERE / f"urls_fiches_{target_date}.json"
    if not urls_path.exists():
        logger.error(f"URLs manquantes : {urls_path.name}")
        sys.exit(1)

    urls = json.loads(urls_path.read_text(encoding="utf-8"))
    fiches_dir = HERE / "fiches_raw"
    fiches_dir.mkdir(exist_ok=True)

    n_total = len(urls.get("fiches", []))
    n_ok = 0
    n_skip = 0
    n_err = 0

    logger.info(f"Scraping {n_total} fiches pour la course {urls.get('course','?')}")

    for entry in urls.get("fiches", []):
        num = entry["numero"]
        nom = entry["nom"]
        href = entry["href"]
        slug, hash_id = slug_and_hash(href)
        out_path = fiches_dir / f"{slug}_{hash_id}.txt"

        if out_path.exists():
            logger.info(f"#{num:>2} {nom:<24} → déjà présent ({out_path.name}), skip")
            n_skip += 1
            continue

        url = BASE_URL + href
        for attempt in range(1, max_retries + 1):
            try:
                html = fetch_html(url)
                text = html_to_text(html)
                # Header pour debug / archive
                header = f"URL: {url}\nDate capture: {target_date}\n---\n"
                out_path.write_text(header + text, encoding="utf-8")
                size_kb = out_path.stat().st_size / 1024
                logger.info(f"#{num:>2} {nom:<24} → OK ({size_kb:.0f} KB)")
                n_ok += 1
                time.sleep(delay_s)  # politesse anti-bot
                break
            except urllib.error.HTTPError as e:
                logger.warning(f"#{num} {nom} → HTTP {e.code} (tentative {attempt}/{max_retries})")
                if attempt == max_retries:
                    n_err += 1
                time.sleep(2)
            except Exception as e:
                logger.error(f"#{num} {nom} → erreur {type(e).__name__}: {e} (tentative {attempt})")
                if attempt == max_retries:
                    n_err += 1
                time.sleep(2)

    logger.info(f"Bilan : {n_ok} OK | {n_skip} skip (déjà présents) | {n_err} erreurs sur {n_total}")
    return {"ok": n_ok, "skip": n_skip, "err": n_err, "total": n_total}


# ----- CLI ---------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=str(date.today()))
    p.add_argument("--delay", type=float, default=1.0, help="Délai (s) entre 2 requêtes")
    args = p.parse_args()

    logger = setup_logger(args.date)
    logger.info(f"=== QUINTE-X Scraper — {args.date} ===")
    try:
        scrape_fiches(args.date, logger, delay_s=args.delay)
        logger.info("OK")
    except Exception as e:
        logger.exception(f"Échec scraper : {e}")
        sys.exit(2)
