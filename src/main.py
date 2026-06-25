# src/main.py
"""Desktop entry point.

  .venv/Scripts/python src/main.py                      # MockFeed demo (no SIM)
  .venv/Scripts/python src/main.py --simdemo            # MockFeed demo + SIM hotkeys
  .venv/Scripts/python src/main.py --sim <slug>         # recorded match + SIM hotkeys
  .venv/Scripts/python src/main.py --party              # SOLO crawl on a recording + SIM hotkeys
  .venv/Scripts/python src/main.py --sololive [--simlive]  # SOLO live crawl on the real feed
  .venv/Scripts/python src/main.py --dungeon            # dungeon crawl on test_sim recording
  .venv/Scripts/python src/main.py --simrt              # realtime SIM harness (rehearse the live flow)
  .venv/Scripts/python src/main.py --live [fixture_id]  # LIVE match off the relay
  .venv/Scripts/python src/main.py --launcher           # web-style menu: live vs test game
  .venv/Scripts/python src/main.py --app                # full web entry: username -> menu
"""
import asyncio
import sys
from pathlib import Path

# Allow `python src/main.py` (run by path) to find the `src` package: the project
# root is this file's grandparent. Harmless under `-m src.main` / PYTHONPATH too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui.app import App
from src.ui import flow
from src.utils.constants import CONFIG


async def main() -> None:
    app = App()
    # Desktop dev runs the live paths AS the lead client so it polls standalone; the
    # web build asks for a username (--app) to decide lead vs follower at run time.
    sim_live = "--simlive" in sys.argv
    if "--app" in sys.argv:
        flow.start_app(app, sim_mode=sim_live)
    elif "--launcher" in sys.argv:
        flow.start_launcher(app, sim_mode=sim_live, is_lead=True)
    elif "--sim" in sys.argv:
        slug = sys.argv[sys.argv.index("--sim") + 1]
        flow.start_simulation(app, f"assets/data/simulations/{slug}.json", sim_mode=True)
    elif "--live" in sys.argv:
        i = sys.argv.index("--live")
        arg = sys.argv[i + 1] if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit() \
            else None
        if arg is not None:
            flow.start_live(app, int(arg), sim_mode=sim_live, is_lead=True)
        else:
            # No id given -> show the match picker (config live.fixtures).
            flow.start_live_select(app, sim_mode=sim_live, is_lead=True)
    elif "--sololive" in sys.argv:
        # SOLO live crawl on the real match feed: party of one, always the leader (no relay
        # coordination). --simlive accelerates pre-game waits; SIM hotkeys still apply.
        flow.start_dungeon_party_live(app, "drpaj", is_lead=True,
                                      sim_mode=sim_live, solo=True)
    elif "--party" in sys.argv:
        # --party plays a RECORDED match as a SOLO crawl (party of one over an in-process
        # relay -- no network). SIM mode is ON so the hotkeys (H help, R auto-buy+descend,
        # F auto-pick+advance a window, S skip/continue) step the whole crawl through fast.
        # The game-select and lobby auto-advance under SIM.
        flow.start_sim_select(
            app,
            lambda path: flow.start_dungeon_party(app, "drpaj", path, sim_mode=True, solo=True),
            sim_mode=True)
    elif "--dungeon" in sys.argv:
        flow.start_sim_select(
            app, lambda path: flow.start_dungeon_sim(app, path, sim_mode=True),
            sim_mode=True)
    elif "--simrt" in sys.argv:
        # Realtime SIM harness: rehearse the live dungeon flow on a recorded match + virtual
        # clock (role -> mode -> match -> join offset), with a [self]/[peer] diagnostic trail.
        flow.start_sim_harness(app, "drpaj", is_lead=True)
    elif "--simdemo" in sys.argv:
        flow.start(app, sim_mode=True)
    else:
        flow.start(app, sim_mode=False)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
