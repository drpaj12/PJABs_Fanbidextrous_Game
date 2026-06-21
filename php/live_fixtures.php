<?php
// live_fixtures.php -- lead-gated, cached proxy of API-Football's "live now" fixture list.
//
// Purpose: the free tier blocks the season-filtered fixtures LIST (fixtures?season=2026),
// but the unfiltered live endpoint (fixtures?live=all) IS served for free. The client picks
// a game from the offline schedule and then matches it, by team name, to whatever World Cup
// match is live right now to discover its REAL API-Football fixture id. That real id then
// drives feed_cache.php (lineups/statistics) exactly as before. No id is ever prefetched or
// stored on disk in the client -- it is resolved live, each time, only while the game plays.
//
// Quota design (free tier = 100 requests/day), same discipline as feed_cache.php:
//   * a SINGLE shared cache file (live=all is not per-fixture),
//   * ONLY the lead client (?lead=1) spends an upstream call; everyone else reads the cache,
//   * a short 30s TTL -- the live list changes as matches start/end, but ids never change
//     mid-match, so one upstream call covers all clients for the cache window.
//
// Server-side filter: live=all returns every in-play match across all leagues (dozens). We
// keep only league.id == 1 (the FIFA World Cup) and project each to {id, home, away, status,
// elapsed} so the client payload is tiny.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$WORLD_CUP_LEAGUE = 1;   // API-Football league id for the FIFA World Cup
$CACHE_TTL        = 30;  // seconds; ids are static mid-match, only the list membership moves

$isLead  = (($_GET['lead'] ?? '') === '1'); // only the lead client spends quota
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable
$cacheFile = __DIR__ . '/live_fixtures.json';

// Fresh cache: serve it to everyone, no upstream cost.
if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}

// Cache stale or missing. Followers must NOT spend quota: hand back the last list we have,
// or a "waiting for the lead client" marker.
if (!$isLead) {
    if (file_exists($cacheFile)) {
        echo file_get_contents($cacheFile);
    } else {
        echo json_encode(["response" => [], "cached_at" => 0, "waiting_for_lead" => true]);
    }
    exit;
}

// --- Lead client only past this point: this is where the upstream call happens. ---
if (!file_exists($keyFile)) {
    http_response_code(503);
    echo '{"error":"feed unavailable"}';
    exit;
}
$key = trim(file_get_contents($keyFile));
$url = "https://v3.football.api-sports.io/fixtures?live=all";

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

$data = json_decode($out, true);
$games = [];
foreach (($data['response'] ?? []) as $fx) {
    if ((int)($fx['league']['id'] ?? 0) !== $WORLD_CUP_LEAGUE) {
        continue;   // keep only World Cup matches
    }
    $games[] = [
        "id"      => $fx['fixture']['id'] ?? null,
        "home"    => $fx['teams']['home']['name'] ?? "",
        "away"    => $fx['teams']['away']['name'] ?? "",
        "status"  => $fx['fixture']['status']['short'] ?? "",
        "elapsed" => $fx['fixture']['status']['elapsed'] ?? null,
    ];
}
$payload = json_encode(["response" => $games, "cached_at" => time()]);
file_put_contents($cacheFile, $payload, LOCK_EX);
echo $payload;
