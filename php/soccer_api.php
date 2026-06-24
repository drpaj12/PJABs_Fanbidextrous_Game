<?php
/**
 * PJAB Coop Soccer - Multiplayer Relay
 * Adapted from baseball_api.php. Co-op: both players build one shared team score.
 *
 * Endpoints:
 *   GET  ?action=list                       - list rooms
 *   POST ?action=join&room=N                - join/create room N
 *   GET  ?action=state&room=N&token=XXX     - get game state (blind-revealed)
 *   POST ?action=update&room=N&token=XXX    - update (JSON body with "type")
 *   POST ?action=heartbeat&room=N&token=XXX - keep alive
 *   POST ?action=leave&room=N&token=XXX     - leave
 *
 * update types: draft_submit, window_submit, score_event, game_result
 */
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }

define('ROOMS_DIR', __DIR__ . '/game_rooms/');
define('MAX_ROOMS', 4);
define('HEARTBEAT_TIMEOUT', 30);
define('GAME_TIMEOUT', 3600);
define('CLEANUP_AGE', 300);

if (!is_dir(ROOMS_DIR)) { mkdir(ROOMS_DIR, 0755, true); }

function generate_token(): string { return bin2hex(random_bytes(8)); }
function get_room_path(int $room): string { return ROOMS_DIR . "room_$room.json"; }

function read_room(int $room): ?array {
    $path = get_room_path($room);
    if (!file_exists($path)) { return null; }
    $c = file_get_contents($path);
    return $c === false ? null : json_decode($c, true);
}

function write_room(int $room, array $data): bool {
    $data['updated_at'] = time();
    return file_put_contents(get_room_path($room),
        json_encode($data, JSON_PRETTY_PRINT), LOCK_EX) !== false;
}

function delete_room(int $room): bool {
    $path = get_room_path($room);
    return file_exists($path) ? unlink($path) : true;
}

function create_empty_room(int $room): array {
    return [
        'room_id' => $room, 'status' => 'empty',
        'created_at' => time(), 'updated_at' => time(),
        'seed' => random_int(100000, 999999),
        'p1' => null, 'p2' => null,
        'current_phase' => 'waiting', 'current_window' => 0,
        'window_started_at' => null,
        'score_events' => [], 'final_score' => null,
    ];
}

function create_player(string $token): array {
    return [
        'token' => $token, 'joined_at' => time(), 'last_heartbeat' => time(),
        'connected' => true, 'athlete_ids' => null,
        'windows_submitted' => [], 'current_window_ready' => false,
    ];
}

function check_player_timeouts(array &$room): bool {
    $changed = false; $now = time();
    foreach (['p1', 'p2'] as $p) {
        if (isset($room[$p]) && $room[$p] !== null && $room[$p]['connected']) {
            if ($now - $room[$p]['last_heartbeat'] > HEARTBEAT_TIMEOUT) {
                $room[$p]['connected'] = false; $changed = true;
            }
        }
    }
    return $changed;
}

function cleanup_old_rooms(): void {
    $now = time();
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $d = read_room($i);
        if (!$d) { continue; }
        $age = $now - $d['updated_at'];
        if ($d['status'] === 'game_over' && $age > CLEANUP_AGE) { delete_room($i); continue; }
        if ($age > GAME_TIMEOUT) { delete_room($i); continue; }
        if ($d['status'] === 'waiting' && $age > 300) { delete_room($i); continue; }
    }
}

function respond(array $data, int $code = 200): void {
    http_response_code($code); echo json_encode($data); exit;
}
function fail(string $msg, int $code = 400): void {
    respond(['error' => $msg, 'success' => false], $code);
}

// Blind reveal: only show an opponent window I have also submitted.
function get_revealed_windows(array $room, int $my_player): array {
    $opp = $my_player === 1 ? 'p2' : 'p1';
    $me = $my_player === 1 ? 'p1' : 'p2';
    if (!isset($room[$opp]) || $room[$opp] === null) { return []; }
    $revealed = [];
    $mine = $room[$me]['windows_submitted'] ?? [];
    $theirs = $room[$opp]['windows_submitted'] ?? [];
    foreach ($theirs as $w => $payload) {
        if (isset($mine[$w])) { $revealed[$w] = $payload; }
    }
    return $revealed;
}

// -------------------------------------------------------------------------
// Party helpers (per-player economy blob; mirrors Python Party.to_dict())
// -------------------------------------------------------------------------
define('MAX_PARTIES', 4);
define('PARTY_MAX_SIZE', 3);

function get_party_path(int $party): string { return ROOMS_DIR . "party_$party.json"; }

