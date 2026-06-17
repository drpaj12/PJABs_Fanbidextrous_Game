# src/ui/screens/predict_screen.py
"""Predict screen: choose <=2 stat lines (+/- to set the integer), pick active player, toggle power."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, athlete_card
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.utils.constants import CONFIG, load_data

_MAX = CONFIG["game"]["max_predictions_per_window"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]


class PredictScreen(Screen):
    def __init__(self, app, available: list[DraftedAthlete], on_submit) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.lines: dict[str, int] = {s["code"]: s["default_line"] for s in _STATS}
        self.chosen: list[str] = []
        self.active_id: str | None = None
        self.use_power = False
        w = app.screen.get_width()
        self.submit_btn = Button(pygame.Rect(20, app.screen.get_height() - 60, w - 40, 46),
                                 "Lock predictions")

    def handle(self, event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        x, y = event.pos
        for i, s in enumerate(_STATS):
            row_y = 20 + i * 56
            if row_y <= y <= row_y + 48:
                if x > self.app.screen.get_width() - 60:      # plus
                    self.lines[s["code"]] += 1
                elif x > self.app.screen.get_width() - 120:   # minus
                    self.lines[s["code"]] = max(0, self.lines[s["code"]] - 1)
                else:                                          # toggle chosen
                    self._toggle(s["code"])
                return
        # active player row
        base_y = 20 + len(_STATS) * 56 + 10
        for j, ath in enumerate(self.available):
            r = pygame.Rect(20, base_y + j * 64, self.app.screen.get_width() - 40, 56)
            if r.collidepoint(event.pos):
                self.active_id = ath.athlete_id
                return
        if self.submit_btn.hit(event.pos) and self.chosen and self.active_id:
            preds = [Prediction(c, self.lines[c]) for c in self.chosen]
            self.on_submit(preds, self.active_id, self.use_power)

    def _toggle(self, code: str) -> None:
        if code in self.chosen:
            self.chosen.remove(code)
        elif len(self.chosen) < _MAX:
            self.chosen.append(code)

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        f = self.app.font
        c = CONFIG["colors"]
        for i, s in enumerate(_STATS):
            row = pygame.Rect(20, 20 + i * 56, surface.get_width() - 40, 48)
            sel = s["code"] in self.chosen
            pygame.draw.rect(surface, c["accent"] if sel else c["surface"], row, border_radius=8)
            surface.blit(f.render(f"{s['label']}: {self.lines[s['code']]}", True, c["white"]),
                         (row.x + 8, row.y + 12))
            surface.blit(f.render("-", True, c["white"]), (row.right - 110, row.y + 10))
            surface.blit(f.render("+", True, c["white"]), (row.right - 48, row.y + 10))
        base_y = 20 + len(_STATS) * 56 + 10
        for j, ath in enumerate(self.available):
            r = pygame.Rect(20, base_y + j * 64, surface.get_width() - 40, 56)
            athlete_card(surface, r, f, ath.name, ath.archetype, ath.stars,
                         ath.athlete_id == self.active_id)
        self.submit_btn.draw(surface, f)
