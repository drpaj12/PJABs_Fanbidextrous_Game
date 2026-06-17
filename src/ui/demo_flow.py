# src/ui/demo_flow.py
"""Back-compat shim. The real flow lives in src/ui/flow.py."""
from src.ui import flow


def start(app) -> None:
    flow.start(app, sim_mode=False)


def start_simulation(app, sim_rel_path: str) -> None:
    flow.start_simulation(app, sim_rel_path, sim_mode=True)
