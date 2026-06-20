# main.py  (pygbag web entry)
import asyncio
from src.ui.app import App
from src.ui import flow


async def main() -> None:
    app = App()
    flow.start_live_select(app)   # match-day: pick one of the configured live fixtures
    await app.run()


asyncio.run(main())
