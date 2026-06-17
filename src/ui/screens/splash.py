# src/ui/screens/splash.py
"""Loading splash: title + animated dots + cycling tips + progress bar. dt-based."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import font
from src.utils.constants import CONFIG, LAYOUT

_C = CONFIG["colors"]
_TIPS = [
    "Tip: predict the next 5 minutes, not the final score.",
    "Tip: an exact call fills your attack meter fastest.",
    "Tip: a wild miss feeds the danger meter.",
    "Tip: rotate your roster -- each player acts once per cycle.",
]


class SplashScreen(Screen):
    def __init__(self, app, on_done, sim=None) -> None:
        super().__init__(app)
        self.on_done = on_done
        self.sim = sim
        self.elapsed = 0.0
        self.duration = LAYOUT.f("splash_duration", 2.2)

    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_s):
            self._finish()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._finish()

    def _finish(self) -> None:
        self.elapsed = self.duration
        self.on_done()

    def update(self, dt: float) -> None:
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.on_done()

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        dots = "." * (int(self.elapsed / 0.4) % 4)
        tf = font(LAYOUT.i("splash_title_size", 38))
        title = tf.render(CONFIG["display"]["title"] + dots, True, _C["accent"])
        surface.blit(title, title.get_rect(center=(sw // 2, LAYOUT.i("splash_title_y", 300))))
        tip_i = int(self.elapsed / 1.5) % len(_TIPS)
        tipf = font(LAYOUT.i("splash_tip_size", 20))
        tip = tipf.render(_TIPS[tip_i], True, _C["text_dim"])
        surface.blit(tip, tip.get_rect(center=(sw // 2, LAYOUT.i("splash_tip_y", 470))))
        bw, bh = LAYOUT.i("splash_bar_w", 320), LAYOUT.i("splash_bar_h", 26)
        bx, by = (sw - bw) // 2, LAYOUT.i("splash_bar_y", 520)
        pygame.draw.rect(surface, _C["surface"], (bx, by, bw, bh), border_radius=8)
        frac = min(1.0, self.elapsed / self.duration)
        pygame.draw.rect(surface, _C["accent"], (bx, by, int(bw * frac), bh), border_radius=8)
        pygame.draw.rect(surface, _C["border"], (bx, by, bw, bh), width=2, border_radius=8)
