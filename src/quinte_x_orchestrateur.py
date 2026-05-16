"""
QUINTE-X — Orchestrateur : consolidation des fiches scrapées en JSON enrichi.

Pipeline :
  1. Lit `quinte_du_jour_parsed.json`         (16 chevaux avec données de base)
  2. Lit `urls_fiches_{date}.json`            (URLs + hash des 16 fiches)
  3. Pour chaque cheval, charge `fiches_raw/{slug}_{hash}.txt` si présent
  4. Applique `parse_fiche_cheval` avec le contexte course (terrain + distance)
  5. Fusionne données de base + données enrichies par numéro
  6. Exclut les non-partants (NP) déclarés ailleurs
  7. Écrit `quinte_du_jour_enrichi.json`
  8. Logging : INFO/WARNING/ERROR vers logs/quinte_x_{date}.log + console

Utilisation :
    python quinte_x_orchestrateur.py [--date YYYY-MM-DD]
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from quinte_x_parser_fiche import parse_fiche_cheval


from paths import BASE as HERE, CACHE, FICHES_RAW, LOGS


# ----- logging ----------------------------------------------------------------

def setup_logger(target_date: str) -> logging.Logger:
    logs_dir = LOGS
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"quinte_x_{target_date}.log"

    logger = logging.getLogger("quinte_x")
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


# ----- helpers ---------------------------------------------------------------

def _slug_from_href(href: str) -> str:
    """Retourne 'gabison' depuis '/cheval/gabison/run/abc...' ou '/cheval/gabison/abc...'"""
    parts = [p for p in href.split("/") if p]
    return parts[1] if len(parts) >= 2 and parts[0] == "cheval" else ""


def _hash_from_href(href: str) -> str:
    """Retourne le hash final depuis n'importe lequel des 2 formats."""
    parts = [p for p in href.split("/") if p]
    return parts[-1] if parts else ""


def find_fiche_raw(fiches_raw: Path, slug: str, hash_id: str) -> Path | None:
    """Cherche le fichier brut. Tente {slug}_{hash}.txt puis {slug}.txt en fallback."""
    candidates = [
        fiches_raw / f"{slug}_{hash_id}.txt",
        fiches_raw / f"{slug}.txt",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ----- pipeline ---------------------------------------------------------------

def consolider(target_date: str, logger: logging.Logger) -> dict:
    # Inputs
    base_path = CACHE / "quinte_du_jour_parsed.json"
    urls_path = CACHE / f"urls_fiches_{target_date}.json"
    fiches_raw = FICHES_RAW
    fiches_raw.mkdir(exist_ok=True)

    if not base_path.exists():
        logger.error(f"Input manquant : {base_path.name}")
        sys.exit(1)
    if not urls_path.exists():
        logger.warning(f"URLs manquantes : {urls_path.name} — enrichissement ignoré")

    base = json.loads(base_path.read_text(encoding="utf-8"))
    urls = json.loads(urls_path.read_text(encoding="utf-8")) if urls_path.exists() else {"fiches": []}

    course = base["course"]
    contexte = {
        "terrain": course.get("terrain"),
        "distance_m": course.get("distance_m"),
    }
    logger.info(f"Course : {course.get('reunion')}{course.get('course_num')} "
                f"{course.get('hippodrome')} — {course.get('nom')}")
    logger.info(f"Contexte algo : terrain={contexte['terrain']} | distance={contexte['distance_m']}m")

    # Index URLs par numéro
    url_by_num = {f["numero"]: f for f in urls.get("fiches", [])}

    enriched: list[dict] = []
    nb_enrichis = 0
    nb_no_fiche = 0
    nb_np = 0

    for cheval in base["partants"]:
        n = cheval["numero"]
        nom = cheval.get("nom") or "?"

        # Exclusion non-partants (si flagués dans le JSON de base — sinon laisser passer)
        if cheval.get("non_partant"):
            logger.warning(f"#{n} {nom} → NON-PARTANT, exclu")
            nb_np += 1
            continue

        out = dict(cheval)
        out["fiche_enrichie"] = None

        url_entry = url_by_num.get(n)
        if not url_entry:
            logger.warning(f"#{n} {nom} → pas d'URL fiche dans urls_fiches_{target_date}.json")
        else:
            slug = _slug_from_href(url_entry["href"])
            hash_id = _hash_from_href(url_entry["href"])
            raw = find_fiche_raw(fiches_raw, slug, hash_id)
            if raw:
                try:
                    text = raw.read_text(encoding="utf-8")
                    fiche = parse_fiche_cheval(text, contexte)
                    out["fiche_enrichie"] = fiche
                    nb_enrichis += 1
                    logger.info(f"#{n:>2} {nom:<22} → enrichi depuis {raw.name}")
                except Exception as e:
                    logger.error(f"#{n} {nom} → échec parsing {raw.name} : {e}")
            else:
                nb_no_fiche += 1
                logger.warning(f"#{n:>2} {nom:<22} → fiche brute absente ({slug}_{hash_id}.txt)")

        enriched.append(out)

    result = {
        "date": target_date,
        "course": course,
        "stats_consolidation": {
            "partants_total": len(base["partants"]),
            "enrichis": nb_enrichis,
            "sans_fiche": nb_no_fiche,
            "non_partants_exclus": nb_np,
        },
        "partants": enriched,
    }

    out_path = CACHE / "quinte_du_jour_enrichi.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Consolidation terminée : {nb_enrichis}/{len(base['partants'])} chevaux enrichis")
    logger.info(f"Sortie : {out_path.name}")
    return result


# ----- CLI ---------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()),
                        help="Date YYYY-MM-DD (défaut : aujourd'hui)")
    args = parser.parse_args()

    logger = setup_logger(args.date)
    logger.info(f"=== QUINTE-X Orchestrateur — {args.date} ===")
    try:
        consolider(args.date, logger)
        logger.info("OK")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Échec orchestrateur : {e}")
        sys.exit(2)
