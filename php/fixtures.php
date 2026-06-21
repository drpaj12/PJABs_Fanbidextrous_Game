<?php
// fixtures.php -- lead-gated, cached proxy of API-Football's fixtures-by-date list.
//
// Purpose: let TOOLS/fetch_fixture_ids.py harvest REAL API-Football fixture ids ahead of
// time so the curated assets/data/schedule.json can carry real ids. The live runtime path
// (feed_cache.php) keys on a real fixture id; without this the picker's synthetic ids never
// resolve and the wait screen hangs.
//
// Quota design (free tier = 100 requests/day), same discipline as feed_cache.php:
//   * cache is PER UTC DATE (fixtures_<date>.json),
//   * ONLY the lead client (?lead=1) spends an upstream call; everyone else reads cache,
//   * 6h TTL -- a day's WC fixture list is effectively static, so one upstream call per
//     date covers an entire harvest run no matter how many times the tool is run.
//
// date is a UTC calendar date (the harvester derives it from each row's kickoff_utc, NOT
// the US-Eastern local date -- a late ET kickoff rolls into the next UTC day).
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$LEAGUE    = 1;      // API-Football league id for the FIFA World Cup
$SEASON    = 2026;
$CACHE_TTL = 21600;  // 6 hours

$date = $_GET['date'] ?? '';
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
    http_response_code(400);
    echo '{"error":"missing or bad date (expected YYYY-MM-DD)"}';
    exit;
}
$isLead  = (($_GET['lead'] ?? '') === '1'); // only the lead client spends quota
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable

$cacheFile = __DIR__ . "/fixtures_$date.json";

// Fresh cache: serve it to everyone, no upstream cost.
if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}

// Cache stale or missing. Followers must NOT spend quota.
if (!$isLead) {
    if (file_exists($cacheFile)) {
        echo file_get_contents($cacheFile);
    } else {
        echo json_encode(["response" => null, "cached_at" => 0, "waiting_for_lead" => true]);
    }
    exit;
}

// --- Lead client only past this point: upstream call happens here. ---
if (!file_exists($keyFile)) {
    http_response_code(503);
    echo '{"error":"feed unavailable"}';
    exit;
}
$key = trim(file_get_contents($keyFile));
$url = "https://v3.football.api-sports.io/fixtures?league=$LEAGUE&season=$SEASON&date=$date";

$ch = curl_init($url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, ["x-apisports-key: $key"]);
curl_setopt($ch, CURLOPT_TIMEOUT, 15);
$out = curl_exec($ch);
curl_close($ch);

if (!$out) {
    http_response_code(502);
    echo '{"error":"upstream failed"}';
    exit;
}
file_put_contents($cacheFile, $out, LOCK_EX);
echo $out;
