<?php
// feed_cache.php -- server-side proxy + cache of API-Football, served to every client.
//
// Quota design (free tier = 100 requests/day):
//   * cache is PER FIXTURE (feed_cache_<id>.json),
//   * ONLY the lead client (?lead=1) is allowed to spend upstream calls; every other
//     client reads whatever is cached and never touches API-Football. This bounds the
//     day's usage to a SINGLE client's poll rate no matter how many people join,
//   * lineups are fetched ONCE per fixture and reused (the XI does not change), so each
//     lead refresh costs 2 upstream calls (statistics + fixture),
//   * a 300s TTL means one refresh per 5-minute poll -> ~10 refreshes over a 45-min
//     half -> ~21 calls/game, ~63 for the three World Cup games on a match day.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$CACHE_TTL = 300; // seconds; matches the client's 5-minute poll cadence
$fixture = preg_replace('/[^0-9]/', '', $_GET['fixture'] ?? '');
$isLead  = (($_GET['lead'] ?? '') === '1'); // only the lead client spends quota
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable

if ($fixture === '') {
    http_response_code(400);
    echo '{"error":"missing fixture"}';
    exit;
}

$cacheFile   = __DIR__ . "/feed_cache_$fixture.json";
$lineupsFile = __DIR__ . "/lineups_$fixture.json";

// Fresh cache: serve it to everyone, no upstream cost.
if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}

// Cache is stale or missing. Followers must NOT spend quota: hand back the last
// snapshot we have (stale but usable), or a "waiting for the lead client" marker.
if (!$isLead) {
    if (file_exists($cacheFile)) {
        echo file_get_contents($cacheFile);
    } else {
        echo json_encode([
            "lineups"          => null,
            "statistics"       => null,
            "fixture"          => null,
            "cached_at"        => 0,
            "waiting_for_lead" => true,
        ]);
    }
    exit;
}

// --- Lead client only past this point: this is where upstream calls happen. ---
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