function read_party(int $party): ?array {
    $path = get_party_path($party);
    if (!file_exists($path)) { return null; }
    $c = file_get_contents($path);
    return $c === false ? null : json_decode($c, true);
}

function write_party(int $party, array $data): bool {
    $data['updated_at'] = time();
    // Keep window_picks as a JSON object ({}) even when empty.
    if (isset($data['window_picks']) && is_array($data['window_picks'])
            && count($data['window_picks']) === 0) {
        $data['window_picks'] = new stdClass();
    }
    return file_put_contents(get_party_path($party),
        json_encode($data, JSON_PRETTY_PRINT), LOCK_EX) !== false;
}

function norm_user(string $u): string { return strtolower(trim($u)); }

function create_empty_party(int $party, string $leader): array {
    return [
        'party_id'   => $party,
        'leader'     => $leader,
        'phase'      => 'lobby',
        'half'       => 1,
        'fixture_id' => 0,
        'kickoff_iso' => '',
        'match' => [
            'home' => '', 'away' => '',
            'home_goals' => 0, 'away_goals' => 0,
            'minute' => 0, 'status' => 'NS',
        ],
        'pool'    => [],
        'members' => [[
            'username' => $leader, 'slot' => 0, 'items' => [],
            'treasury' => 0, 'ready' => false, 'alive' => true, 'wounds' => 0,
        ]],
        'dungeon'                   => null,
        'log'                       => [],
        'window_colors'             => [],
        'resolved_through_window'   => 0,
        'window_picks'              => new stdClass(),
        // Peer-computed co-op: creator-set RNG seed (null until set) and the api-lead's frozen
        // per-window input bundles ({window: {actuals, lines, use}}) that every client replays.
        'seed'                      => null,
        'window_actuals'            => new stdClass(),
    ];
}

function party_member_index(array $p, string $user): int {
    foreach ($p['members'] as $i => $m) {
        if (norm_user($m['username']) === $user) { return $i; }
    }
    return -1;
}

// -------------------------------------------------------------------------
// Party action handlers
// -------------------------------------------------------------------------

function action_party_join(int $party): void {
    if ($party < 0 || $party >= MAX_PARTIES) { fail('Invalid party number'); }
    $input = json_decode(file_get_contents('php://input'), true);
    $user  = norm_user($input['username'] ?? '');
    if ($user === '') { fail('Missing username'); }

    $p = read_party($party);
    if (!$p) {
        $p = create_empty_party($party, $user);
        write_party($party, $p);
        respond(['success' => true, 'slot' => 0, 'is_leader' => true]);
    }

    $idx = party_member_index($p, $user);
    if ($idx >= 0) {
        respond([
            'success'   => true,
            'slot'      => (int)$p['members'][$idx]['slot'],
            'is_leader' => (norm_user($p['leader']) === $user),
        ]);
    }

    if (count($p['members']) >= PARTY_MAX_SIZE) { fail('Party is full', 409); }
    $slot = count($p['members']);
    $p['members'][] = [
        'username' => $user, 'slot' => $slot, 'items' => [],
        'treasury' => 0, 'ready' => false, 'alive' => true, 'wounds' => 0,
    ];
    write_party($party, $p);
    respond(['success' => true, 'slot' => $slot, 'is_leader' => false]);
}

function action_party_state(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    respond(['success' => true, 'party' => $p]);
}

function action_party_pick(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);
    $idx   = party_member_index($p, norm_user($input['username'] ?? ''));
    if ($idx < 0) { fail('Not a member', 403); }

    $slot  = (string)$p['members'][$idx]['slot'];
    $picks = (array)($p['window_picks'] ?? []);
    $picks[$slot] = [
        'w'     => (int)($input['window'] ?? 0),
        'preds' => array_values((array)($input['preds'] ?? [])),
        'use'   => array_values((array)($input['use'] ?? [])),
    ];
    $p['window_picks'] = $picks;
    write_party($party, $p);
    respond(['success' => true]);
}

function action_party_loadout(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);
    $idx   = party_member_index($p, norm_user($input['username'] ?? ''));
    if ($idx < 0) { fail('Not a member', 403); }

    $p['members'][$idx]['items']    = array_values((array)($input['item_ids'] ?? []));
    $p['members'][$idx]['treasury'] = (int)($input['treasury'] ?? 0);
    $p['members'][$idx]['ready']    = true;
    write_party($party, $p);
    respond(['success' => true]);
}

