# src/main.py
"""Desktop entry point."""
import asyncio
from src.ui.app import App
from src.ui import demo_flow


async def main() -> None:
    app = App()
    demo_flow.start(app)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
