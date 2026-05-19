"""
QUINTE-X — Parser texte paris-turf.com → JSON structuré.

Entrée  : texte renvoyé par get_page_text sur paris-turf.com/quinte/aujourdhui
Sortie  : dict / JSON avec course + partants enrichis.

Toutes les infos utiles à l'algo de scoring sont conservées :
  - numero, nom, sexe, age, poids
  - artifice (oeillères/coquilles si '-')
  - jockey, entraineur
  - musique (perfs codées) + dérivés : derniere_position, nb_victoires_recentes, regularite
  - VH (valeur handicap), gains carrière, cote PMU
  - infos course : hippodrome, distance, terrain, nb_partants, allocation, type, météo
"""

import json
import re
import sys
from datetime import date
from pathlib import Path


# ----- regex partagées ---------------------------------------------------------

RE_SA_POIDS = re.compile(r"^([HFM])(\d{1,2})\s+(?:\d{1,2}\s+)?(\d{2,4}(?:,\d)?)$")
# Pattern galop : musique + VH + gains + entraîneur
RE_PERF_GALOP = re.compile(
    r"^(?P<musique>\S+)\s+"
    r"(?P<vh>\d{2,3}(?:,\d)?)\s+"
    r"(?P<gains>\d[\d ]*?)\s*€\s+"
    r"(?P<entraineur>.+)$"
)
# Pattern trot : musique + gains + entraîneur (pas de VH)
RE_PERF_TROT = re.compile(
    r"^(?P<musique>\S+)\s+"
    r"(?P<gains>\d[\d ]*?)\s*€\s+"
    r"(?P<entraineur>.+)$"
)
RE_PERF_LINE = RE_PERF_GALOP  # compat
RE_NUM_ONLY = re.compile(r"^\d{1,2}$")
RE_COTE = re.compile(r"^\d+(?:,\d+)?$")


# ----- extraction infos course -------------------------------------------------

def parse_course_info(text: str) -> dict:
    # Limite la recherche à la zone après le titre "QUINTÉ+" (évite le bandeau d'autres courses)
    qmark = text.find("LE QUINTÉ+")
    if qmark > 0:
        text = text[qmark:]
    """Extrait les infos de la course (réunion, hippodrome, distance, terrain...)."""
    info = {
        "reunion": None,
        "course_num": None,
        "hippodrome": None,
        "nom": None,
        "heure": None,
        "type": None,
        "categorie": None,
        "nb_partants": None,
        "allocation_eur": None,
        "distance_m": None,
        "corde": None,
        "terrain": None,
        "meteo": None,
    }

    # Heure (ex: "15h15")
    m = re.search(r"\b(\d{1,2})h(\d{2})\b", text)
    if m:
        info["heure"] = f"{m.group(1).zfill(2)}:{m.group(2)}"

    # R1 / C4
    m = re.search(r"\bR(\d)\b", text)
    if m:
        info["reunion"] = f"R{m.group(1)}"
    m = re.search(r"\bC(\d)\b", text)
    if m:
        info["course_num"] = f"C{m.group(1)}"

    # Hippodrome via breadcrumb "R1 Auteuil"
    m = re.search(r"\bR\d\s+([A-Za-zÀ-ÿ\-' ]+?)\s*\n\s*>", text)
    if m:
        info["hippodrome"] = m.group(1).strip()
    # Nom via breadcrumb "C4 Prix «...»"
    m = re.search(r"\bC\d\s+(Prix\s+«[^\n]+)", text)
    if m:
        info["nom"] = m.group(1).strip()

    # Type + catégorie : "Haies - L. (Listed Races) - Listed Race - ..."
    m = re.search(r"(Haies|Plat|Trot attelé|Trot monté|Trot|Steeple-chase|Steeple|Cross-country|Cross)\s*-\s*([^\n]+)", text)
    if m:
        info["type"] = m.group(1).strip()
        info["categorie"] = m.group(2).strip()

    # Partants + allocation : "16 partants | 98 000 €"
    m = re.search(r"(\d+)\s+partants\s*\|\s*([\d\s]+)\s*€", text)
    if m:
        info["nb_partants"] = int(m.group(1))
        info["allocation_eur"] = int(m.group(2).replace(" ", ""))

    # Distance + corde : "3600m (5) | Corde à gauche"
    m = re.search(r"(\d{3,4})m.*?Corde à (\w+)", text)
    if m:
        info["distance_m"] = int(m.group(1))
        info["corde"] = m.group(2)

    # Terrain
    m = re.search(r"Terrain\s*:\s*([^\n]+)", text)
    if m:
        info["terrain"] = m.group(1).strip()

    # Météo : "13 °C Nuageux / 20km/h - O"
    m = re.search(r"(\-?\d+)\s*°C\s+([^\n/]+)/\s*(\d+km/h\s*-\s*\w+)", text)
    if m:
        info["meteo"] = f"{m.group(1)}°C {m.group(2).strip()}, vent {m.group(3).strip()}"

    return info


