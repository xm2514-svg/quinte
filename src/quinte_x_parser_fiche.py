"""
QUINTE-X — Parser fiche cheval paris-turf.com → dict enrichi.

Entrée  : texte renvoyé par get_page_text sur paris-turf.com/cheval/{slug}/run/{hash}
Sortie  : dict avec carte d'identité, stats couples, perfs globales, dernières courses, et dérivés.

Si un contexte course est fourni (terrain + distance du jour), calcule les préférences :
  - preference_terrain  : taux de réussite sur le terrain du jour
  - preference_distance : taux de réussite sur ±10% de la distance du jour
  - jours_depuis_derniere_course : récupération
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path


RE_NUM_NOM = re.compile(r"^(\d{1,2})\s*-\s*(.+)$")
RE_COURSE_HEADER = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+([A-Z])\s+(.+)$")
RE_COURSE_DETAIL = re.compile(
    r"^(?P<qplus>Q\+|-)\s+(?P<dist>\d{3,4})\s*m\s*-\s*(?P<corde>[GD])\s+(?P<terrain>[A-Za-zÀ-ÿ ]+?)(?:\s+(?P<type>[A-Z]))?(?:\s+-)?\s+(?P<alloc>[\d\s]+)\s*€$"
)
RE_RANG = re.compile(r"^(\d+er|\d+e|TJ|AT|DAI|NP)$")
RE_COUPLE_LINE = re.compile(r"^(\d+)\s+victoire[s]?\s+et\s+(\d+)\s+place[s]?\s+en\s+(\d+)\s+courses?$")
RE_GLOBAL_LINE = re.compile(r"^(\d+)\s+courses?\s+(\d+)\s+victoires?\s+(\d+)\s+places?$")


# ----- helpers ----------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _section(lines: list[str], start_marker: str, end_markers: list[str]) -> list[str]:
    """Retourne les lignes entre start_marker et le premier end_marker rencontré."""
    out: list[str] = []
    i = 0
    while i < len(lines) and start_marker not in lines[i]:
        i += 1
    if i == len(lines):
        return []
    i += 1
    while i < len(lines) and not any(m in lines[i] for m in end_markers):
        out.append(lines[i])
        i += 1
    return out


def _find_after(lines: list[str], marker: str, offset: int = 1) -> str | None:
    """Retourne la ligne `offset` positions après celle contenant marker, ou None."""
    for i, ln in enumerate(lines):
        if marker in ln and i + offset < len(lines):
            return lines[i + offset]
    return None


# ----- extracteurs ------------------------------------------------------------

def parse_titre(lines: list[str]) -> dict:
    """Numéro + nom du cheval (ex: '5 - Gabison')."""
    for ln in lines:
        m = RE_NUM_NOM.match(ln)
        if m and m.group(2)[0].isupper():
            return {"numero": int(m.group(1)), "nom": m.group(2).strip()}
    return {"numero": None, "nom": None}


def parse_carte_identite(lines: list[str]) -> dict:
    """Carte d'identité : Jockey/Entraîneur/Propriétaire/Éleveur + Sexe/Robe/Naissance/Discipline + Père/Mère."""
    out = {"jockey": None, "entraineur": None, "proprietaire": None, "eleveur": None,
           "sexe": None, "robe": None, "naissance": None, "discipline": None,
           "pere": None, "mere": None}
    for i, ln in enumerate(lines):
        if ln == "CARTE D'IDENTITÉ":
            # Les 4 lignes suivantes après les 4 labels (Jockey/Entraîneur/Propriétaire/Éleveur)
            try:
                # Header labels = lines[i+1..i+4]. Values = lines[i+5..i+8]
                out["jockey"] = lines[i + 5]
                out["entraineur"] = lines[i + 6]
                out["proprietaire"] = lines[i + 7]
                out["eleveur"] = lines[i + 8]
                # Sexe/Robe/Naissance/Discipline labels = i+9..i+12, values = i+13..i+16
                out["sexe"] = lines[i + 13]
                out["robe"] = lines[i + 14]
                out["naissance"] = int(lines[i + 15]) if lines[i + 15].isdigit() else lines[i + 15]
                out["discipline"] = lines[i + 16]
                # Père/Mère labels = i+17..i+18, values = i+19..i+20
                out["pere"] = lines[i + 19]
                out["mere"] = lines[i + 20]
            except (IndexError, ValueError):
                pass
            break
    return out


