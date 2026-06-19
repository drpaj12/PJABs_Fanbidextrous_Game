# Change Log

Format: DATE | WHAT CHANGED | FILES TOUCHED
Append one line per session. Never delete old entries.

---

2026-06-15 | Project created from DarkWeb GameJam template | All files
2026-06-16 | API-Football smoke test script created; LIVE GATE PENDING (needs human API key + live match) - v1 defaults to MockFeed until verified | scripts/smoke_test_apifootball.py
2026-06-16 | Phase 5 mobile UI: widgets, async app, draft/predict/status screens, mock-feed demo flow, entry points wired | src/ui/*
2026-06-16 | pygbag mobile build OK (build-only); browser smoke-test PENDING (manual) | TOOLS/build_web_mobile.py
2026-06-16 | Post-review seam fix: api_field bridge now live (normalize_soccer.actuals_from_raw), yellow+red->cards, demo uses shared mapping, relay config reconciled, ScoreEvent.from_code guarded | src/game/normalize_soccer.py src/ui/demo_flow.py config/game_config.json src/game/scoring.py tests/
2026-06-16 | Plan v1 complete (single-device mock demo, 41 tests pass, mobile build OK). Catalogued remaining work (manual gates + deferred multiplayer/live-feed/simulated-events) in docs/remaining-work.md | docs/remaining-work.md log.md
2026-06-16 | Simulated events from real StatsBomb WC2018 data: pure adapter + ReplayFeed + 3 generated sim files (FRA-CRO final, FRA-BEL sf, BRA-BEL qf, all reconcile to real scores) + builder script + --sim play path. 52 tests pass | src/game/statsbomb_adapter.py src/game/replay_feed.py scripts/build_simulation_from_statsbomb.py assets/data/simulations/ src/ui/demo_flow.py src/main.py tests/
2026-06-16 | Full mobile-web UI: config-driven layout, splash/room/draft-zoom/play/cinematic/final screens, pure cinematic beat builder, SIM hotkeys+popup, dev ui_tweaker | config/layout_config.json src/game/cinematic.py src/ui/ TOOLS/ui_tweaker.py tests/
2026-06-16 | Headless full-flow smoke driver verifies both feed paths reach FinalScreen (20 windows replay, 3 windows mock) | TOOLS/smoke_flow.py
2026-06-19 | Prediction phase redesigned: predict all 5 stats with red->orange->green lock circles, Continue/Lock button (any subset, with feedback), bottom last-window results panel (both meter % + per-stat closeness/credit) via new pure WindowReport | config/game_config.json, config/layout_config.json, src/game/window_report.py, tests/test_window_report.py, src/ui/flow.py, src/ui/screens/play_screen.py
2026-06-19 | Results panel now reports the shot a fired meter earns: shooter name, role+conversion%, GOAL/no-goal (red on miss), plus raw meter "(N of T)". Threaded ShotOutcome from session through WindowReport | src/game/session.py, src/game/window_report.py, tests/test_window_report.py, src/ui/flow.py, src/ui/screens/play_screen.py
