"""
Entry point -- keep this file small.
All game logic lives in src/game/.
All rendering lives in src/ui/.
"""

import asyncio
import sys
import os

# Make sure imports resolve from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.game_window import run


if __name__ == "__main__":
    asyncio.run(run())
