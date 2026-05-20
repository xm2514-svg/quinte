"""
QUINTE-X — Programme MAÎTRE entièrement automatique.

Un seul lancement = tout le pipeline :
  1. Récupère la page Quinté+ du jour (Playwright)
  2. Parse partants + cotes PMU via API
  3. Récupère les URLs fiches pré-course
  4. Scrape les N fiches en parallèle (rendu JS)
  5. Parse chaque fiche → variables enrichies
  6. Applique l'algo v2 → top 5
  7. Écrit `quinte_x_top5.json` (lu par l'APK Kivy)
  8. Logging complet dans logs/

Utilisation :
    python quinte_x_run.py                    # Quinté+ d'aujourd'hui
    python quinte_x_run.py --demain           # Quinté+ de demain (pré-course, sans cotes)

Tâche planifiée Windows (chaque jour 9h) :
    schtasks /Create /SC DAILY /TN QUINTE-X /TR "python C:\path\quinte_x_run.py" /ST 09:00
"""

import argparse
import json
import logging
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
    _PARIS_TZ = ZoneInfo("Europe/Paris")
except Exception:
    _PARIS_TZ = timezone(timedelta(hours=2))  # fallback CEST

from playwright.sync_api import sync_playwright

# Modules QUINTE-X locaux
from quinte_x_parser import parse_paris_turf
from quinte_x_parser_fiche import parse_fiche_cheval
from quinte_x_algo_v2 import score_chevaux, fiabilite_globale, W


from paths import BASE as HERE, CACHE, FICHES_RAW, LOGS
BASE_URL = "https://www.paris-turf.com"


# ----- logging ----------------------------------------------------------------

def setup_logger(target_date: str) -> logging.Logger:
    logs_dir = LOGS
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"quinte_x_{target_date}.log"

    logger = logging.getLogger("quinte_x_run")
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


# ----- étape 1 : page Quinté+ -------------------------------------------------

