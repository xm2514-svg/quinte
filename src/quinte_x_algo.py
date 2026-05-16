"""
QUINTE-X — Algorithme de scoring.

Lit `quinte_du_jour_parsed.json` (sortie du parser), calcule un score 0-100 par cheval
selon la pondération validée, et écrit `quinte_x_top5.json`.

Formule
-------
score = 100 * (
    0.35 * f_cote        # probabilité implicite du marché PMU
  + 0.25 * f_gains       # gains carrière normalisés
  + 0.20 * f_ej_proxy    # proxy musique (nb victoires/places récentes)
  + 0.10 * f_poids       # moins lourd = mieux
  + 0.10 * f_partants    # modulateur confiance selon N partants
)

f_cote(c)     = (1/c) / sum(1/c_i)        # probabilité implicite normalisée
f_gains(g)    = g / max(g_i)              # 0-1
f_ej_proxy(m) = (3*nb_victoires + nb_places) / (3 * max(nb_courses, 1))  # 0-1
f_poids(p)    = 1 - (p - min_p) / (max_p - min_p)  # 0-1, ou 0.5 si tous égaux
f_partants(N) = 1.0 si N<=12, 0.9 si N<=16, 0.8 sinon  # appliqué à tous identique
"""

import json
import sys
from pathlib import Path


W_COTE     = 0.35
W_GAINS    = 0.25
W_EJ       = 0.20
W_POIDS    = 0.10
W_PARTANTS = 0.10


def f_cote(c: float | None, sum_inv: float) -> float:
    if not c or c <= 0 or sum_inv <= 0:
        return 0.0
    return (1.0 / c) / sum_inv


def f_gains(g: int | None, max_g: int) -> float:
    if not g or max_g <= 0:
        return 0.0
    return g / max_g


def f_ej_proxy(ch: dict) -> float:
    nb_v = ch.get("nb_victoires_recentes") or 0
    nb_p = ch.get("nb_places_recentes") or 0
    nb_c = ch.get("nb_courses_recentes") or 0
    if nb_c == 0:
        return 0.0
    return (3 * nb_v + nb_p) / (3 * nb_c)


def f_poids(p: float | None, min_p: float, max_p: float) -> float:
    if p is None or max_p == min_p:
        return 0.5
    return 1.0 - (p - min_p) / (max_p - min_p)


def f_partants(n: int) -> float:
    if n <= 12:
        return 1.0
    if n <= 16:
        return 0.9
    return 0.8


def score_all(partants: list[dict], nb_partants: int) -> list[dict]:
    """Calcule le score 0-100 de chaque cheval et retourne la liste enrichie + triée."""
    cotes = [ch["cote_pmu"] for ch in partants if ch.get("cote_pmu")]
    sum_inv = sum(1.0 / c for c in cotes) if cotes else 0.0

    gains = [ch["gains_eur"] for ch in partants if ch.get("gains_eur")]
    max_g = max(gains) if gains else 0

    poids = [ch["poids"] for ch in partants if ch.get("poids") is not None]
    min_p, max_p = (min(poids), max(poids)) if poids else (0.0, 0.0)

    f_part = f_partants(nb_partants)

    enriched: list[dict] = []
    for ch in partants:
        s_cote  = f_cote(ch.get("cote_pmu"), sum_inv)
        s_gains = f_gains(ch.get("gains_eur"), max_g)
        s_ej    = f_ej_proxy(ch)
        s_poids = f_poids(ch.get("poids"), min_p, max_p)

        score = 100.0 * (
            W_COTE     * s_cote
            + W_GAINS  * s_gains
            + W_EJ     * s_ej
            + W_POIDS  * s_poids
            + W_PARTANTS * f_part
        )

        ch_out = dict(ch)
        ch_out["sous_scores"] = {
            "cote":     round(s_cote, 4),
            "gains":    round(s_gains, 4),
            "ej_proxy": round(s_ej, 4),
            "poids":    round(s_poids, 4),
            "partants": round(f_part, 4),
        }
        ch_out["score"] = round(score, 2)
        enriched.append(ch_out)

    enriched.sort(key=lambda x: x["score"], reverse=True)
    for rang, ch in enumerate(enriched, start=1):
        ch["rang_predit"] = rang
    return enriched


def run(input_path: Path, output_path: Path) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    course = data["course"]
    n = course.get("nb_partants") or len(data["partants"])

    enriched = score_all(data["partants"], n)

    result = {
        "date": data.get("date"),
        "course": course,
        "top5": enriched[:5],
        "tous_chevaux": enriched,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


# ----- CLI ---------------------------------------------------------------------

if __name__ == "__main__":
    here = Path(__file__).parent
    in_path = here / "quinte_du_jour_parsed.json"
    out_path = here / "quinte_x_top5.json"

    if not in_path.exists():
        print(f"[ERREUR] Input introuvable : {in_path}", file=sys.stderr)
        sys.exit(1)

    data = run(in_path, out_path)

    c = data["course"]
    print(f"Course   : {c['reunion']}{c['course_num']} {c['hippodrome']} — {c['nom']}")
    print(f"          {c['type']} | {c['distance_m']}m | {c['terrain']} | {c['nb_partants']} partants")
    print()
    print("TOP 5 PRÉDIT :")
    print(f"{'Rg':>2} {'N°':>3} {'Nom':<22} {'Cote':>5} {'Score':>6} {'Détail (cote/gains/ej/poids)':<35}")
    for ch in data["top5"]:
        sub = ch["sous_scores"]
        detail = f"{sub['cote']:.2f}/{sub['gains']:.2f}/{sub['ej_proxy']:.2f}/{sub['poids']:.2f}"
        cote = f"{ch['cote_pmu']}" if ch.get('cote_pmu') else "?"
        print(f"{ch['rang_predit']:>2} {ch['numero']:>3} {(ch['nom'] or '?')[:22]:<22} {cote:>5} {ch['score']:>6} {detail:<35}")

    print()
    print("CLASSEMENT COMPLET :")
    for ch in data["tous_chevaux"]:
        cote = f"{ch['cote_pmu']}" if ch.get('cote_pmu') else "?"
        print(f"  {ch['rang_predit']:>2}. #{ch['numero']:>2} {(ch['nom'] or '?'):<22} cote={cote:>5}  score={ch['score']:>6}")

    print(f"\n[OK] JSON écrit : {out_path}")
