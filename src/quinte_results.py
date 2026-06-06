"""QUINTE-X — Recupere l'arrivee du Quinte+ d'hier (API PMU) et archive un comparatif.

Sortie : data/historique/YYYY-MM-DD.json
Le fichier est commit + push directement (utile sur GitHub Actions runner ou local).
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, timedelta

from paths import BASE as HERE

UA = {"User-Agent": "Mozilla/5.0"}


def _fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def find_quinte(target_pmu):
    prog = _fetch(f"https://offline.turfinfo.api.pmu.fr/rest/client/61/programme/{target_pmu}")
    for r in prog.get("programme", {}).get("reunions", []):
        for c in r.get("courses", []):
            for p in (c.get("paris") or []):
                if "QUINTE_PLUS" in str(p.get("typePari", "")):
                    return {
                        "reunion": r["numOfficiel"],
                        "course": c["numOrdre"],
                        "hippodrome": r["hippodrome"]["libelleCourt"],
                        "libelle": c.get("libelle"),
                    }
    return None


def fetch_arrivee(target_pmu, reunion, course):
    url = (f"https://offline.turfinfo.api.pmu.fr/rest/client/61/programme/{target_pmu}"
           f"/R{reunion}/C{course}")
    course_data = _fetch(url)
    ordre = course_data.get("ordreArrivee")
    if not ordre:
        return None
    return [{"rang": i + 1, "numero": grp[0]} for i, grp in enumerate(ordre)]


def git_commit_push(file_path, message):
    """Commit + push le fichier. Echoue silencieusement si pas dans un repo git."""
    try:
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
                       check=False, cwd=HERE, capture_output=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"],
                       check=False, cwd=HERE, capture_output=True)
        subprocess.run(["git", "add", str(file_path.relative_to(HERE))],
                       check=True, cwd=HERE, capture_output=True)
        # Si rien a ajouter (deja stage), git diff --cached est vide
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=HERE)
        if r.returncode == 0:
            print("[GIT] Rien a committer")
            return
        subprocess.run(["git", "commit", "-m", message],
                       check=True, cwd=HERE, capture_output=True)
        subprocess.run(["git", "push"], check=True, cwd=HERE, capture_output=True)
        print(f"[GIT] Push OK : {message}")
    except subprocess.CalledProcessError as e:
        print(f"[GIT] Echec (non bloquant) : {e}")
    except Exception as e:
        print(f"[GIT] Erreur non geree : {e}")


def main():
    target = date.today() - timedelta(days=1)
    target_pmu = target.strftime("%d%m%Y")
    target_iso = target.strftime("%Y-%m-%d")

    out_dir = HERE / "data" / "historique"
    out_path = out_dir / f"{target_iso}.json"

    if out_path.exists():
        print(f"[SKIP] Historique deja present : {out_path.name}")
        return 0

    try:
        quinte = find_quinte(target_pmu)
    except Exception as e:
        print(f"[ERREUR] find_quinte : {e}")
        return 0

    if not quinte:
        print(f"[SKIP] Aucun Quinte+ trouve le {target_iso}")
        return 0

    try:
        arrivee = fetch_arrivee(target_pmu, quinte["reunion"], quinte["course"])
    except Exception as e:
        print(f"[ERREUR] fetch_arrivee : {e}")
        return 0

    if not arrivee:
        print(f"[SKIP] Pas d arrivee disponible pour {target_iso}")
        return 0

    pred_path = HERE / "data" / "quinte_x_top5.json"
    pred_top5 = None
    pred_date = None
    if pred_path.exists():
        try:
            pred = json.loads(pred_path.read_text(encoding="utf-8"))
            pred_date = pred.get("date")
            if pred_date == target_iso:
                pred_top5 = [c["numero"] for c in pred.get("top5", [])]
        except json.JSONDecodeError:
            print(f"[WARN] quinte_x_top5.json corrompu, predictions ignorees")

    metriques = None
    if pred_top5:
        ar_nums = [a["numero"] for a in arrivee]
        top3 = set(ar_nums[:3])
        top5_real = set(ar_nums[:5])
        pred_set = set(pred_top5)
        favori = pred_top5[0] if pred_top5 else None
        metriques = {
            "nb_top5_pred_dans_top3_reel": len(pred_set & top3),
            "nb_top5_pred_dans_top5_reel": len(pred_set & top5_real),
            "favori_predit": favori,
            "favori_arrive_rang": (ar_nums.index(favori) + 1) if favori in ar_nums else None,
        }

    record = {
        "date": target_iso,
        "course": quinte,
        "arrivee": arrivee,
        "predictions": {
            "top5": pred_top5,
            "date_prediction": pred_date,
        } if pred_top5 else None,
        "metriques": metriques,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Historique ecrit : {out_path}")
    if metriques:
        print(f"     Top5 dans top3 reel : {metriques['nb_top5_pred_dans_top3_reel']}/3")
        print(f"     Top5 dans top5 reel : {metriques['nb_top5_pred_dans_top5_reel']}/5")

    # Push automatique si on est dans un repo git (runner GitHub Actions ou Termux)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        git_commit_push(out_path, f"auto: results {target_iso}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