# ----- extraction partants -----------------------------------------------------

def _clean_lines(text: str) -> list[str]:
    """Garde uniquement les lignes non vides après la section PARTANTS."""
    # Coupe avant la section partants (skip header)
    start = text.find("PARTANTS")
    if start == -1:
        return []
    sub = text[start:]
    # Coupe à la fin (section pronostics / pied de page)
    end_markers = ["PRONOSTICS", "Voir légende", "NOS PRÉFÉRÉS"]
    for marker in end_markers:
        idx = sub.find(marker)
        if idx != -1:
            sub = sub[:idx]
            break
    return [ln.strip() for ln in sub.splitlines() if ln.strip()]


def _split_blocks(lines: list[str]) -> list[list[str]]:
    """Découpe par ancre = ligne SA+Poids (qui n'apparaît qu'une fois par cheval).
    On remonte ensuite jusqu'au numéro le plus proche pour démarrer le bloc."""
    sa_positions = [i for i, ln in enumerate(lines) if RE_SA_POIDS.match(ln)]
    if not sa_positions:
        return []

    blocks: list[list[str]] = []
    for k, pos in enumerate(sa_positions):
        # Début du bloc = numéro juste avant SA+Poids (max 4 lignes en arrière)
        start = pos
        for j in range(pos - 1, max(-1, pos - 5), -1):
            if RE_NUM_ONLY.match(lines[j]):
                start = j
                break
        # Fin = juste avant le numéro du cheval suivant (ou fin de liste)
        if k + 1 < len(sa_positions):
            next_pos = sa_positions[k + 1]
            end = next_pos
            for j in range(next_pos - 1, pos, -1):
                if RE_NUM_ONLY.match(lines[j]):
                    end = j
                    break
        else:
            end = len(lines)
        blocks.append(lines[start:end])
    return blocks


def _parse_musique(musique: str) -> dict:
    """Extrait des features depuis la musique (5 dernières courses codées)."""
    # Une perf = chiffre(1-9)+lettre (h=haies, p=plat, s=steeple, a=attelé...) ou T/A/D/Js (incidents)
    perfs = re.findall(r"(\d|[ATDJ])[a-zA-Z]", musique)
    # On ne garde que les positions numériques valides
    positions = [int(p) for p in perfs if p.isdigit()]
    nb_courses = len(perfs)
    nb_victoires = positions.count(1)
    nb_places = sum(1 for p in positions if p <= 3)
    derniere = positions[0] if positions else None
    moyenne = round(sum(positions) / len(positions), 2) if positions else None
    return {
        "musique_raw": musique,
        "nb_courses_recentes": nb_courses,
        "nb_victoires_recentes": nb_victoires,
        "nb_places_recentes": nb_places,
        "derniere_position": derniere,
        "position_moyenne": moyenne,
    }


