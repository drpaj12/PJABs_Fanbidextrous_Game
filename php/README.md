# PHP Relay -- PJAB Coop Soccer Game

Adapted from MULTIPLAYER/baseball_api.php. Deploy `soccer_api.php`, `feed_cache.php`, and the
two `.htaccess` files to `drpeterjamieson.com/game/` via SFTP. A writable `game_rooms/`
directory sits beside them (auto-created; the `.htaccess` there denies direct JSON access).

## soccer_api.php (room/token/action)
- GET  `?action=list`                      -> room summaries
- POST `?action=join&room=N`               -> `{token, player, seed}`
- GET  `?action=state&room=N&token=T`      -> blind-revealed game state
- POST `?action=update&room=N&token=T`     -> body `{type, ...}`:
  - `{type:"draft_submit", athlete_ids:[...]}`   (phase: draft)
  - `{type:"window_submit", window, predictions:[...], active_id, use_power}` (phase: playing)
  - `{type:"score_event", code:"slot:window:side:scored"}`
  - `{type:"game_result", final_score:[team, opp]}`
- POST `?action=heartbeat&room=N&token=T`  -> keep alive (30s timeout)
- POST `?action=leave&room=N&token=T`      -> disconnect

Blind reveal: `state` only returns an opponent's window once you have submitted the same
window number. Rooms self-clean (completed after 5 min, stale after 1 h).

## feed_cache.php
- GET `?fixture=ID` -> cached API-Football snapshot, refreshed at most once per CACHE_TTL.
  API key read from `apifootball_key.txt` (NOT web-readable).

Keep payloads small: only drafts, window predictions, and score-event codes are stored.
