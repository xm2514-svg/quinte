"""paths.py - Chemins centraux du projet QUINTE.

Tous les scripts src/ doivent importer ce module pour résoudre les chemins.
"""

from pathlib import Path

# Racine du projet (parent du dossier src/)
BASE = Path(__file__).parent.parent.resolve()

SRC          = BASE / "src"
PWA          = BASE / "pwa"
PWA_DATA     = PWA / "data"
APP          = BASE / "app"
CACHE        = BASE / "cache"
FICHES_RAW   = CACHE / "fiches_raw"
LOGS         = CACHE / "logs"
DOCS         = BASE / "docs"
TOOLS        = BASE / "tools"
GOLDEN       = BASE / "golden_backup"

TOKEN_FILE   = BASE / ".github_token"

# Assure que les dossiers de sortie existent
for d in (CACHE, FICHES_RAW, LOGS, PWA_DATA):
    d.mkdir(parents=True, exist_ok=True)
