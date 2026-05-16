# QUINTE — Reprise prévue 20h40 (2026-05-16)

## État au moment de la coupure

**Tout est sauvegardé.** Golden backups dans `golden_backup/` :
- `quinte_golden_v1.0.0.py`
- `quinte_x_run_golden_v1.0.0.py`
- `quinte_x_parser_golden_v1.0.0.py`
- `quinte_x_parser_fiche_golden_v1.0.0.py`
- `quinte_x_algo_v2_golden_v1.0.0.py`
- `main_golden_v1.0.0.py` (app Kivy)
- `push_github_golden_v1.0.1.py`
- `setup_github_golden_v1.0.1.bat`

## Ce qui marche déjà (testé)

- ✅ `quinte.py` : pipeline complet (Playwright + parse + algo v2 + JSON + HTML)
- ✅ `quinte.html` : visualisation top 5 (déjà vue dans Edge)
- ✅ Top 5 pour 17/5 (Grand Steeple-Chase de Paris) calculé : Sel Jem, Kivala du Berlais, Juntos Ganamos, Kolokico, Gold Tweet
- ✅ Backend autonome (urllib + Playwright pour rendu JS)
- ✅ APK Kivy code prêt (compilation WSL pas faite)

## Ce qui est PRÊT mais pas encore activé

- `push_github.py` : push auto vers `github.com/xm2514-svg/quinte` avec token masqué
- `setup_github.bat` : init repo local (à lancer UNE FOIS)
- `.github_token` : token récupéré depuis `config-sentinel.txt` (UTF-16), stocké local, jamais loggé, jamais committé (gitignored)

## EN ATTENTE à 20h40

**Décision Xavier :** repo `quinte` sur github.com doit être **PUBLIC ou PRIVÉ** ?

- **Public** (recommandé pour livraison rapide) → GitHub Pages gratuit → URL `xm2514-svg.github.io/quinte/` accessible direct depuis téléphone → installation PWA "Ajouter à l'écran d'accueil" en 10s. **C'est la voie pour livrer ce soir.**
- **Privé** → GitHub Pages payant. Alternative gratuite = Netlify drop. Plus de friction.

## Actions séquentielles à 20h40

Si **PUBLIC choisi** :
1. Xavier crée repo public `quinte` sur github.com/xm2514-svg (2 min)
2. Claude code la PWA : `index.html` + `manifest.json` + `service-worker.js` (10 min)
3. Xavier double-clique `setup_github.bat` → init + premier push (3 min)
4. Xavier active GitHub Pages sur Settings → Pages → main / root (1 min)
5. Xavier attend 30s puis ouvre `https://xm2514-svg.github.io/quinte/` sur son téléphone
6. Sur le téléphone : menu Edge/Chrome → "Ajouter à l'écran d'accueil" → app installée
7. Demain matin 9h : tâche Windows lance `quinte.py` → scrape + algo + push GitHub → l'app sur le téléphone se met à jour automatiquement

**Total ce soir : ~20 minutes pour livrer.**

## Si problème à la reprise

- Tous les scripts modifiés ont leur version golden dans `golden_backup/`
- `quinte.py --demain` retourne le top 5 calculé localement
- `quinte.html` affiche déjà la version actuelle (visualisable sans GitHub)
- Le token n'a JAMAIS été affiché dans le chat ni committé sur GitHub
