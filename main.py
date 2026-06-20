# main.py  (pygbag web entry)
import asyncio
from src.ui.app import App
from src.ui import flow


async def main() -> None:
    app = App()
    flow.start_launcher(app)   # pick Live match (real fixtures) or an offline test game
    await app.run()


asyncio.run(main())