def parse_course_actuelle(lines: list[str]) -> dict:
    """Infos course du jour (déjà connues mais on les recapture pour validation)."""
    out = {"hippodrome": None, "nb_partants": None, "allocation_eur": None,
           "distance_m": None, "vh": None}
    text = "\n".join(lines)
    m = re.search(r"R\d+C\d+([A-ZÉÈ]+)Prix", text)
    if m:
        out["hippodrome"] = m.group(1).title()
    m = re.search(r"(\d+)\s+Partants", text)
    if m:
        out["nb_partants"] = int(m.group(1))
    m = re.search(r"([\d\s]+)\s*€", text)
    if m:
        out["allocation_eur"] = int(m.group(1).replace(" ", ""))
    m = re.search(r"(\d[\d\s]+)\s*m\b", text)
    if m:
        out["distance_m"] = int(m.group(1).replace(" ", ""))
    m = re.search(r"VH\s+(\d{2,3}(?:,\d)?)", text)
    if m:
        out["vh"] = float(m.group(1).replace(",", "."))
    return out


def parse_cote_live(lines: list[str]) -> float | None:
    """Cote PMU live affichée juste avant 'PMU.fr'."""
    for i, ln in enumerate(lines):
        if ln == "PMU.fr" and i > 0:
            prev = lines[i - 1]
            m = re.match(r"^(\d+(?:,\d+)?)$", prev)
            if m:
                return float(m.group(1).replace(",", "."))
    return None


def parse_stats_couple(lines: list[str], marker: str) -> dict | None:
    """Parse un bloc 'Avec ce jockey' / 'Avec cet entraîneur' / 'Sur cet hippodrome'."""
    for i, ln in enumerate(lines):
        if ln == marker:
            # Lignes attendues : marker, NOM, "X victoire(s) et Y place(s) en Z courses", "%pourcentage", "%"
            nom = lines[i + 1] if i + 1 < len(lines) else None
            for j in range(i + 1, min(i + 6, len(lines))):
                m = RE_COUPLE_LINE.match(lines[j])
                if m:
                    pct_line = lines[j + 1] if j + 1 < len(lines) else None
                    pct = None
                    if pct_line and pct_line.replace(".", "").isdigit():
                        pct = float(pct_line)
                    return {
                        "nom": nom,
                        "victoires": int(m.group(1)),
                        "places": int(m.group(2)),
                        "courses": int(m.group(3)),
                        "pourcentage": pct,
                    }
            return None
    return None


def parse_performances_globales(lines: list[str]) -> dict:
    """Section PERFORMANCES : gains, musique, stats carrière."""
    out = {"gains_eur": None, "musique": None, "carriere": None}
    for i, ln in enumerate(lines):
        if ln == "Gains" and i + 1 < len(lines):
            m = re.match(r"^([\d\s]+)\s*€$", lines[i + 1])
            if m:
                out["gains_eur"] = int(m.group(1).replace(" ", ""))
        if ln == "Musique":
            # Lit les lignes suivantes (tokens courts) jusqu'à une ligne longue ou vide
            tokens = []
            for j in range(i + 1, min(i + 15, len(lines))):
                tok = lines[j]
                if RE_GLOBAL_LINE.match(tok):
                    break
                if len(tok) > 8 or " " in tok:
                    break
                tokens.append(tok)
            if tokens:
                out["musique"] = " ".join(tokens)
        m = RE_GLOBAL_LINE.match(ln)
        if m:
            pct_line = lines[i + 1] if i + 1 < len(lines) else None
            pct = float(pct_line) if pct_line and pct_line.replace(".", "").isdigit() else None
            out["carriere"] = {
                "courses": int(m.group(1)),
                "victoires": int(m.group(2)),
                "places": int(m.group(3)),
                "pourcentage": pct,
            }
    return out


