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
from quinte_x_algo import score_chevaux, fiabilite_globale, W


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



def fetch_quinte_pmu(target_date, logger):
    """Récupère la course Quinté+ + partants directement via l'API PMU (source primaire).
    Retourne le dict `base` au format attendu par le pipeline (compatible parse_paris_turf)."""
    import urllib.request, json as _json, re as _re
    date_pmu = target_date.strftime("%d%m%Y")
    url = f"https://offline.turfinfo.api.pmu.fr/rest/client/61/programme/{date_pmu}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = _json.loads(urllib.request.urlopen(req, timeout=15).read())

    # Trouve la course Quinté+
    quinte_c = None
    reunion_info = None
    for r in data.get("programme", {}).get("reunions", []):
        for c in r.get("courses", []):
            for p in (c.get("paris") or []):
                if "QUINTE_PLUS" in str(p.get("typePari", "")):
                    quinte_c = c
                    reunion_info = r
                    break
            if quinte_c: break
        if quinte_c: break

    if not quinte_c:
        logger.warning("Aucun Quinté+ trouvé dans le programme PMU")
        return {"date": str(target_date), "course": {}, "partants": []}

    reunion_num = reunion_info["numOfficiel"]
    course_num = quinte_c["numOrdre"]
    hippo = reunion_info["hippodrome"]["libelleCourt"].title()

    # Récupère les participants
    url_p = f"https://offline.turfinfo.api.pmu.fr/rest/client/61/programme/{date_pmu}/R{reunion_num}/C{course_num}/participants"
    parts_data = _json.loads(urllib.request.urlopen(urllib.request.Request(url_p, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read())

    def _parse_mus(m):
        if not m: return {}
        perfs = _re.findall(r"(\d|[ATDJ])[a-zA-Z]", m)
        positions = [int(p) for p in perfs if p.isdigit()]
        return {
            "musique_raw": m,
            "nb_courses_recentes": len(perfs),
            "nb_victoires_recentes": positions.count(1),
            "nb_places_recentes": sum(1 for p in positions if p <= 3),
            "derniere_position": positions[0] if positions else None,
            "position_moyenne": round(sum(positions)/len(positions), 2) if positions else None,
        }

    partants = []
    for p in parts_data.get("participants", []):
        np = "NON_PARTANT" in str(p.get("statut", ""))
        cote = None
        for k in ("dernierRapportDirect", "dernierRapportReference"):
            if p.get(k) and p[k].get("rapport"):
                cote = p[k]["rapport"]; break
        gains = p.get("gainsParticipant", {}).get("gainsCarriere", 0) or 0
        gains = gains // 100 if gains else 0  # PMU renvoie en centimes
        musique = p.get("musique") or ""
        cheval = {
            "numero": p.get("numPmu"),
            "nom": (p.get("nom") or "").title() or None,
            "artifice": None,
            "sexe": p.get("sexe"),
            "age": p.get("age"),
            "poids": None,
            "jockey": (p.get("driver") or p.get("nomJockey") or "").title() or None,
            "musique": musique,
            "vh": None,
            "gains_eur": gains,
            "entraineur": (p.get("entraineur") or "").title() or None,
            "cote_pmu": cote,
            "non_partant": np,
        }
        cheval.update(_parse_mus(musique))
        partants.append(cheval)

    # Info course
    heure_ts = quinte_c.get("heureDepart", 0)
    heure_str = None
    if heure_ts:
        import datetime as _dt
        h = _dt.datetime.fromtimestamp(heure_ts/1000, _dt.timezone.utc).astimezone(_dt.timezone(_dt.timedelta(hours=2)))
        heure_str = h.strftime("%Hh%M")

    course = {
        "reunion": f"R{reunion_num}",
        "course_num": f"C{course_num}",
        "hippodrome": hippo,
        "nom": quinte_c.get("libelle"),
        "heure": heure_str,
        "type": quinte_c.get("discipline"),
        "categorie": quinte_c.get("categorieParticularite"),
        "nb_partants": quinte_c.get("nombreDeclaresPartants") or len(partants),
        "allocation_eur": quinte_c.get("montantPrix"),
        "distance_m": quinte_c.get("distance"),
        "corde": quinte_c.get("corde"),
        "terrain": quinte_c.get("penetrometre") or "-",
        "meteo": None,
    }

    logger.info(f"  → API PMU : {len(partants)} partants récupérés ({sum(1 for c in partants if c['non_partant'])} NP)")
    return {"date": str(target_date), "course": course, "partants": partants}


def _cross_check_non_partants_pmu(base, date_str, logger):
    """Croise avec l'API PMU pour flagger les non-partants ratés par paris-turf."""
    import urllib.request, json as _json
    c = base.get("course", {})
    reunion = str(c.get("reunion", "")).replace("R", "")
    course_num = str(c.get("course_num", "")).replace("C", "")
    if not reunion or not course_num:
        return
    y, m, d = date_str.split("-")
    date_pmu = f"{d}{m}{y}"
    url = f"https://offline.turfinfo.api.pmu.fr/rest/client/61/programme/{date_pmu}/R{reunion}/C{course_num}/participants"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = _json.loads(urllib.request.urlopen(req, timeout=10).read())
    np_nums = set()
    for p in data.get("participants", []):
        if "NON_PARTANT" in str(p.get("statut", "")):
            np_nums.add(p.get("numPmu"))
    if np_nums:
        logger.info(f"  → API PMU signale non-partants : {sorted(np_nums)}")
        for ch in base.get("partants", []):
            if ch.get("numero") in np_nums and not ch.get("non_partant"):
                ch["non_partant"] = True
                logger.info(f"    → Fix PMU : #{ch['numero']} {ch.get('nom')} flagge non_partant")


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

        # 2. Récupération partants + course via API PMU (source primaire - fiable)
        logger.info("[2/4] Récupération partants via API PMU...")
        base = fetch_quinte_pmu(target_date, logger)
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

    # Cross-check API PMU pour flagger les non-partants ratés par paris-turf (fallback fiable)
    try:
        _cross_check_non_partants_pmu(base, date_str, logger)
    except Exception as e:
        logger.warning(f"  → Cross-check PMU non-partants echec (non bloquant): {e}")

    # Filtre NP (non-partants)
    partants_actifs = [c for c in base["partants"] if not c.get("non_partant")]
    enriched = score_chevaux(partants_actifs)
    fiab = fiabilite_globale(base["course"].get("type"))

    result = {
        "date": date_str,
        "course": base["course"],
        "fiabilite_globale": fiab,
        "ponderations": W,
        "top5": enriched[:6],  # 6 chevaux champ réduit Xavier
        "tous_chevaux": enriched,
        "nb_enrichis": sum(1 for c in enriched if c.get("fiche_enrichie")),
        "nb_partants": len(partants_actifs),
        "cotes_dispo": sum(1 for c in enriched if c.get("cote_pmu")),
    }
    out_path = CACHE / "quinte_x_top5.json"
    # Anti-écrasement renforcé : ne pas écraser si scraping vide ou partiel (< 80 % des partants attendus)
    nb_expected = base["course"].get("nb_partants") or 0
    if not enriched:
        logger.warning(f"  → Scraping vide (0 chevaux), JSON precedent conserve")
        return result
    if nb_expected and len(enriched) < nb_expected * 0.8:
        logger.warning(f"  → Scraping partiel ({len(enriched)}/{nb_expected}), JSON precedent conserve")
        return result
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
