<?php
// highscore.php -- per-game leaderboard for the Coop Soccer Predictor.
//
// Stores ONLY a self-chosen handle + scoreline (goals_for/goals_against) per game in a flat
// per-game JSON file. No tokens, no personal data -- safe for the public highscore.html page.
//
//   POST {game, username, goals_for, goals_against}  -> append + re-rank, returns the board
//   GET  ?game=NAME                                  -> that game's board (top N)
//   GET  (no game)                                   -> { games: { NAME: [entries...] } }
//
// Ranking (matches the in-game scoreline rule): goal difference DESC, then goals-for DESC.
// Each handle keeps only its BEST scoreline per game, so re-submitting cannot spam the board.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }

define('SCORES_DIR', __DIR__ . '/highscores/');
define('MAX_ENTRIES', 10);
if (!is_dir(SCORES_DIR)) { mkdir(SCORES_DIR, 0755, true); }

// Map a game label to a safe flat-file name (label kept inside the file for display).
function game_file(string $game): string {
    $slug = strtolower(preg_replace('/[^A-Za-z0-9]+/', '_', $game));
    $slug = trim($slug, '_');
    if ($slug === '') { $slug = 'game'; }
    return SCORES_DIR . 'hs_' . substr($slug, 0, 60) . '.json';
}

function read_board(string $game): array {
    $f = game_file($game);
    if (!file_exists($f)) { return []; }
    $c = json_decode(file_get_contents($f), true);
    return is_array($c) ? $c : [];
}

// goal difference DESC, then goals-for DESC; stable enough for a 10-row board.
function rank_board(array $entries): array {
    usort($entries, function ($a, $b) {
        $da = intval($a['goals_for']) - intval($a['goals_against']);
        $db = intval($b['goals_for']) - intval($b['goals_against']);
        if ($da !== $db) { return $db - $da; }
        return intval($b['goals_for']) - intval($a['goals_for']);
    });
    return array_slice($entries, 0, MAX_ENTRIES);
}

function respond(array $data, int $code = 200): void {
    http_response_code($code); echo json_encode($data); exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $in = json_decode(file_get_contents('php://input'), true);
    if (!$in || !isset($in['game']) || !isset($in['username'])) {
        respond(['error' => 'need game + username', 'success' => false], 400);
    }
    $game = substr(trim(strval($in['game'])), 0, 80);
    $user = substr(trim(strval($in['username'])), 0, 24);
    if ($user === '') { $user = 'anon'; }
    $gf = max(0, intval($in['goals_for'] ?? 0));
    $ga = max(0, intval($in['goals_against'] ?? 0));

    $board = read_board($game);
    // One row per handle: keep the better scoreline (by GD, then GF) if they replay.
    $kept = [];
    foreach ($board as $e) {
        if (strtolower($e['username']) !== strtolower($user)) { $kept[] = $e; }
    }
    $kept[] = ['username' => $user, 'goals_for' => $gf, 'goals_against' => $ga,
               'game' => $game, 'at' => time()];
    // If the handle already had a better line, rank_board would still keep the new one;
    // so compare and retain the stronger of the two.
    foreach ($board as $e) {
        if (strtolower($e['username']) === strtolower($user)) {
            $old_gd = intval($e['goals_for']) - intval($e['goals_against']);
            $new_gd = $gf - $ga;
            $better_old = ($old_gd > $new_gd)
                || ($old_gd === $new_gd && intval($e['goals_for']) > $gf);
            if ($better_old) { array_pop($kept); $kept[] = $e; }
        }
    }
    $ranked = rank_board($kept);
    file_put_contents(game_file($game), json_encode($ranked), LOCK_EX);
    respond(['success' => true, 'game' => $game, 'board' => $ranked]);
}

// GET
$game = isset($_GET['game']) ? strval($_GET['game']) : '';
if ($game !== '') {
    respond(['success' => true, 'game' => $game, 'board' => read_board($game)]);
}

// No game: return every board (used by highscore.html to render all games).
$games = [];
foreach (glob(SCORES_DIR . 'hs_*.json') as $f) {
    $entries = json_decode(file_get_contents($f), true);
    if (is_array($entries) && count($entries) > 0) {
        $label = $entries[0]['game'] ?? basename($f);
        $games[$label] = $entries;
    }
}
respond(['success' => true, 'games' => $games]);
