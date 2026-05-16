"""push_github.py - Push automatique top5+HTML sur GitHub via token (jamais affiche).

Lit le token depuis .github_token (gitignore, lu en interne, jamais logge).
Configure le remote avec le token integre pour permettre push sur repo prive.
"""

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from paths import BASE as HERE, CACHE, PWA, PWA_DATA, TOKEN_FILE
GITHUB_USER = "xm2514-svg"
GITHUB_REPO = "quinte"


def read_token():
    p = TOKEN_FILE
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").strip()


def mask(s, token):
    return s.replace(token, "***TOKEN***") if token and token in s else s


def configure_remote_with_token(token):
    url = f"https://{token}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"
    subprocess.run(["git", "remote", "remove", "origin"], cwd=HERE, capture_output=True)
    r = subprocess.run(["git", "remote", "add", "origin", url], cwd=HERE, capture_output=True, text=True)
    return r.returncode == 0


def run_cmd(cmd, token):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    return r.returncode, mask(r.stdout, token), mask(r.stderr, token)


def push():
    token = read_token()
    if not token:
        print("[push] .github_token introuvable. Lance setup_github.bat.")
        return False

    if not (HERE / ".git").exists():
        print("[push] Pas de repo Git. Lance setup_github.bat.")
        return False

    src = CACHE / "quinte_x_top5.json"
    if not src.exists():
        print(f"[push] {src.name} introuvable, skip")
        return False

    data_dir = PWA_DATA
    data_dir.mkdir(exist_ok=True)
    shutil.copy2(src, data_dir / "quinte_x_top5.json")
    print(f"[push] copie -> {data_dir / 'quinte_x_top5.json'}")

    if not configure_remote_with_token(token):
        print("[push] Echec config remote")
        return False

    msg = f"auto: top5 {date.today().isoformat()}"
    files_to_add = []
    pwa_files = [
        "pwa/data/quinte_x_top5.json",
        "pwa/index.html",
        "pwa/manifest.json",
        "pwa/icon.svg",
        "pwa/service-worker.js",
        "pwa/quinte.html",
        "README.md",
        "quinte.py",
    ]
    for rel in pwa_files:
        if (HERE / rel).exists():
            files_to_add.append(rel)
    # Ajoute aussi tout le code src/ pour avoir backup complet
    src_dir = HERE / "src"
    if src_dir.exists():
        for py in src_dir.glob("*.py"):
            files_to_add.append(f"src/{py.name}")

    cmds = [
        ["git", "add"] + files_to_add,
        ["git", "commit", "-m", msg],
        ["git", "push", "origin", "main"],
    ]
    for cmd in cmds:
        rc, so, se = run_cmd(cmd, token)
        if rc != 0:
            if "nothing to commit" in (so + se).lower() or "rien" in (so + se).lower():
                print(f"[push] {cmd[1]} : rien a pousser")
                return True
            print(f"[push] ECHEC {cmd[1]} : {se[:200]}")
            return False
        print(f"[push] OK : {cmd[1]}")

    print(f"[push] Publie sur github.com/{GITHUB_USER}/{GITHUB_REPO}")
    return True


if __name__ == "__main__":
    sys.exit(0 if push() else 1)
