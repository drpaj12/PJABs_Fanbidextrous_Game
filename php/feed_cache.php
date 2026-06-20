<?php
// feed_cache.php -- server-side proxy + cache of API-Football, served to both clients.
//
// Free tier is 100 requests/day, so this is written to be frugal:
//   * cache is PER FIXTURE (feed_cache_<id>.json) so several matches in a day do not
//     clobber each other,
//   * lineups are fetched ONCE per fixture and reused (they do not change after the XI
//     is published), so each refresh costs 2 upstream calls (statistics + fixture),
//   * a 180s TTL means ~15 refreshes over a 45-min half -> ~31 calls/game, ~93 for the
//     three World Cup games on a match day.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$CACHE_TTL = 180; // seconds; > the 120s client poll so cache hits dominate the quota
$fixture = preg_replace('/[^0-9]/', '', $_GET['fixture'] ?? '');
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable

if ($fixture === '') {
    http_response_code(400);
    echo '{"error":"missing fixture"}';
    exit;
}

$cacheFile   = __DIR__ . "/feed_cache_$fixture.json";
$lineupsFile = __DIR__ . "/lineups_$fixture.json";

if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}
if (!file_exists($keyFile)) {
    http_response_code(503);
    echo '{"error":"feed unavailable"}';
    exit;
}
$key = trim(file_get_contents($keyFile));
$base = "https://v3.football.api-sports.io";
$headers = ["x-apisports-key: $key"];

function api_get($url, $headers) {
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    $out = curl_exec($ch);
    curl_close($ch);
    return $out ? json_decode($out, true) : null;
}

// Lineups: reuse the persisted copy if we already have a non-empty XI for this fixture.
$lineups = null;
if (file_exists($lineupsFile)) {
    $cached = json_decode(file_get_contents($lineupsFile), true);
    if (!empty($cached['response'])) {
        $lineups = $cached;
    }
}
if ($lineups === null) {
    $lineups = api_get("$base/fixtures/lineups?fixture=$fixture", $headers);
    if (!empty($lineups['response'])) {
        file_put_contents($lineupsFile, json_encode($lineups), LOCK_EX);
    }
}

$snapshot = [
    "lineups"    => $lineups,
    "statistics" => api_get("$base/fixtures/statistics?fixture=$fixture", $headers),
    "fixture"    => api_get("$base/fixtures?id=$fixture", $headers),
    "cached_at"  => time(),
];
file_put_contents($cacheFile, json_encode($snapshot), LOCK_EX);
echo json_encode($snapshot);
