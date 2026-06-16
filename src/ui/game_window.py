"""
game_window.py -- pygame event loop and screen state machine.

States:  menu -> playing -> game_over
All rendering happens here or in helper modules inside src/ui/.
All game logic calls go through src/game/ modules.
"""

import asyncio

import pygame
from src.game.game_state import GameState
from src.game.rules import apply_action, check_winner
from src.utils.constants import CONFIG


# Screen states
STATE_MENU      = "menu"
STATE_PLAYING   = "playing"
STATE_GAME_OVER = "game_over"


async def run() -> None:
    """Initialize pygame and run the main loop.

    Declared async and yielding once per frame so the same loop runs
    both the desktop build (src/main.py) and the pygbag web build
    (main.py at the project root) -- pygbag needs the browser's event
    loop to get a turn every frame or the tab freezes.
    """
    pygame.init()

    width: int  = CONFIG["display"]["width"]
    height: int = CONFIG["display"]["height"]
    fps: int    = CONFIG["display"]["fps"]
    title: str  = CONFIG["display"]["title"]

    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption(title)
    clock = pygame.time.Clock()

    state = GameState()
    screen_state = STATE_MENU

    # Colors from config so they can be tweaked without touching code
    color_bg     = tuple(CONFIG["colors"]["background"])
    color_text   = tuple(CONFIG["colors"]["text"])
    color_accent = tuple(CONFIG["colors"]["accent"])

    font_large = pygame.font.SysFont("monospace", 36, bold=True)
    font_small = pygame.font.SysFont("monospace", 18)

    running = True
    while running:
        dt = clock.tick(fps)

        # ---- Event handling ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if screen_state == STATE_MENU and event.key == pygame.K_RETURN:
                    screen_state = STATE_PLAYING

                elif screen_state == STATE_PLAYING:
                    # Placeholder: SPACE triggers a dummy "place" action
                    # Replace with your real input logic from DESIGN.md
                    if event.key == pygame.K_SPACE:
                        action = {"type": "place", "target": 1, "entity_index": 0}
                        apply_action(state, state.current_player_index, action)
                        check_winner(state)
                        if state.is_over():
                            screen_state = STATE_GAME_OVER

                elif screen_state == STATE_GAME_OVER and event.key == pygame.K_r:
                    state = GameState()
                    screen_state = STATE_MENU

        # ---- Drawing ----
        screen.fill(color_bg)

        if screen_state == STATE_MENU:
            _draw_menu(screen, font_large, font_small, color_text, color_accent, title)

        elif screen_state == STATE_PLAYING:
            _draw_game(screen, font_large, font_small, color_text, color_accent, state)

        elif screen_state == STATE_GAME_OVER:
            _draw_game_over(screen, font_large, font_small, color_text, color_accent, state)

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


# ------------------------------------------------------------------
# Screen drawing helpers
# Replace these with your actual game screens.
# ------------------------------------------------------------------

def _draw_menu(screen, font_large, font_small, color_text, color_accent, title: str) -> None:
    cx = screen.get_width() // 2
    cy = screen.get_height() // 2
    _blit_centered(screen, font_large.render(title, True, color_accent), cx, cy - 40)
    _blit_centered(screen, font_small.render("Press ENTER to start", True, color_text), cx, cy + 20)


def _draw_game(screen, font_large, font_small, color_text, color_accent, state: GameState) -> None:
    cx = screen.get_width() // 2
    turn_text = f"Turn {state.turn}  |  {state.active_player().name}'s move"
    _blit_centered(screen, font_small.render(turn_text, True, color_accent), cx, 40)
    for i, player in enumerate(state.players):
        line = f"{player.name}: {player.score} pts"
        _blit_centered(screen, font_small.render(line, True, color_text), cx, 120 + i * 40)
    _blit_centered(screen, font_small.render("Press SPACE to take action", True, color_text), cx, 300)


def _draw_game_over(screen, font_large, font_small, color_text, color_accent, state: GameState) -> None:
    cx = screen.get_width() // 2
    cy = screen.get_height() // 2
    if state.winner is not None:
        msg = f"{state.players[state.winner].name} wins!"
    else:
        msg = "Draw!"
    _blit_centered(screen, font_large.render(msg, True, color_accent), cx, cy - 30)
    _blit_centered(screen, font_small.render("Press R to restart", True, color_text), cx, cy + 30)


def _blit_centered(surface, rendered, cx: int, cy: int) -> None:
    rect = rendered.get_rect(center=(cx, cy))
    surface.blit(rendered, rect)
