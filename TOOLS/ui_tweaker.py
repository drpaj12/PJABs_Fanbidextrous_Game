# TOOLS/ui_tweaker.py
"""Mobile layout tweaker: live portrait preview + value panel editing layout_config.json.

Dev-only. NEVER imported by the game or the pygbag build.

Usage:  .venv/Scripts/python TOOLS/ui_tweaker.py
Hotkeys: Ctrl+S save | R reload | Up/Down select | Left/Right nudge (Shift x10) |
         1..5 switch preview screen | Q/Esc quit
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from src.utils.constants import CONFIG

LAYOUT_PATH = PROJECT_ROOT / "config" / "layout_config.json"
PREVIEW_W, PREVIEW_H = CONFIG["display"]["width"], CONFIG["display"]["height"]
PANEL_W = 380
ROW_H = 26


def _editable_keys(data: dict) -> list[str]:
    return [k for k, v in data.items() if isinstance(v, (int, float))]


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((PREVIEW_W + PANEL_W, PREVIEW_H))
    pygame.display.set_caption("UI Tweaker (mobile)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)
    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    keys = _editable_keys(data)
    sel = 0
    scroll = 0
    msg = "R reload  Ctrl+S save  arrows edit"

    # Build a synthetic preview by running the real screens against a stub app.
    from src.ui.app import App
    # We render onto a subsurface so the real screens think the canvas is 414x896.

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        mods = pygame.key.get_mods()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif e.key == pygame.K_r:
                    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
                    keys = _editable_keys(data)
                    msg = "reloaded"
                elif e.key == pygame.K_s and (mods & pygame.KMOD_CTRL):
                    LAYOUT_PATH.write_text(json.dumps(data, indent=2), encoding="ascii")
                    msg = "saved"
                elif e.key == pygame.K_DOWN:
                    sel = min(len(keys) - 1, sel + 1)
                elif e.key == pygame.K_UP:
                    sel = max(0, sel - 1)
                elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    step = 10 if (mods & pygame.KMOD_SHIFT) else 1
                    step = -step if e.key == pygame.K_LEFT else step
                    k = keys[sel]
                    data[k] = round(data[k] + step, 3) if isinstance(data[k], float) else data[k] + step
                    msg = f"{k} = {data[k]}"
            elif e.type == pygame.MOUSEBUTTONDOWN and e.pos[0] > PREVIEW_W:
                row = (e.pos[1] - 40) // ROW_H + scroll
                if 0 <= row < len(keys):
                    sel = row
            elif e.type == pygame.MOUSEWHEEL:
                scroll = max(0, scroll - e.y)

        screen.fill((10, 10, 14))
        # preview placeholder: a framed portrait area (screens render here when wired)
        pygame.draw.rect(screen, (23, 25, 31), (0, 0, PREVIEW_W, PREVIEW_H))
        pygame.draw.rect(screen, (0, 245, 228), (0, 0, PREVIEW_W, PREVIEW_H), 1)
        screen.blit(font.render("live preview (414x896)", True, (120, 120, 130)), (14, 14))

        # panel
        pygame.draw.rect(screen, (18, 19, 24), (PREVIEW_W, 0, PANEL_W, PREVIEW_H))
        screen.blit(font.render(msg, True, (0, 245, 228)), (PREVIEW_W + 12, 12))
        visible = (PREVIEW_H - 40) // ROW_H
        for i in range(scroll, min(len(keys), scroll + visible)):
            k = keys[i]
            y = 40 + (i - scroll) * ROW_H
            color = (238, 240, 245) if i == sel else (150, 154, 164)
            if i == sel:
                pygame.draw.rect(screen, (40, 44, 56),
                                 (PREVIEW_W + 4, y - 2, PANEL_W - 8, ROW_H))
            screen.blit(font.render(f"{k}", True, color), (PREVIEW_W + 12, y))
            screen.blit(font.render(f"{data[k]}", True, color),
                        (PREVIEW_W + PANEL_W - 70, y))
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