def _parse_block(block: list[str]) -> dict | None:
    """Parse un bloc de lignes → dict cheval. Retourne None si malformé."""
    if len(block) < 5:
        return None

    cheval = {
        "numero": int(block[0]),
        "nom": None,
        "artifice": None,
        "sexe": None,
        "age": None,
        "poids": None,
        "jockey": None,
        "musique": None,
        "vh": None,
        "gains_eur": None,
        "entraineur": None,
        "cote_pmu": None,
        "non_partant": False,
    }

    # Index 1 = nom (1 ou 2 lignes — on prend la première non-poids)
    idx = 1
    cheval["nom"] = block[idx]
    idx += 1

    # Optionnel : "-" = présence d'artifice
    if idx < len(block) and block[idx] in ("-", "Œ", "œ"):
        cheval["artifice"] = "oui"
        idx += 1

    # SA + Poids : "H4 71" ou "F4 68,5"
    while idx < len(block):
        m = RE_SA_POIDS.match(block[idx])
        if m:
            cheval["sexe"] = m.group(1)
            cheval["age"] = int(m.group(2))
            cheval["poids"] = float(m.group(3).replace(",", "."))
            idx += 1
            break
        idx += 1
    else:
        return None  # pas de SA+Poids trouvé

    # Jockey (1 ligne)
    if idx < len(block):
        cheval["jockey"] = block[idx]
        idx += 1

    # Ligne combinée : "musique vh gains € entraineur"
    while idx < len(block):
        m = RE_PERF_GALOP.match(block[idx]) or RE_PERF_TROT.match(block[idx])
        if m:
            cheval["musique"] = m.group("musique").strip()
            vh_v = m.groupdict().get("vh")
            cheval["vh"] = float(vh_v.replace(",", ".")) if vh_v else None
            cheval["gains_eur"] = int(m.group("gains").replace(" ", ""))
            cheval["entraineur"] = m.group("entraineur").strip()
            idx += 1
            break
        idx += 1

    # Cote OU non-partant (NP)
    while idx < len(block):
        if block[idx] == "NP":
            cheval["non_partant"] = True
            break
        if RE_COTE.match(block[idx]):
            cheval["cote_pmu"] = float(block[idx].replace(",", "."))
            break
        idx += 1

    # Enrichissement musique
    if cheval["musique"]:
        cheval.update(_parse_musique(cheval["musique"]))

    return cheval


def parse_partants(text: str) -> list[dict]:
    """Parse tous les partants depuis le texte paris-turf."""
    lines = _clean_lines(text)
    blocks = _split_blocks(lines)
    chevaux: list[dict] = []
    for b in blocks:
        ch = _parse_block(b)
        if ch and ch["numero"] is not None:
            chevaux.append(ch)
    return chevaux


# ----- API principale ----------------------------------------------------------

def parse_paris_turf(text: str) -> dict:
    """Point d'entrée : texte brut → dict structuré."""
    return {
        "date": str(date.today()),
        "source": "paris-turf.com/quinte/aujourdhui",
        "course": parse_course_info(text),
        "partants": parse_partants(text),
    }


# ----- CLI / test --------------------------------------------------------------

if __name__ == "__main__":
    here = Path(__file__).parent
    raw_path = here / "raw_paristurf_2026-05-16.txt"
    if not raw_path.exists():
        print(f"[ERREUR] Fichier source introuvable : {raw_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = raw_path.read_text(encoding="utf-8")
    data = parse_paris_turf(raw_text)

    out_path = here / "quinte_du_jour_parsed.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Résumé console
    c = data["course"]
    print(f"Course   : {c['reunion']}{c['course_num']} {c['hippodrome']} — {c['nom']}")
    print(f"Détails  : {c['type']} | {c['distance_m']}m | {c['terrain']} | {c['nb_partants']} partants | {c['allocation_eur']} €")
    print(f"Partants : {len(data['partants'])} parsés")
    print()
    print(f"{'N°':>3} {'Nom':<22} {'SA':>3} {'Poids':>6} {'Cote':>5} {'Gains':>10} {'Jockey':<20} {'Entraîneur':<25}")
    for ch in data["partants"]:
        sa = f"{ch['sexe'] or '?'}{ch['age'] or '?'}"
        poids = f"{ch['poids']}" if ch['poids'] else "?"
        cote = f"{ch['cote_pmu']}" if ch['cote_pmu'] else "?"
        gains = f"{ch['gains_eur']:,}".replace(",", " ") if ch['gains_eur'] else "?"
        print(f"{ch['numero']:>3} {(ch['nom'] or '?')[:22]:<22} {sa:>3} {poids:>6} {cote:>5} {gains:>10} {(ch['jockey'] or '?')[:20]:<20} {(ch['entraineur'] or '?')[:25]:<25}")

    print(f"\n[OK] JSON écrit : {out_path}")
       