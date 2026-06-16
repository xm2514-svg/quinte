"""Génère quinte.html à partir de quinte_x_top5.json — visualisation immédiate dans Chrome."""

import json
from pathlib import Path

from paths import BASE as HERE, CACHE, PWA
data = json.loads((CACHE / "quinte_x_top5.json").read_text(encoding="utf-8"))

c = data.get("course", {}) or {}
top5 = data.get("top5", []) or []
fiab = int(data.get("fiabilite_globale", 1.0) * 100)
nb_enrichis = data.get("nb_enrichis", "?")
nb_partants = data.get("nb_partants", "?")
cotes_dispo = data.get("cotes_dispo", 0)

GOLD = "#F2C752"
SILVER = "#C7D4E0"
BRONZE = "#CC8C4D"
ACCENT = "#4DD9A6"


def rank_color(r):
    return [GOLD, SILVER, BRONZE][r - 1] if 1 <= r <= 3 else ACCENT


cards = []
for ch in top5:
    rg = ch.get("rang_predit") or 0
    col = rank_color(rg)
    cote = ch.get("cote_pmu") or "—"
    sub = ch.get("sous_scores", {}) or {}
    cards.append(f"""
    <div class="card">
      <div class="rank" style="color:{col}">{rg}<div class="num">N° {ch.get('numero','?')}</div></div>
      <div class="info">
        <div class="name">{ch.get('nom','?')}</div>
        <div class="dim">Jockey&nbsp;&nbsp;&nbsp;: {ch.get('jockey') or '—'}</div>
        <div class="dim">Entraîn.&nbsp;: {ch.get('entraineur') or '—'}</div>
        <div class="bars">
          <span class="bar" title="Cote">C {int(sub.get('cote',0)*100)}%</span>
          <span class="bar" title="Gains">G {int(sub.get('gains',0)*100)}%</span>
          <span class="bar" title="Couple J/E">J/E {int(sub.get('couple_je',0)*100)}%</span>
          <span class="bar" title="Hippodrome">H {int(sub.get('hippodrome',0)*100)}%</span>
          <span class="bar" title="Terrain">T {int(sub.get('pref_terrain',0)*100)}%</span>
          <span class="bar" title="Distance">D {int(sub.get('pref_distance',0)*100)}%</span>
          <span class="bar" title="Récup">R {int(sub.get('recuperation',0)*100)}%</span>
        </div>
      </div>
      <div class="cote" style="color:{col}">
        <div class="cote-label">Cote</div>
        <div class="cote-val">{cote}</div>
        <div class="score">score {ch.get('score','?')}</div>
      </div>
    </div>""")

html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>QUINTE-X — {data.get('date','?')}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }}
body {{ background: #12161F; color: #F2F5F8; min-height: 100vh; padding: 18px; }}
.wrap {{ max-width: 720px; margin: 0 auto; }}
header {{ background: #1A2133; border-radius: 12px; padding: 18px; margin-bottom: 16px; border: 1px solid #232C42; }}
header h1 {{ color: {GOLD}; font-size: 22px; margin-bottom: 6px; }}
header .sub {{ color: #F2F5F8; font-size: 14px; margin-bottom: 4px; }}
header .meta {{ color: #A5AFC0; font-size: 12px; }}
header .fiab {{ color: {ACCENT}; font-size: 12px; margin-top: 6px; }}
h2 {{ color: {GOLD}; font-size: 16px; margin: 14px 6px; }}
.card {{ background: #1F2638; border-radius: 12px; padding: 14px; display: flex; gap: 14px; margin-bottom: 10px; border: 1px solid #232C42; }}
.rank {{ font-size: 38px; font-weight: 700; min-width: 70px; text-align: center; line-height: 1; }}
.rank .num {{ font-size: 11px; color: #A5AFC0; font-weight: 400; margin-top: 4px; }}
.info {{ flex: 1; min-width: 0; }}
.name {{ font-size: 19px; font-weight: 700; margin-bottom: 6px; color: #F2F5F8; }}
.dim {{ font-size: 12px; color: #A5AFC0; margin-bottom: 2px; }}
.bars {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }}
.bar {{ background: #2A3450; color: #C7D4E0; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }}
.cote {{ min-width: 110px; text-align: center; }}
.cote-label {{ font-size: 11px; color: #A5AFC0; }}
.cote-val {{ font-size: 26px; font-weight: 700; line-height: 1.1; }}
.score {{ color: {ACCENT}; font-size: 11px; margin-top: 4px; }}
footer {{ text-align: center; color: #A5AFC0; font-size: 11px; margin-top: 16px; }}
</style></head>
<body><div class="wrap">
<header>
  <h1>{c.get('reunion','?')}{c.get('course_num','?')} {c.get('hippodrome','?')}</h1>
  <div class="sub">{c.get('nom') or '—'}</div>
  <div class="meta">{c.get('type','?')} · {c.get('distance_m','?')}m · terrain {c.get('terrain') or '?'} · {nb_partants} partants</div>
  <div class="fiab">Fiabilité algo : {fiab}% · Enrichis {nb_enrichis}/{nb_partants} · Cotes {cotes_dispo}/{nb_partants}</div>
</header>
<h2>TOP 5 PRÉDIT</h2>
{''.join(cards)}
<footer>QUINTE-X v4 · {data.get('date','?')} · Légende sous-scores : C cote · G gains · J/E couple · H hippo · T terrain · D distance · R récup</footer>
</div></body></html>"""

out = PWA / "quinte.html"
out.write_text(html, encoding="utf-8")
print(f"[OK] Rendu écrit : {out}")
print(f"     Double-clique sur quinte.html pour voir le top 5 dans Chrome.")
