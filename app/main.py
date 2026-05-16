"""
QUINTE-X — App Kivy : affiche le top 5 du jour sur PC / tablette / APK Android.

Source données : `quinte_x_top5.json` (local) — à terme : raw URL GitHub.
"""

import json
from pathlib import Path

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle


# ----- chargement données ------------------------------------------------------

GITHUB_RAW_URL = "https://raw.githubusercontent.com/xm2514-svg/quinte/main/data/quinte_x_top5.json"


def find_data_file() -> Path | None:
    """Cherche le fichier top5 en local (fallback PC/test)."""
    candidates = [
        Path(__file__).parent / "quinte_x_top5.json",
        Path(__file__).parent.parent / "quinte_x_top5.json",
        Path.cwd() / "quinte_x_top5.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_data() -> dict:
    """Fetch GitHub raw URL en priorité (APK Android), sinon fichier local."""
    try:
        import urllib.request
        req = urllib.request.Request(GITHUB_RAW_URL,
                                     headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        p = find_data_file()
        if p:
            return json.loads(p.read_text(encoding="utf-8"))
        return {"error": "Pas de connexion et pas de JSON local."}


# ----- couleurs (palette sobre tablette) --------------------------------------

C_BG          = (0.07, 0.09, 0.13, 1)   # bleu nuit
C_HEADER_BG   = (0.10, 0.13, 0.20, 1)
C_CARD_BG     = (0.13, 0.16, 0.24, 1)
C_GOLD        = (0.95, 0.78, 0.32, 1)   # or pour le #1
C_SILVER      = (0.78, 0.83, 0.88, 1)   # argent pour #2
C_BRONZE      = (0.80, 0.55, 0.30, 1)   # bronze pour #3
C_TEXT        = (0.95, 0.96, 0.98, 1)
C_TEXT_DIM    = (0.65, 0.70, 0.78, 1)
C_ACCENT      = (0.30, 0.85, 0.65, 1)   # vert favori


def rank_color(rank: int):
    return {1: C_GOLD, 2: C_SILVER, 3: C_BRONZE}.get(rank, C_ACCENT)


# ----- widgets ----------------------------------------------------------------

class HeaderBox(BoxLayout):
    def __init__(self, course: dict, fiabilite: float, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(110), padding=dp(14), spacing=dp(4), **kw)
        with self.canvas.before:
            Color(*C_HEADER_BG)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._upd, size=self._upd)

        titre = f"{course.get('reunion','?')}{course.get('course_num','?')} {course.get('hippodrome','?')}"
        sous_titre = course.get('nom') or '—'
        infos = f"{course.get('type','?')} · {course.get('distance_m','?')}m · terrain {course.get('terrain','?')} · {course.get('nb_partants','?')} partants"
        fiab_txt = f"Fiabilité algo : {int(fiabilite*100)}%"

        self.add_widget(Label(text=f"[b]{titre}[/b]", markup=True, color=C_GOLD,
                              font_size=dp(20), size_hint_y=None, height=dp(28), halign="left", valign="middle"))
        self.add_widget(Label(text=sous_titre, color=C_TEXT, font_size=dp(14),
                              size_hint_y=None, height=dp(20), halign="left", valign="middle", shorten=True))
        self.add_widget(Label(text=infos, color=C_TEXT_DIM, font_size=dp(12),
                              size_hint_y=None, height=dp(18), halign="left", valign="middle"))
        self.add_widget(Label(text=fiab_txt, color=C_ACCENT, font_size=dp(12),
                              size_hint_y=None, height=dp(18), halign="left", valign="middle"))
        for w in self.children:
            w.text_size = (Window.width - dp(32), w.height)

    def _upd(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class HorseCard(BoxLayout):
    def __init__(self, ch: dict, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(98), padding=dp(12), spacing=dp(10), **kw)
        with self.canvas.before:
            Color(*C_CARD_BG)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._upd, size=self._upd)

        rang = ch.get("rang_predit") or 0
        col = rank_color(rang)

        # Colonne rang + numéro
        left = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(70), spacing=dp(2))
        left.add_widget(Label(text=f"[b]{rang}[/b]", markup=True, color=col,
                              font_size=dp(32), halign="center", valign="middle"))
        left.add_widget(Label(text=f"N° {ch.get('numero','?')}", color=C_TEXT_DIM,
                              font_size=dp(12), halign="center", valign="middle"))
        self.add_widget(left)

        # Colonne nom + jockey + entraineur
        mid = BoxLayout(orientation="vertical", spacing=dp(2))
        mid.add_widget(Label(text=f"[b]{ch.get('nom','?')}[/b]", markup=True, color=C_TEXT,
                             font_size=dp(18), halign="left", valign="middle",
                             text_size=(Window.width - dp(260), dp(24)), shorten=True))
        jock = ch.get("jockey") or "—"
        ent  = ch.get("entraineur") or "—"
        mid.add_widget(Label(text=f"Jockey   : {jock}", color=C_TEXT_DIM, font_size=dp(12),
                             halign="left", valign="middle", text_size=(Window.width - dp(260), dp(18))))
        mid.add_widget(Label(text=f"Entraîn. : {ent}", color=C_TEXT_DIM, font_size=dp(12),
                             halign="left", valign="middle", text_size=(Window.width - dp(260), dp(18))))
        self.add_widget(mid)

        # Colonne cote + score
        right = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(110), spacing=dp(2))
        cote = ch.get("cote_pmu")
        cote_txt = f"{cote}" if cote else "?"
        right.add_widget(Label(text=f"Cote", color=C_TEXT_DIM, font_size=dp(11),
                               halign="center", valign="middle"))
        right.add_widget(Label(text=f"[b]{cote_txt}[/b]", markup=True, color=col,
                               font_size=dp(22), halign="center", valign="middle"))
        right.add_widget(Label(text=f"score {ch.get('score','?')}", color=C_ACCENT, font_size=dp(11),
                               halign="center", valign="middle"))
        self.add_widget(right)

    def _upd(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class QuinteXRoot(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(10), **kw)
        with self.canvas.before:
            Color(*C_BG)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=self._upd, size=self._upd)

        data = load_data()

        if data.get("error"):
            self.add_widget(Label(text=data["error"], color=C_TEXT, font_size=dp(16)))
            return

        course = data.get("course", {})
        fiab = data.get("fiabilite_globale", 1.0)
        self.add_widget(HeaderBox(course, fiab))

        # Titre top 5
        title = Label(text="[b]TOP 5 PRÉDIT[/b]", markup=True, color=C_GOLD,
                      font_size=dp(16), size_hint_y=None, height=dp(28), halign="left", valign="middle")
        title.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(title)

        # Scroll des cards
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        cards = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        cards.bind(minimum_height=cards.setter("height"))
        for ch in data.get("top5", []):
            cards.add_widget(HorseCard(ch))
        scroll.add_widget(cards)
        self.add_widget(scroll)

        # Footer
        footer = Label(text=f"Date : {data.get('date','?')}  ·  QUINTE-X v2",
                       color=C_TEXT_DIM, font_size=dp(11),
                       size_hint_y=None, height=dp(20), halign="center", valign="middle")
        footer.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(footer)

    def _upd(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class QuinteXApp(App):
    title = "QUINTE-X"

    def build(self):
        Window.clearcolor = C_BG
        return QuinteXRoot()


if __name__ == "__main__":
    QuinteXApp().run()