function action_party_push(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);

    if (norm_user($input['username'] ?? '') !== norm_user($p['leader'])) {
        fail('Only the leader may push state', 403);
    }

    foreach (['phase', 'half', 'fixture_id', 'kickoff_iso', 'match', 'pool', 'members',
              'dungeon', 'log', 'window_colors', 'resolved_through_window',
              'seed', 'window_actuals'] as $key) {
        if (array_key_exists($key, $input)) { $p[$key] = $input[$key]; }
    }
    if (!empty($input['clear_picks'])) { $p['window_picks'] = new stdClass(); }
    write_party($party, $p);
    respond(['success' => true]);
}

// -------------------------------------------------------------------------
// Room action handlers
// -------------------------------------------------------------------------

function action_list(): void {
    cleanup_old_rooms();
    $rooms = [];
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $d = read_room($i);
        if ($d) {
            check_player_timeouts($d); write_room($i, $d);
            $rooms[] = [
                'room_id' => $i, 'status' => $d['status'], 'phase' => $d['current_phase'],
                'p1_connected' => isset($d['p1']) && $d['p1'] !== null && $d['p1']['connected'],
                'p2_connected' => isset($d['p2']) && $d['p2'] !== null && $d['p2']['connected'],
                'current_window' => $d['current_window'],
                'age_seconds' => time() - $d['created_at'],
            ];
        } else {
            $rooms[] = ['room_id' => $i, 'status' => 'empty', 'phase' => null,
                        'p1_connected' => false, 'p2_connected' => false,
                        'current_window' => 0, 'age_seconds' => 0];
        }
    }
    respond(['success' => true, 'rooms' => $rooms, 'server_time' => time()]);
}

function action_join(int $room): void {
    if ($room < 0 || $room >= MAX_ROOMS) { fail('Invalid room number'); }
    $d = read_room($room);
    $token = generate_token();

    if (!$d || $d['status'] === 'empty' || $d['status'] === 'game_over') {
        $d = create_empty_room($room);
        $d['status'] = 'waiting'; $d['current_phase'] = 'waiting';
        $d['p1'] = create_player($token);
        write_room($room, $d);
        respond(['success' => true, 'token' => $token, 'player' => 1,
                 'seed' => $d['seed'], 'message' => 'Created room. Waiting for partner...']);
    }

    check_player_timeouts($d);
    if (in_array($d['current_phase'], ['playing', 'resolving'])) {
        fail('Game in progress. Try another room.', 409);
    }
    $p2_exists = isset($d['p2']) && $d['p2'] !== null;
    if (!$p2_exists) {
        $d['p2'] = create_player($token);
        $d['status'] = 'active'; $d['current_phase'] = 'draft';
        write_room($room, $d);
        respond(['success' => true, 'token' => $token, 'player' => 2,
                 'seed' => $d['seed'], 'message' => 'Joined as Player 2. Draft your six!']);
    }
    fail('Room is full. Try another room.', 409);
}

function resolve_player(array $d, string $token): array {
    if (isset($d['p1']) && $d['p1'] !== null && $d['p1']['token'] === $token) {
        return [1, 'p1'];
    }
    if (isset($d['p2']) && $d['p2'] !== null && $d['p2']['token'] === $token) {
        return [2, 'p2'];
    }
    fail('Invalid token', 403);
}

function action_state(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $me_key] = resolve_player($d, $token);
    check_player_timeouts($d); write_room($room, $d);
    $opp_key = $player === 1 ? 'p2' : 'p1';
    $me = $d[$me_key]; $opp = $d[$opp_key];

    respond([
        'success' => true, 'room_id' => $room, 'status' => $d['status'],
        'phase' => $d['current_phase'], 'seed' => $d['seed'],
        'current_window' => $d['current_window'],
        'window_started_at' => $d['window_started_at'],
        'my_player' => $player, 'score_events' => $d['score_events'] ?? [],
        'final_score' => $d['final_score'], 'server_time' => time(),
        'me' => [
            'connected' => $me['connected'] ?? false,
            'athlete_ids' => $me['athlete_ids'] ?? null,
            'current_window_ready' => $me['current_window_ready'] ?? false,
            'windows_submitted' => $me['windows_submitted'] ?? [],
        ],
        'opponent' => [
            'connected' => $opp['connected'] ?? false,
            'athlete_ids' => $opp['athlete_ids'] ?? null,
            'current_window_ready' => $opp['current_window_ready'] ?? false,
            'windows_submitted' => get_revealed_windows($d, $player),
        ],
    ]);
}