def parse_dernieres_courses(lines: list[str]) -> list[dict]:
    """Parse le tableau des dernières courses."""
    courses: list[dict] = []
    i = 0
    while i < len(lines):
        m = RE_COURSE_HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        course = {
            "date": m.group(1),
            "spec": m.group(2),
            "hippodrome": m.group(3).strip(),
            "nom_course": None,
            "qplus": None,
            "distance_m": None,
            "corde": None,
            "terrain": None,
            "allocation_eur": None,
            "rang": None,
            "partants": None,
            "vh": None,
        }
        # Lignes suivantes : nom course, détail, rang, /partants, VH, artif
        # Skip jusqu'à trouver le détail
        for j in range(i + 1, min(i + 8, len(lines))):
            ln = lines[j]
            md = RE_COURSE_DETAIL.match(ln)
            if md:
                course["qplus"] = (md.group("qplus") == "Q+")
                course["distance_m"] = int(md.group("dist"))
                course["corde"] = md.group("corde")
                course["terrain"] = md.group("terrain").strip()
                course["allocation_eur"] = int(md.group("alloc").replace(" ", ""))
                # Nom course = ligne entre header et détail
                if j > i + 1:
                    course["nom_course"] = lines[i + 1]
                # Rang = ligne après détail
                if j + 1 < len(lines):
                    rg = lines[j + 1]
                    if RE_RANG.match(rg):
                        course["rang"] = rg
                # /partants
                if j + 2 < len(lines):
                    part_m = re.match(r"^/\s*(\d+)$", lines[j + 2])
                    if part_m:
                        course["partants"] = int(part_m.group(1))
                # VH
                if j + 3 < len(lines):
                    vh_m = re.match(r"^(\d+(?:[\.,]\d)?)$", lines[j + 3])
                    if vh_m:
                        course["vh"] = float(vh_m.group(1).replace(",", "."))
                i = j + 4
                break
        else:
            i += 1
            continue
        courses.append(course)
    return courses


# ----- dérivés ---------------------------------------------------------------

def _rang_to_int(rang: str | None) -> int | None:
    if not rang:
        return None
    m = re.match(r"^(\d+)", rang)
    return int(m.group(1)) if m else None


def calc_derives(fiche: dict, contexte: dict | None) -> dict:
    """Calcule préférence terrain/distance + jours depuis dernière course.
    Exclut la course du jour de l'historique pour éviter les biais post-course."""
    out = {"preference_terrain": None, "preference_distance": None,
           "jours_depuis_derniere_course": None}
    all_courses = fiche.get("dernieres_courses", [])
    if not all_courses:
        return out

    # Exclure la course du jour si elle est dans l'historique (cas post-course)
    today = date.today()
    today_str = today.strftime("%d/%m/%y")
    courses = [c for c in all_courses if c.get("date") != today_str]
    if not courses:
        return out

    # Jours depuis dernière course (la dernière ANTÉRIEURE au jour)
    try:
        last_dt = datetime.strptime(courses[0]["date"], "%d/%m/%y").date()
        out["jours_depuis_derniere_course"] = (today - last_dt).days
    except (ValueError, KeyError):
        pass

    if not contexte:
        return out

    terrain_jour = contexte.get("terrain")
    distance_jour = contexte.get("distance_m")

    # Préférence terrain (taux placé top 3 sur courses au même terrain)
    if terrain_jour:
        same_terrain = [c for c in courses if c.get("terrain") == terrain_jour]
        if same_terrain:
            placed = sum(1 for c in same_terrain if (_rang_to_int(c.get("rang")) or 99) <= 3)
            out["preference_terrain"] = {
                "courses": len(same_terrain),
                "places_top3": placed,
                "taux": round(placed / len(same_terrain), 3),
            }

    # Préférence distance (±10%)
    if distance_jour:
        delta = distance_jour * 0.10
        same_dist = [c for c in courses if c.get("distance_m") and
                     abs(c["distance_m"] - distance_jour) <= delta]
        if same_dist:
            placed = sum(1 for c in same_dist if (_rang_to_int(c.get("rang")) or 99) <= 3)
            out["preference_distance"] = {
                "courses": len(same_dist),
                "places_top3": placed,
                "taux": round(placed / len(same_dist), 3),
            }

    return out


