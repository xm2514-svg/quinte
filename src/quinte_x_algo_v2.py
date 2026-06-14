"""
QUINTE-X — Algorithme de scoring v2 (recalibré + variables enrichies).

Lit `quinte_du_jour_enrichi.json`, calcule un score 0-100 par cheval, sort le top 5.

Formule v2
----------
score = 100 * (
    0.40 * f_cote                # signal marché (le plus prédictif)
  + 0.15 * f_gains               # gains carrière normalisés
  + 0.15 * f_couple_je           # moyenne taux couple jockey + couple entraineur
  + 0.10 * f_hippodrome          # taux de réussite sur l'hippodrome du jour
  + 0.10 * f_preference_terrain  # taux places top3 sur le même terrain
  + 0.05 * f_preference_distance # taux places top3 sur distance ±10%
  + 0.05 * f_recuperation        # confort de récupération (idéal 12-45 jours)
)

Variables manquantes -> sous-score neutre 0.5 (pour ne pas pénaliser arbitrairement).

Fiabilité globale (output uniquement, ne change pas le ranking) :
  - Plat / Trot : 1.00
  - Haies / Steeple : 0.80 (aléa de chute structurel)
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path


from paths import BASE as HERE, CACHE, LOGS


# Pondérations v2
W = {
    "cote":       0.30,
    "gains":      0.15,
    "couple_je":  0.15,
    "hippodrome": 0.15,
    "pref_terrain":  0.15,
    "pref_distance": 0.05,
    "recuperation":  0.05,
}


# ----- logging ----------------------------------------------------------------

def setup_logger(target_date: str) -> logging.Logger:
    logs_dir = LOGS
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"quinte_x_{target_date}.log"

    logger = logging.getLogger("quinte_x_algo")
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


# ----- sous-scores -------------------------------------------------------------

NEUTRAL = 0.5


def f_cote(cote: float | None, sum_inv: float) -> float:
    if not cote or cote <= 0 or sum_inv <= 0:
        return NEUTRAL
    return (1.0 / cote) / sum_inv


def f_gains(g: int | None, max_g: int) -> float:
    if not g or max_g <= 0:
        return NEUTRAL
    return g / max_g


def f_couple_je(fiche: dict) -> float:
    """Moyenne du taux couple jockey + couple entraîneur (0-1)."""
    if not fiche:
        return NEUTRAL
    sc = fiche.get("stats_couples", {}) or {}
    j = sc.get("avec_jockey") or {}
    e = sc.get("avec_entraineur") or {}
    vals = []
    for src in (j, e):
        pct = src.get("pourcentage")
        if pct is not None:
            vals.append(pct / 100.0)
    if not vals:
        return NEUTRAL
    return sum(vals) / len(vals)


def f_hippodrome(fiche: dict) -> float:
    if not fiche:
        return NEUTRAL
    sh = (fiche.get("stats_couples") or {}).get("sur_hippodrome") or {}
    pct = sh.get("pourcentage")
    return (pct / 100.0) if pct is not None else NEUTRAL


def _taux_musique(cheval: dict) -> float | None:
    """Fallback ultime : taux places top3 / courses depuis la musique parsee (top niveau du partant).
    Sert quand la fiche enrichie n'a pas de dernieres_courses exploitables."""
    nb_c = cheval.get("nb_courses_recentes")
    nb_p = cheval.get("nb_places_recentes")
    if nb_c and nb_c > 0 and nb_p is not None:
        return nb_p / nb_c
    return None


def f_preference_terrain(fiche: dict, cheval: dict | None = None) -> float:
    if not fiche:
        # Fallback musique meme sans fiche
        if cheval is not None:
            tm = _taux_musique(cheval)
            if tm is not None:
                return tm
        return NEUTRAL
    pt = (fiche.get("derives") or {}).get("preference_terrain") or {}
    taux = pt.get("taux")
    if taux is not None:
        return taux
    # Fallback musique si dernieres_courses vide
    if cheval is not None:
        tm = _taux_musique(cheval)
        if tm is not None:
            return tm
    return NEUTRAL


def f_preference_distance(fiche: dict, cheval: dict | None = None) -> float:
    if not fiche:
        if cheval is not None:
            tm = _taux_musique(cheval)
            if tm is not None:
                return tm
        return NEUTRAL
    pd = (fiche.get("derives") or {}).get("preference_distance") or {}
    taux = pd.get("taux")
    if taux is not None:
        return taux
    if cheval is not None:
        tm = _taux_musique(cheval)
        if tm is not None:
            return tm
    return NEUTRAL


def f_recuperation(fiche: dict) -> float:
    """Optimal entre 12 et 45 jours. Pénalité si trop court (<10j) ou trop long (>90j)."""
    if not fiche:
        return NEUTRAL
    jours = (fiche.get("derives") or {}).get("jours_depuis_derniere_course")
    if jours is None:
        return NEUTRAL
    if 12 <= jours <= 45:
        return 1.0
    if 8 <= jours < 12 or 45 < jours <= 60:
        return 0.75
    if jours < 8 or 60 < jours <= 90:
        return 0.5
    return 0.3  # > 90 jours = rouille importante