function action_update(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $pk] = resolve_player($d, $token);
    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['type'])) { fail('Body must be JSON with "type"'); }

    $d[$pk]['last_heartbeat'] = time();
    $d[$pk]['connected'] = true;

    switch ($input['type']) {
        case 'draft_submit':
            if ($d['current_phase'] !== 'draft') { fail('Not in draft phase'); }
            if (!isset($input['athlete_ids']) || !is_array($input['athlete_ids'])) {
                fail('Missing athlete_ids');
            }
            $d[$pk]['athlete_ids'] = array_map('strval', $input['athlete_ids']);
            $p1r = isset($d['p1']['athlete_ids']) && $d['p1']['athlete_ids'] !== null;
            $p2r = isset($d['p2']['athlete_ids']) && $d['p2']['athlete_ids'] !== null;
            if ($p1r && $p2r) {
                $d['current_phase'] = 'playing';
                $d['current_window'] = 1;
                $d['window_started_at'] = time();
            }
            break;

        case 'window_submit':
            if ($d['current_phase'] !== 'playing') { fail('Not in playing phase'); }
            if (!isset($input['window']) || !isset($input['predictions'])) {
                fail('Missing window or predictions');
            }
            $w = strval(intval($input['window']));
            $d[$pk]['windows_submitted'][$w] = [
                'predictions' => $input['predictions'],
                'active_id' => strval($input['active_id'] ?? ''),
                'use_power' => (bool)($input['use_power'] ?? false),
            ];
            $d[$pk]['current_window_ready'] = true;
            $p1r = $d['p1']['current_window_ready'] ?? false;
            $p2r = $d['p2']['current_window_ready'] ?? false;
            if ($p1r && $p2r) {
                $d['p1']['current_window_ready'] = false;
                $d['p2']['current_window_ready'] = false;
                $d['current_window']++;
                $d['window_started_at'] = time();
            }
            break;

        case 'score_event':
            if (!isset($input['code'])) { fail('Missing code'); }
            $code = strval($input['code']);
            if (!in_array($code, $d['score_events'], true)) {
                $d['score_events'][] = $code;
            }
            break;

        case 'game_result':
            $d['current_phase'] = 'game_over';
            $d['status'] = 'game_over';
            $d['final_score'] = $input['final_score'] ?? [0, 0];
            break;

        default:
            fail('Unknown update type: ' . $input['type']);
    }

    write_room($room, $d);
    respond(['success' => true, 'phase' => $d['current_phase'],
             'current_window' => $d['current_window']]);
}

function action_heartbeat(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $pk] = resolve_player($d, $token);
    $d[$pk]['last_heartbeat'] = time();
    $d[$pk]['connected'] = true;
    check_player_timeouts($d); write_room($room, $d);
    respond(['success' => true, 'server_time' => time()]);
}

function action_leave(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { respond(['success' => true, 'message' => 'Room already empty']); }
    [$player, $pk] = resolve_player($d, $token);
    $d[$pk]['connected'] = false;
    $p1c = isset($d['p1']) && $d['p1'] !== null && $d['p1']['connected'];
    $p2c = isset($d['p2']) && $d['p2'] !== null && $d['p2']['connected'];
    if (!$p1c && !$p2c) {
        $d['status'] = 'game_over'; $d['current_phase'] = 'game_over';
    }
    write_room($room, $d);
    respond(['success' => true, 'message' => 'Left room']);
}

$action = $_GET['action'] ?? '';
$room   = isset($_GET['room'])  ? intval($_GET['room'])  : -1;
$party  = isset($_GET['party']) ? intval($_GET['party']) : -1;
$token  = $_GET['token'] ?? '';

switch ($action) {
    case 'list':      action_list(); break;
    case 'join':      action_join($room); break;
    case 'state':     action_state($room, $token); break;
    case 'update':    action_update($room, $token); break;
    case 'heartbeat': action_heartbeat($room, $token); break;
    case 'leave':     action_leave($room, $token); break;
    case 'reset':
        if ($room >= 0 && $room < MAX_ROOMS) {
            delete_room($room);
            respond(['success' => true, 'message' => "Room $room reset"]);
        }
        fail('Invalid room number');
        break;
    // --- Party actions (per-player economy; co-op multiplayer) ---
    case 'party_join':     action_party_join($party); break;
    case 'party_state':    action_party_state($party); break;
    case 'party_pick':     action_party_pick($party); break;
    case 'party_loadout':  action_party_loadout($party); break;
    case 'party_push':     action_party_push($party); break;
    case '':
        respond(['name' => 'PJAB Coop Soccer Relay', 'version' => '1.1.0',
                 'endpoints' => [
                     'list', 'join', 'state', 'update', 'heartbeat', 'leave',
                     'party_join', 'party_state', 'party_pick', 'party_loadout', 'party_push',
                 ]]);
        break;
    default: fail("Unknown action: $action");
}
