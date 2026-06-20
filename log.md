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
2026-06-19 | half-game flow: pre-game lobby + 9 windows + extra-time window (poll to half-time) + Half-Time summary | flow.py half_clock.py mock_feed.py replay_feed.py pregame_screen.py play_screen.py status_screens.py smoke_flow.py config
2026-06-19 | move pre-game fixture fallbacks + start-button label into config (no-magic-numbers cleanup) | game_config.json flow.py pregame_screen.py
2026-06-19 | LIVE single-player: LiveFeed team-name accessors + LiveWaitScreen (wall-clock relay polling, fires on lineups/minute/halftime) + LiveFlow (drives draft + remaining-half scored windows off live_plan, waits out each window before resolving) + --live entry point. Verified: 108 tests green, headless drive of all four new transitions | src/game/live_feed.py src/ui/screens/live_wait_screen.py src/ui/flow.py src/main.py tests/test_live_feed.py
2026-06-19 | Match-day live prep: working API key validated (free tier 100/day); FixtureSelectScreen + flow.start_live_select wire the 3 World Cup 2026-06-20 fixtures (Netherlands-Sweden 1539007, Germany-Ivory Coast 1489393, Turkiye-Paraguay 1539006); web entry now launches the live picker; relay made quota-safe (per-fixture cache, lineups fetched once, 180s TTL) + .htaccess denies .txt/.json. Verified LiveFeed parses real API JSON (22-player pool). | config/game_config.json src/ui/screens/fixture_select_screen.py src/ui/flow.py src/main.py main.py php/feed_cache.php php/.htaccess
2026-06-19 | Match-day deploy package: mirrored fresh web client (start_live_select, fixtures 1539007/1489393/1539006, correct PROJECTS/PREDICTOR relay path) into PREDICTOR twin; rebuilt PREDICTOR_deploy.zip (12 files, 124KB) with quota-safe feed_cache.php + hardened .htaccess + valid key; updated DEPLOY_README notes 1&2 (now done, not TODO) | WEB_BUILD/PREDICTOR/ WEB_BUILD/PREDICTOR_deploy.zip log.md
