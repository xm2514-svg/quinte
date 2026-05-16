# QUINTE

Pipeline automatique de prédiction du Quinté+ du jour : scrape paris-turf.com → algo de scoring → top 5 → PWA installable sur téléphone.

## Lancer

```
python quinte.py              # Quinté+ d'aujourd'hui
python quinte.py --demain     # Quinté+ de demain
```

## Structure

| Dossier | Contenu |
|---|---|
| `src/`           | Code Python (parser, algo, scraper, push, run) |
| `pwa/`           | Site web installable (index.html + manifest + sw + data/) |
| `app/`           | App Kivy + buildozer.spec (APK Android) |
| `cache/`         | Données scrapées + logs + JSON intermédiaires (gitignored) |
| `docs/`          | Documentation (bilans, procédures) |
| `tools/`         | Scripts utilitaires Windows (.bat) |
| `golden_backup/` | Sauvegardes versionnées des fichiers critiques |

## Workflow

1. `tools/setup_github.bat` (une fois) : init repo Git + premier push
2. `tools/install_tache_planifiee.bat` : tâche Windows auto 9h00 chaque jour
3. Chaque matin : `quinte.py` scrape, calcule, push GitHub → la PWA sur ton téléphone se met à jour automatiquement
4. `tools/tester_local.bat` : test local de la PWA avant push

## URLs publiques (après push GitHub Pages activé)

- JSON brut : `https://raw.githubusercontent.com/xm2514-svg/quinte/main/pwa/data/quinte_x_top5.json`
- PWA installable : `https://xm2514-svg.github.io/quinte/`