# ----- API principale ---------------------------------------------------------

def parse_fiche_cheval(text: str, contexte: dict | None = None) -> dict:
    lines = _lines(text)
    fiche = {
        **parse_titre(lines),
        "carte_identite": parse_carte_identite(lines),
        "course_actuelle": parse_course_actuelle(lines),
        "cote_live_fiche": parse_cote_live(lines),
        "stats_couples": {
            "avec_jockey":     parse_stats_couple(lines, "Avec ce jockey"),
            "avec_entraineur": parse_stats_couple(lines, "Avec cet entraîneur"),
            "sur_hippodrome":  parse_stats_couple(lines, "Sur cet hippodrome"),
        },
        "performances_globales": parse_performances_globales(lines),
        "dernieres_courses": parse_dernieres_courses(lines),
    }
    fiche["derives"] = calc_derives(fiche, contexte)
    return fiche


# ----- CLI / test --------------------------------------------------------------

if __name__ == "__main__":
    here = Path(__file__).parent
    raw_path = here / "raw_fiche_gabison_brut_2026-05-16.txt"
    if not raw_path.exists():
        print(f"[ERREUR] Fichier source introuvable : {raw_path}", file=sys.stderr)
        sys.exit(1)

    text = raw_path.read_text(encoding="utf-8")
    contexte = {"terrain": "Lourd", "distance_m": 3600}
    fiche = parse_fiche_cheval(text, contexte)

    out_path = here / "fiche_gabison_parsed.json"
    out_path.write_text(json.dumps(fiche, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Cheval     : #{fiche['numero']} {fiche['nom']}")
    ci = fiche["carte_identite"]
    print(f"Identité   : {ci['sexe']} {ci['robe']}, né {ci['naissance']} | {ci['pere']} x {ci['mere']}")
    print(f"Jockey     : {ci['jockey']}")
    print(f"Entraîneur : {ci['entraineur']}")
    print(f"Cote live  : {fiche['cote_live_fiche']}")
    sc = fiche["stats_couples"]
    if sc["avec_jockey"]:
        print(f"Couple J   : {sc['avec_jockey']['victoires']}V {sc['avec_jockey']['places']}P / {sc['avec_jockey']['courses']}c → {sc['avec_jockey']['pourcentage']}%")
    if sc["avec_entraineur"]:
        print(f"Couple E   : {sc['avec_entraineur']['victoires']}V {sc['avec_entraineur']['places']}P / {sc['avec_entraineur']['courses']}c → {sc['avec_entraineur']['pourcentage']}%")
    if sc["sur_hippodrome"]:
        print(f"Hippodrome : {sc['sur_hippodrome']['victoires']}V {sc['sur_hippodrome']['places']}P / {sc['sur_hippodrome']['courses']}c → {sc['sur_hippodrome']['pourcentage']}%")
    pg = fiche["performances_globales"]
    print(f"Gains      : {pg['gains_eur']} € | Musique : {pg['musique']}")
    if pg["carriere"]:
        print(f"Carrière   : {pg['carriere']['courses']}c {pg['carriere']['victoires']}V {pg['carriere']['places']}P → {pg['carriere']['pourcentage']}%")
    print(f"Dernières  : {len(fiche['dernieres_courses'])} courses parsées")
    for c in fiche["dernieres_courses"]:
        print(f"  {c['date']} {c['hippodrome']:<12} {c['distance_m']}m {c['terrain']:<14} rang {c['rang']}/{c['partants']}")
    d = fiche["derives"]
    print(f"\nDérivés (contexte = {contexte}) :")
    print(f"  Récupération     : {d['jours_depuis_derniere_course']} jours")
    print(f"  Préf terrain     : {d['preference_terrain']}")
    print(f"  Préf distance    : {d['preference_distance']}")
    print(f"\n[OK] JSON écrit : {out_path}")
