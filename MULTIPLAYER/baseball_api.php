<?php
/**
 * Baseball Card Battle - Multiplayer API
 * Version: 1.0.0
 *
 * Endpoints:
 *   GET  ?action=list                     - List all rooms
 *   POST ?action=join&room=N              - Join room N (0-3)
 *   GET  ?action=state&room=N&token=XXX   - Get game state
 *   POST ?action=update&room=N&token=XXX  - Update game state
 *   POST ?action=heartbeat&room=N&token=XXX - Keep connection alive
 *   POST ?action=leave&room=N&token=XXX   - Leave room
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Handle CORS preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// ==================== CONFIGURATION ====================

define('ROOMS_DIR', __DIR__ . '/game_rooms/');
define('MAX_ROOMS', 4);
define('TURN_TIMEOUT', 120);        // 2 minutes per turn
define('HEARTBEAT_TIMEOUT', 30);    // 30 seconds = disconnected
define('GAME_TIMEOUT', 3600);       // 1 hour max game
define('CLEANUP_AGE', 300);         // 5 min after game over = delete

// Ensure rooms directory exists
if (!is_dir(ROOMS_DIR)) {
    mkdir(ROOMS_DIR, 0755, true);
}

// ==================== UTILITY FUNCTIONS ====================

function generate_token(): string {
    return bin2hex(random_bytes(8));
}

function get_room_path(int $room): string {
    return ROOMS_DIR . "room_$room.json";
}

function read_room(int $room): ?array {
    $path = get_room_path($room);
    if (!file_exists($path)) {
        return null;
    }
    $content = file_get_contents($path);
    if ($content === false) {
        return null;
    }
    return json_decode($content, true);
}

function write_room(int $room, array $data): bool {
    $data['updated_at'] = time();
    $path = get_room_path($room);
    $result = file_put_contents(
        $path,
        json_encode($data, JSON_PRETTY_PRINT),
        LOCK_EX
    );
    return $result !== false;
}

function delete_room(int $room): bool {
    $path = get_room_path($room);
    if (file_exists($path)) {
        return unlink($path);
    }
    return true;
}

function create_empty_room(int $room): array {
    return [
        'room_id' => $room,
        'status' => 'empty',
        'created_at' => time(),
        'updated_at' => time(),
        'seed' => random_int(100000, 999999),
        'p1' => null,
        'p2' => null,
        'current_phase' => 'waiting',
        'current_turn' => 0,
        'turn_started_at' => null,
        'winner' => null,
        'final_score' => null
    ];
}

function create_player(string $token): array {
    return [
        'token' => $token,
        'joined_at' => time(),
        'last_heartbeat' => time(),
        'connected' => true,
        'team_id' => null,
        'team_name' => null,
        'pitcher_id' => null,
        'relief_id' => null,
        'manager_id' => null,
        'ready' => false,
        'turns_submitted' => [],
        'current_turn_ready' => false
    ];
}

function check_player_timeouts(array &$room): bool {
    $changed = false;
    $now = time();

    foreach (['p1', 'p2'] as $p) {
        if (isset($room[$p]) && $room[$p] !== null && $room[$p]['connected']) {
            if ($now - $room[$p]['last_heartbeat'] > HEARTBEAT_TIMEOUT) {
                $room[$p]['connected'] = false;
                $changed = true;
            }
        }
    }

    return $changed;
}

function cleanup_old_rooms(): void {
    $now = time();
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $data = read_room($i);
        if ($data) {
            $age = $now - $data['updated_at'];

            // Delete completed games after cleanup period
            if ($data['status'] === 'game_over' && $age > CLEANUP_AGE) {
                delete_room($i);
                continue;
            }

            // Delete stale games
            if ($age > GAME_TIMEOUT) {
                delete_room($i);
                continue;
            }

            // Reset abandoned waiting rooms
            if ($data['status'] === 'waiting' && $age > 300) {
                delete_room($i);
                continue;
            }
        }
    }
}

function respond(array $data, int $code = 200): void {
    http_response_code($code);
    echo json_encode($data);
    exit;
}

function error(string $message, int $code = 400): void {
    respond(['error' => $message, 'success' => false], $code);
}

function get_revealed_turns(array $room, int $my_player): array {
    $opponent = $my_player === 1 ? 'p2' : 'p1';
    $me = $my_player === 1 ? 'p1' : 'p2';

    if (!isset($room[$opponent]) || $room[$opponent] === null) {
        return [];
    }

    $revealed = [];
    $my_turns = $room[$me]['turns_submitted'] ?? [];
    $opp_turns = $room[$opponent]['turns_submitted'] ?? [];

    // Only reveal opponent turns that I've also submitted
    foreach ($opp_turns as $turn_num => $placements) {
        if (isset($my_turns[$turn_num])) {
            $revealed[$turn_num] = $placements;
        }
    }

    return $revealed;
}

// ==================== ACTION: LIST ====================

function action_list(): void {
    cleanup_old_rooms();

    $rooms = [];
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $data = read_room($i);

        if ($data) {
            check_player_timeouts($data);
            write_room($i, $data);

            $rooms[] = [
                'room_id' => $i,
                'status' => $data['status'],
                'phase' => $data['current_phase'],
                'p1_connected' => isset($data['p1']) && $data['p1'] !== null && $data['p1']['connected'],
                'p2_connected' => isset($data['p2']) && $data['p2'] !== null && $data['p2']['connected'],
                'p1_team' => $data['p1']['team_name'] ?? null,
                'p2_team' => $data['p2']['team_name'] ?? null,
                'current_turn' => $data['current_turn'],
                'age_seconds' => time() - $data['created_at'],
                'winner' => $data['winner'] ?? null,
                'final_score' => $data['final_score'] ?? null
            ];
        } else {
            $rooms[] = [
                'room_id' => $i,
                'status' => 'empty',
                'phase' => null,
                'p1_connected' => false,
                'p2_connected' => false,
                'p1_team' => null,
                'p2_team' => null,
                'current_turn' => 0,
                'age_seconds' => 0
            ];
        }
    }

    respond(['success' => true, 'rooms' => $rooms, 'server_time' => time()]);
}

// ==================== ACTION: JOIN ====================

function action_join(int $room): void {
    if ($room < 0 || $room >= MAX_ROOMS) {
        error('Invalid room number (must be 0-' . (MAX_ROOMS - 1) . ')');
    }

    $data = read_room($room);
    $token = generate_token();

    // Room empty or finished - create new and join as P1
    if (!$data || $data['status'] === 'empty' || $data['status'] === 'game_over') {
        $data = create_empty_room($room);
        $data['status'] = 'waiting';
        $data['current_phase'] = 'waiting';
        $data['p1'] = create_player($token);
        write_room($room, $data);

        respond([
            'success' => true,
            'token' => $token,
            'player' => 1,
            'role' => 'home',
            'seed' => $data['seed'],
            'message' => 'Created room. Waiting for opponent...'
        ]);
    }

    check_player_timeouts($data);

    // Block joins once a game is in progress (playing or resolving)
    $in_progress = in_array($data['current_phase'], ['playing', 'resolving']);
    if ($in_progress) {
        error('Game in progress. Try another room.', 409);
    }

    $p1_active = isset($data['p1']) && $data['p1'] !== null && $data['p1']['connected'];
    $p2_active = isset($data['p2']) && $data['p2'] !== null && $data['p2']['connected'];
    $p2_exists = isset($data['p2']) && $data['p2'] !== null;

    if ($p1_active && !$p2_exists) {
        $data['p2'] = create_player($token);
        $data['status'] = 'active';
        $data['current_phase'] = 'team_select';
        write_room($room, $data);

        respond([
            'success' => true,
            'token' => $token,
            'player' => 2,
            'role' => 'away',
            'seed' => $data['seed'],
            'message' => 'Joined as Player 2. Select your team!'
        ]);
    }

    if (!$p1_active && $p2_active) {
        $data['p1'] = create_player($token);
        $data['status'] = 'active';
        if ($data['current_phase'] === 'waiting') {
            $data['current_phase'] = 'team_select';
        }
        write_room($room, $data);

        respond([
            'success' => true,
            'token' => $token,
            'player' => 1,
            'role' => 'home',
            'seed' => $data['seed'],
            'message' => 'Took over Player 1 slot.'
        ]);
    }

    if ($p1_active && !$p2_active && $p2_exists) {
        $data['p2'] = create_player($token);
        write_room($room, $data);

        respond([
            'success' => true,
            'token' => $token,
            'player' => 2,
            'role' => 'away',
            'seed' => $data['seed'],
            'message' => 'Took over Player 2 slot.'
        ]);
    }

    error('Room is full. Try another room.', 409);
}

// ==================== ACTION: STATE ====================

function action_state(int $room, string $token): void {
    $data = read_room($room);
    if (!$data) {
        error('Room not found', 404);
    }

    $player = null;
    if (isset($data['p1']) && $data['p1'] !== null && $data['p1']['token'] === $token) {
        $player = 1;
    } elseif (isset($data['p2']) && $data['p2'] !== null && $data['p2']['token'] === $token) {
        $player = 2;
    } else {
        error('Invalid token', 403);
    }

    check_player_timeouts($data);
    write_room($room, $data);

    $me = $player === 1 ? 'p1' : 'p2';
    $opponent = $player === 1 ? 'p2' : 'p1';

    $opp_data = $data[$opponent];
    $my_data = $data[$me];

    $turn_time_remaining = TURN_TIMEOUT;
    if ($data['turn_started_at']) {
        $turn_time_remaining = max(0, TURN_TIMEOUT - (time() - $data['turn_started_at']));
    }

    $response = [
        'success' => true,
        'room_id' => $room,
        'status' => $data['status'],
        'phase' => $data['current_phase'],
        'seed' => $data['seed'],
        'current_turn' => $data['current_turn'],
        'turn_started_at' => $data['turn_started_at'],
        'turn_time_remaining' => $turn_time_remaining,
        'my_player' => $player,
        'winner' => $data['winner'],
        'final_score' => $data['final_score'],
        'resolution_data' => $data['resolution_data'] ?? null,
        'pitcher_sync' => $data['pitcher_sync'] ?? null,
        'server_time' => time(),

        'me' => [
            'connected' => $my_data['connected'] ?? false,
            'team_id' => $my_data['team_id'] ?? null,
            'team_name' => $my_data['team_name'] ?? null,
            'pitcher_id' => $my_data['pitcher_id'] ?? null,
            'relief_id' => $my_data['relief_id'] ?? null,
            'manager_id' => $my_data['manager_id'] ?? null,
            'ready' => $my_data['ready'] ?? false,
            'current_turn_ready' => $my_data['current_turn_ready'] ?? false,
            'turns_submitted' => $my_data['turns_submitted'] ?? []
        ],

        'opponent' => [
            'connected' => $opp_data['connected'] ?? false,
            'team_id' => $opp_data['team_id'] ?? null,
            'team_name' => $opp_data['team_name'] ?? null,
            'pitcher_id' => $opp_data['pitcher_id'] ?? null,
            'relief_id' => $opp_data['relief_id'] ?? null,
            'manager_id' => $opp_data['manager_id'] ?? null,
            'ready' => $opp_data['ready'] ?? false,
            'current_turn_ready' => $opp_data['current_turn_ready'] ?? false,
            'turns_submitted' => get_revealed_turns($data, $player)
        ]
    ];

    respond($response);
}

// ==================== ACTION: UPDATE ====================

function action_update(int $room, string $token): void {
    $data = read_room($room);
    if (!$data) {
        error('Room not found', 404);
    }

    $player = null;
    $player_key = null;
    if (isset($data['p1']) && $data['p1'] !== null && $data['p1']['token'] === $token) {
        $player = 1;
        $player_key = 'p1';
    } elseif (isset($data['p2']) && $data['p2'] !== null && $data['p2']['token'] === $token) {
        $player = 2;
        $player_key = 'p2';
    } else {
        error('Invalid token', 403);
    }

    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['type'])) {
        error('Invalid request body - must be JSON with "type" field');
    }

    $data[$player_key]['last_heartbeat'] = time();
    $data[$player_key]['connected'] = true;

    $update_type = $input['type'];

    switch ($update_type) {

        case 'team_select':
            if ($data['current_phase'] !== 'team_select') {
                error('Not in team select phase');
            }
            if (!isset($input['team_id']) || !isset($input['team_name'])) {
                error('Missing team_id or team_name');
            }

            $data[$player_key]['team_id'] = intval($input['team_id']);
            $data[$player_key]['team_name'] = strval($input['team_name']);

            $p1_ready = isset($data['p1']['team_id']) && $data['p1']['team_id'] !== null;
            $p2_ready = isset($data['p2']['team_id']) && $data['p2']['team_id'] !== null;

            if ($p1_ready && $p2_ready) {
                $data['current_phase'] = 'pitcher_select';
            }
            break;

        case 'pitcher_select':
            if ($data['current_phase'] !== 'pitcher_select') {
                error('Not in pitcher select phase');
            }
            if (!isset($input['pitcher_id'])) {
                error('Missing pitcher_id');
            }

            $data[$player_key]['pitcher_id'] = intval($input['pitcher_id']);
            $data[$player_key]['relief_id'] = isset($input['relief_id']) ? intval($input['relief_id']) : null;
            $data[$player_key]['manager_id'] = isset($input['manager_id']) ? intval($input['manager_id']) : null;

            $p1_ready = isset($data['p1']['pitcher_id']) && $data['p1']['pitcher_id'] !== null;
            $p2_ready = isset($data['p2']['pitcher_id']) && $data['p2']['pitcher_id'] !== null;

            if ($p1_ready && $p2_ready) {
                $data['current_phase'] = 'playing';
                $data['current_turn'] = 1;
                $data['turn_started_at'] = time();
            }
            break;

        case 'turn_submit':
            if ($data['current_phase'] !== 'playing') {
                error('Not in playing phase');
            }
            if (!isset($input['turn']) || !isset($input['placements'])) {
                error('Missing turn or placements');
            }

            $turn_num = intval($input['turn']);
            if ($turn_num !== $data['current_turn']) {
                error("Wrong turn number. Expected {$data['current_turn']}, got $turn_num");
            }

            $data[$player_key]['turns_submitted'][$turn_num] = $input['placements'];
            $data[$player_key]['current_turn_ready'] = true;

            $p1_ready = $data['p1']['current_turn_ready'] ?? false;
            $p2_ready = $data['p2']['current_turn_ready'] ?? false;

            if ($p1_ready && $p2_ready) {
                $data['p1']['current_turn_ready'] = false;
                $data['p2']['current_turn_ready'] = false;

                if ($data['current_turn'] >= 6) {
                    $data['current_phase'] = 'resolving';
                } else {
                    $data['current_turn']++;
                    $data['turn_started_at'] = time();
                }
            }
            break;

        case 'game_result':
            if ($data['current_phase'] !== 'resolving' && $data['current_phase'] !== 'game_over') {
                error('Not in resolving phase');
            }

            $data['current_phase'] = 'game_over';
            $data['status'] = 'game_over';
            $data['winner'] = isset($input['winner']) ? intval($input['winner']) : 0;
            $data['final_score'] = $input['score'] ?? [0, 0];
            // Store full resolution data so P2 can use P1's results
            if (isset($input['resolution_data'])) {
                $data['resolution_data'] = $input['resolution_data'];
            }
            // Store pitcher fatigue orders + face-up state so P2's display matches
            if (isset($input['pitcher_sync'])) {
                $data['pitcher_sync'] = $input['pitcher_sync'];
            }
            break;

        default:
            error("Unknown update type: $update_type");
    }

    write_room($room, $data);
    respond([
        'success' => true,
        'phase' => $data['current_phase'],
        'current_turn' => $data['current_turn']
    ]);
}

// ==================== ACTION: HEARTBEAT ====================

function action_heartbeat(int $room, string $token): void {
    $data = read_room($room);
    if (!$data) {
        error('Room not found', 404);
    }

    $player_key = null;
    if (isset($data['p1']) && $data['p1'] !== null && $data['p1']['token'] === $token) {
        $player_key = 'p1';
    } elseif (isset($data['p2']) && $data['p2'] !== null && $data['p2']['token'] === $token) {
        $player_key = 'p2';
    } else {
        error('Invalid token', 403);
    }

    $data[$player_key]['last_heartbeat'] = time();
    $data[$player_key]['connected'] = true;

    check_player_timeouts($data);
    write_room($room, $data);

    respond(['success' => true, 'server_time' => time()]);
}

// ==================== ACTION: LEAVE ====================

function action_leave(int $room, string $token): void {
    $data = read_room($room);
    if (!$data) {
        respond(['success' => true, 'message' => 'Room already empty']);
        return;
    }

    $player_key = null;
    $player_num = 0;
    if (isset($data['p1']) && $data['p1'] !== null && $data['p1']['token'] === $token) {
        $player_key = 'p1';
        $player_num = 1;
        $data['p1']['connected'] = false;
    } elseif (isset($data['p2']) && $data['p2'] !== null && $data['p2']['token'] === $token) {
        $player_key = 'p2';
        $player_num = 2;
        $data['p2']['connected'] = false;
    }

    $p1_connected = isset($data['p1']) && $data['p1'] !== null && $data['p1']['connected'];
    $p2_connected = isset($data['p2']) && $data['p2'] !== null && $data['p2']['connected'];

    if (!$p1_connected && !$p2_connected) {
        $data['status'] = 'game_over';
        $data['current_phase'] = 'game_over';
        $data['winner'] = 0;
    } elseif ($data['current_phase'] === 'playing' || $data['current_phase'] === 'resolving') {
        $data['status'] = 'game_over';
        $data['current_phase'] = 'game_over';
        $data['winner'] = $player_num === 1 ? 2 : 1;
    }

    write_room($room, $data);
    respond(['success' => true, 'message' => 'Left room']);
}

// ==================== ROUTER ====================

$action = $_GET['action'] ?? '';
$room = isset($_GET['room']) ? intval($_GET['room']) : -1;
$token = $_GET['token'] ?? '';

switch ($action) {
    case 'list':
        action_list();
        break;

    case 'join':
        action_join($room);
        break;

    case 'state':
        action_state($room, $token);
        break;

    case 'update':
        action_update($room, $token);
        break;

    case 'heartbeat':
        action_heartbeat($room, $token);
        break;

    case 'leave':
        action_leave($room, $token);
        break;

    case 'reset':
        // Force-clear a room (admin/debug)
        if ($room >= 0 && $room < MAX_ROOMS) {
            delete_room($room);
            respond(['success' => true, 'message' => "Room $room reset"]);
        } else {
            error('Invalid room number');
        }
        break;

    case 'reset_all':
        // Force-clear all rooms (admin/debug)
        for ($i = 0; $i < MAX_ROOMS; $i++) {
            delete_room($i);
        }
        respond(['success' => true, 'message' => 'All rooms reset']);
        break;

    case '':
        respond([
            'name' => 'Baseball Card Battle Multiplayer API',
            'version' => '1.0.0',
            'endpoints' => [
                'GET ?action=list' => 'List all rooms',
                'POST ?action=join&room=N' => 'Join room N (0-3)',
                'GET ?action=state&room=N&token=XXX' => 'Get game state',
                'POST ?action=update&room=N&token=XXX' => 'Update game (body: JSON)',
                'POST ?action=heartbeat&room=N&token=XXX' => 'Keep alive',
                'POST ?action=leave&room=N&token=XXX' => 'Leave room',
                'POST ?action=reset&room=N' => 'Force-reset room (admin)',
                'POST ?action=reset_all' => 'Force-reset all rooms (admin)'
            ]
        ]);
        break;

    default:
        error("Unknown action: $action");
}