def fetch_quinte_page(page, demain: bool) -> tuple[str, list[dict]]:
    """Charge /quinte/aujourdhui ou /quinte/demain, retourne (texte, urls fiches)."""
    path = "/quinte/demain" if demain else "/quinte/aujourdhui"
    page.goto(BASE_URL + path, timeout=25000, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    text = page.inner_text("body")
    # Récupère les hrefs des fiches
    hrefs = page.eval_on_selector_all(
        'a[href*="/cheval/"]',
        "els => els.map(e => e.getAttribute('href'))"
    )
    # Garde les fiches /run/ (pré-course) si présentes, sinon /cheval/{slug}/{hash}
    runs = [h for h in hrefs if "/run/" in h]
    if runs:
        fiches_urls = runs
    else:
        fiches_urls = [h for h in hrefs if re.match(r"^/cheval/[^/]+/[0-9a-f]+$", h)]
    return text, fiches_urls


# ----- étape 2 : cotes PMU via API -------------------------------------------

def fetch_cotes_pmu(target_date: date, logger: logging.Logger) -> tuple[dict[int, float], str | None]:
    """Cherche la course Quinté+ du jour sur l'API PMU.
    Retourne ({numero: cote}, heure_paris_str ou None)."""
    date_str = target_date.strftime("%d%m%Y")
    url = f"https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{date_str}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        # Cherche la course Quinté+
        for reunion in data.get("programme", {}).get("reunions", []):
            for course in reunion.get("courses", []):
                if course.get("paris", []) and any(p.get("typePari") == "QUINTE_PLUS" for p in course.get("paris", [])):
                    rn = reunion.get("numOfficiel") or course.get("numReunion")
                    cn = course.get("numOrdre") or course.get("numExterne")
                    # Heure de départ (timestamp ms UTC) → heure Paris
                    heure_paris = None
                    ts = course.get("heureDepart")
                    if ts:
                        try:
                            utc_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            heure_paris = utc_dt.astimezone(_PARIS_TZ).strftime("%Hh%M")
                        except Exception as e:
                            logger.warning(f"Conv heureDepart échec : {e}")
                    parts_url = f"https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{date_str}/R{rn}/C{cn}/participants"
                    req2 = urllib.request.Request(parts_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                    with urllib.request.urlopen(req2, timeout=15) as r2:
                        pdata = json.loads(r2.read())
                    cotes = {}
                    for p in pdata.get("participants", []):
                        num = p.get("numPmu")
                        rap = p.get("dernierRapportDirect") or p.get("dernierRapportReference")
                        c = rap.get("rapport") if rap else None
                        if num and c:
                            cotes[num] = c
                    logger.info(f"API PMU : {len(cotes)} cotes récupérées sur R{rn}C{cn} — départ {heure_paris or '?'}")
                    return cotes, heure_paris
        logger.warning("API PMU : aucune course Quinté+ trouvée")
        return {}, None
    except Exception as e:
        logger.warning(f"API PMU échec : {e} (algo tournera avec cote neutre)")
        return {}, None


# ----- étape 3 : scraping fiches ----------------------------------------------

def scrape_fiche(page, url: str, wait_ms: int = 1200) -> str:
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    page.wait_for_timeout(wait_ms)
    return page.inner_text("body")


def slug_and_hash(href: str) -> tuple[str, str]:
    parts = [p for p in href.split("/") if p and p != "run"]
    return parts[1] if len(parts) >= 2 else "", parts[-1] if parts else ""


# ----- main -------------------------------------------------------------------

def run(demain: bool, logger: logging.Logger) -> dict:
    target_date = date.today() + (timedelta(days=1) if demain else timedelta(days=0))
    date_str = str(target_date)
    fiches_dir = FICHES_RAW
    fiches_dir.mkdir(exist_ok=True)

    logger.info(f"=== QUINTE-X RUN — {date_str} ({'demain' if demain else 'aujourd hui'}) ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            locale="fr-FR",
        )
        page = ctx.new_page()

        # 1. Quinté+ du jour
        logger.info("[1/4] Récupération page Quinté+...")
        quinte_text, fiches_urls = fetch_quinte_page(page, demain)
        (CACHE / f"raw_paristurf_{date_str}.txt").write_text(quinte_text, encoding="utf-8")
        logger.info(f"  → {len(fiches_urls)} URLs fiches détectées")

        # 2. Parse Quinté+
        logger.info("[2/4] Parsing Quinté+...")
        base = parse_paris_turf(quinte_text)
        base["date"] = date_str
        nb_partants = len(base["partants"])
        logger.info(f"  → {nb_partants} chevaux, course : {base['course'].get('reunion')}{base['course'].get('course_num')} "
                    f"{base['course'].get('hippodrome')} — {base['course'].get('nom')}")

        # 2b. Cotes PMU + heure départ via API
        cotes_pmu, heure_pmu = fetch_cotes_pmu(target_date, logger)
        if cotes_pmu:
            for ch in base["partants"]:
                if not ch.get("cote_pmu") and ch["numero"] in cotes_pmu:
                    ch["cote_pmu"] = cotes_pmu[ch["numero"]]
        # L'heure de l'API PMU fait autorité (paris-turf scrape donne parfois UTC)
        if heure_pmu:
            base["course"]["heure"] = heure_pmu

        # 3. Scraping fiches
        logger.info("[3/4] Scraping fiches chevaux...")
        contexte = {"terrain": base["course"].get("terrain"), "distance_m": base["course"].get("distance_m")}
        for href in fiches_urls:
            slug, hash_id = slug_and_hash(href)
            out_path = fiches_dir / f"{slug}_{hash_id}.txt"
            if out_path.exists() and "Avec ce jockey" in out_path.read_text(encoding="utf-8"):
                logger.info(f"  cache : {slug}")
                continue
            try:
                text = scrape_fiche(page, BASE_URL + href)
                out_path.write_text(f"URL: {BASE_URL+href}\n---\n{text}", encoding="utf-8")
                logger.info(f"  scrapé : {slug}")
            except Exception as e:
                logger.error(f"  échec {slug} : {e}")

        browser.close()

    # 4. Consolidation + algo
    logger.info("[4/4] Consolidation + scoring...")
    for ch in base["partants"]:
        # Cherche le .txt
        for href in fiches_urls:
            if ch["nom"] and ch["nom"].lower().replace("'", "").replace(" ", "-") in href.lower():
                slug, hash_id = slug_and_hash(href)
                p_ = fiches_dir / f"{slug}_{hash_id}.txt"
                if p_.exists():
                    try:
                        ch["fiche_enrichie"] = parse_fiche_cheval(p_.read_text(encoding="utf-8"), contexte)
                    except Exception as e:
                        logger.error(f"Parse fiche {slug} : {e}")
                break

    # Filtre NP (non-partants)
    partants_actifs = [c for c in base["partants"] if not c.get("non_partant")]
    enriched = score_chevaux(partants_actifs)
    fiab = fiabilite_globale(base["course"].get("type"))

    result = {
        "date": date_str,
        "course": base["course"],
        "fiabilite_globale": fiab,
        "ponderations": W,
        "top5": enriched[:5],
        "tous_chevaux": enriched,
        "nb_enrichis": sum(1 for c in enriched if c.get("fiche_enrichie")),
        "nb_partants": len(partants_actifs),
        "cotes_dispo": sum(1 for c in enriched if c.get("cote_pmu")),
    }
    out_path = CACHE / "quinte_x_top5.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  → Top 5 écrit : {out_path.name}")
    logger.info(f"  → Enrichis : {result['nb_enrichis']}/{result['nb_partants']} | Cotes : {result['cotes_dispo']}/{result['nb_partants']}")

    return result


def afficher_top5(data: dict) -> None:
    c = data["course"]
    print(f"\n=== QUINTE-X — {data['date']} ===")
    print(f"{c.get('reunion')}{c.get('course_num')} {c.get('hippodrome')} — {c.get('nom')}")
    print(f"{c.get('type')} | {c.get('distance_m')}m | terrain {c.get('terrain')} | {data['nb_partants']} partants")
    print(f"Fiabilité {data['fiabilite_globale']:.0%} · Enrichis {data['nb_enrichis']}/{data['nb_partants']} · Cotes {data['cotes_dispo']}/{data['nb_partants']}\n")
    print(f"{'Rg':>2} {'N°':>3} {'Nom':<22} {'Cote':>5} {'Score':>6}")
    print("-" * 50)
    for ch in data["top5"]:
        cote = f"{ch.get('cote_pmu')}" if ch.get('cote_pmu') else "—"
        print(f"{ch['rang_predit']:>2} {ch['numero']:>3} {(ch.get('nom') or '?')[:22]:<22} {cote:>5} {ch['score']:>6}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--demain", action="store_true", help="Quinté+ de demain au lieu d'aujourd'hui")
    args = p.parse_args()

    target = date.today() + (timedelta(days=1) if args.demain else timedelta(days=0))
    logger = setup_logger(str(target))
    try:
        data = run(args.demain, logger)
        afficher_top5(data)
        logger.info("=== TERMINÉ AVEC SUCCÈS ===")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"ÉCHEC : {e}")
        sys.exit(2)
