<?php
// feed_cache.php -- server-side proxy + cache of API-Football, served to both clients.
// Refreshes at most once per CACHE_TTL seconds so the shared free-tier quota is not doubled.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$CACHE_TTL = 110; // seconds; just under the client 120s poll cadence
$cacheFile = __DIR__ . '/feed_cache.json';
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable

$fixture = preg_replace('/[^0-9]/', '', $_GET['fixture'] ?? '');

if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}
if (!file_exists($keyFile) || $fixture === '') {
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

$snapshot = [
    "lineups"    => api_get("$base/fixtures/lineups?fixture=$fixture", $headers),
    "statistics" => api_get("$base/fixtures/statistics?fixture=$fixture", $headers),
    "fixture"    => api_get("$base/fixtures?id=$fixture", $headers),
    "cached_at"  => time(),
];
file_put_contents($cacheFile, json_encode($snapshot), LOCK_EX);
echo json_encode($snapshot);