def fiabilite_globale(type_course: str | None) -> float:
    if not type_course:
        return 1.0
    t = type_course.lower()
    if any(k in t for k in ("haies", "steeple", "cross")):
        return 0.80
    return 1.0


# ----- scoring ----------------------------------------------------------------

def score_chevaux(partants: list[dict]) -> list[dict]:
    cotes = [c["cote_pmu"] for c in partants if c.get("cote_pmu")]
    sum_inv = sum(1.0 / c for c in cotes) if cotes else 0.0

    gains = [c["gains_eur"] for c in partants if c.get("gains_eur")]
    max_g = max(gains) if gains else 0

    enriched: list[dict] = []
    for ch in partants:
        fiche = ch.get("fiche_enrichie")
        sub = {
            "cote":          f_cote(ch.get("cote_pmu"), sum_inv),
            "gains":         f_gains(ch.get("gains_eur"), max_g),
            "couple_je":     f_couple_je(fiche),
            "hippodrome":    f_hippodrome(fiche),
            "pref_terrain":  f_preference_terrain(fiche, ch),
            "pref_distance": f_preference_distance(fiche, ch),
            "recuperation":  f_recuperation(fiche),
        }
        score = 100.0 * sum(W[k] * sub[k] for k in W)
        out = dict(ch)
        out["sous_scores"] = {k: round(v, 4) for k, v in sub.items()}
        out["score"] = round(score, 2)
        out["enrichi"] = fiche is not None
        enriched.append(out)

    enriched.sort(key=lambda x: x["score"], reverse=True)
    for rang, ch in enumerate(enriched, start=1):
        ch["rang_predit"] = rang
    return enriched


# ----- pipeline ---------------------------------------------------------------

def run(target_date: str, logger: logging.Logger) -> dict:
    in_path = CACHE / "quinte_du_jour_enrichi.json"
    if not in_path.exists():
        logger.error(f"Input introuvable : {in_path.name}. Lance d'abord quinte_x_orchestrateur.py")
        sys.exit(1)

    data = json.loads(in_path.read_text(encoding="utf-8"))
    course = data["course"]
    fiab = fiabilite_globale(course.get("type"))

    logger.info(f"Algo v2 — {course.get('reunion')}{course.get('course_num')} "
                f"{course.get('hippodrome')} | type={course.get('type')} | fiabilité={fiab}")

    enriched = score_chevaux(data["partants"])

    nb_enrichis = sum(1 for c in enriched if c.get("enrichi"))
    logger.info(f"Score appliqué à {len(enriched)} chevaux ({nb_enrichis} enrichis)")

    result = {
        "date": data.get("date"),
        "course": course,
        "fiabilite_globale": fiab,
        "ponderations": W,
        "top5": enriched[:6],  # 6 chevaux pour champ réduit Xavier
        "tous_chevaux": enriched,
    }
    out_path = CACHE / "quinte_x_top5.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Top 5 écrit : {out_path.name}")
    return result


def afficher(data: dict) -> None:
    c = data["course"]
    print(f"\nCourse   : {c.get('reunion')}{c.get('course_num')} {c.get('hippodrome')} — {c.get('nom')}")
    print(f"Type     : {c.get('type')} | {c.get('distance_m')}m | terrain {c.get('terrain')}")
    print(f"Fiabilité globale (info) : {data['fiabilite_globale']:.0%}")
    print()
    print("TOP 5 PRÉDIT (algo v2) :")
    print(f"{'Rg':>2} {'N°':>3} {'Nom':<22} {'Cote':>5} {'Score':>6} {'Enrichi':>8}")
    print("-" * 65)
    for ch in data["top5"]:
        cote = f"{ch['cote_pmu']}" if ch.get("cote_pmu") else "?"
        enr = "✓" if ch.get("enrichi") else "—"
        print(f"{ch['rang_predit']:>2} {ch['numero']:>3} {(ch['nom'] or '?')[:22]:<22} {cote:>5} {ch['score']:>6} {enr:>8}")
    print()
    print("Détail sous-scores top 5 :")
    print(f"{'N°':>3} {'cote':>5} {'gains':>5} {'J/E':>5} {'hipp':>5} {'terr':>5} {'dist':>5} {'récup':>5}")
    print("-" * 65)
    for ch in data["top5"]:
        s = ch["sous_scores"]
        print(f"{ch['numero']:>3} {s['cote']:>5.2f} {s['gains']:>5.2f} {s['couple_je']:>5.2f} "
              f"{s['hippodrome']:>5.2f} {s['pref_terrain']:>5.2f} {s['pref_distance']:>5.2f} {s['recuperation']:>5.2f}")


# ----- CLI ---------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=str(date.today()))
    args = p.parse_args()

    logger = setup_logger(args.date)
    logger.info(f"=== QUINTE-X Algo v2 — {args.date} ===")
    try:
        data = run(args.date, logger)
        afficher(data)
        logger.info("OK")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Échec algo v2 : {e}")
        sys.exit(2)
