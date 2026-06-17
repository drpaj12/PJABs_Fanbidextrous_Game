# Change Log

Format: DATE | WHAT CHANGED | FILES TOUCHED
Append one line per session. Never delete old entries.

---

2026-06-15 | Project created from DarkWeb GameJam template | All files
2026-06-16 | API-Football smoke test script created; LIVE GATE PENDING (needs human API key + live match) - v1 defaults to MockFeed until verified | scripts/smoke_test_apifootball.py
2026-06-16 | Phase 5 mobile UI: widgets, async app, draft/predict/status screens, mock-feed demo flow, entry points wired | src/ui/*
2026-06-16 | pygbag mobile build OK (build-only); browser smoke-test PENDING (manual) | TOOLS/build_web_mobile.py
2026-06-16 | Post-review seam fix: api_field bridge now live (normalize_soccer.actuals_from_raw), yellow+red->cards, demo uses shared mapping, relay config reconciled, ScoreEvent.from_code guarded | src/game/normalize_soccer.py src/ui/demo_flow.py config/game_config.json src/game/scoring.py tests/
