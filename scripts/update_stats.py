"""Nightly: pull finished NBA box scores from ESPN's public site API and keep each
player's recent game log in data/player_logs.json for the parlay builder.

(The NBA's own CDN refuses requests from GitHub's servers; ESPN's does not.)
Standard library only. Incremental: finished dates and games are remembered, so
the first run backfills the season and later runs fetch only the previous night.
"""
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
OUT = Path(__file__).resolve().parent.parent / "data" / "player_logs.json"
ET = ZoneInfo("America/New_York")
KEEP = 25                       # most recent games kept per player
SCHEMA = 2                      # bump to rebuild the file when the row format changes
SKIP_SEASON_TYPES = {1}         # 1 = preseason
# ESPN abbreviations that differ from the NBA tricodes the app uses
ABBR = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/json"}


def get_json(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.load(r)
        except Exception as err:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url}: {err}", file=sys.stderr)
            time.sleep(2 * (i + 1))


def tri(a):
    return ABBR.get(a, a)


def season_start(today):
    year = today.year if today.month >= 8 else today.year - 1
    return date(year, 10, 1), f"{year}-{str(year + 1)[2:]}"


def pos_bucket(a):
    """ESPN position (PG, SG, SF, PF, C, G, F, G-F, ...) -> 'G' | 'F' | 'C' | ''"""
    pos = ((a.get("athlete") or {}).get("position") or a.get("position") or {})
    ab = (pos.get("abbreviation") or "").upper() if isinstance(pos, dict) else ""
    if not ab:
        return ""
    if ab.startswith("C"):
        return "C"
    return "G" if "G" in ab.split("-")[0] else "F"


def parse_box(summary, game_date, gid):
    """-> list of (espn_player_id, name, team, position, row)"""
    comp = summary["header"]["competitions"][0]
    side = {c["team"]["abbreviation"]: c["homeAway"] for c in comp["competitors"]}
    teams = [c["team"]["abbreviation"] for c in comp["competitors"]]
    out = []
    for t in summary.get("boxscore", {}).get("players", []):
        abbr = t["team"]["abbreviation"]
        opp = next((x for x in teams if x != abbr), "")
        for block in t.get("statistics", []):
            keys = block.get("keys", [])
            idx = {k: i for i, k in enumerate(keys)}
            for a in block.get("athletes", []):
                st = a.get("stats") or []
                if a.get("didNotPlay") or not st:
                    continue

                def val(key, made=False):
                    i = idx.get(key)
                    if i is None or i >= len(st):
                        return 0
                    v = st[i].split("-")[0] if made else st[i]
                    try:
                        return float(v) if key == "minutes" else int(v)
                    except ValueError:
                        return 0
                mins = val("minutes")
                if not mins:
                    continue
                row = [game_date, tri(opp), 1 if side.get(abbr) == "home" else 0, mins,
                       val("points"), val("rebounds"), val("assists"),
                       val("threePointFieldGoalsMade-threePointFieldGoalsAttempted", made=True), gid, tri(abbr)]
                out.append((str(a["athlete"]["id"]), a["athlete"].get("displayName", ""), tri(abbr), pos_bucket(a), row))
    return out


def main():
    today = datetime.now(ET).date()
    start, season = season_start(today)
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    if data.get("season") != season or data.get("source") != "espn" or data.get("v") != SCHEMA:
        print("Building the season file from scratch.")
        data = {"season": season, "source": "espn", "v": SCHEMA, "dates_done": [], "games_done": [], "players": {}}
    dates_done, games_done, players = set(data["dates_done"]), set(data["games_done"]), data["players"]

    added = 0
    d = start
    while d < today:                       # tonight's games aren't final yet
        ds = d.isoformat()
        if ds not in dates_done:
            sb = get_json(f"{BASE}/scoreboard?dates={d.strftime('%Y%m%d')}&limit=50")
            all_final = True
            for ev in sb.get("events", []):
                if (ev.get("season") or {}).get("type") in SKIP_SEASON_TYPES:
                    continue
                if not ev.get("status", {}).get("type", {}).get("completed"):
                    all_final = False      # postponed or still in progress: retry next run
                    continue
                gid = str(ev["id"])
                if gid in games_done:
                    continue
                try:
                    rows = parse_box(get_json(f"{BASE}/summary?event={gid}"), ds, gid)
                except Exception as err:  # noqa: BLE001
                    print(f"  skip {gid}: {err}", file=sys.stderr)
                    all_final = False
                    continue
                for pid, name, team, pos, row in rows:
                    rec = players.setdefault(pid, {"n": name, "t": team, "p": pos, "g": []})
                    rec["n"] = name or rec["n"]
                    rec["p"] = pos or rec.get("p", "")
                    if not rec["g"] or ds >= rec["g"][0][0]:
                        rec["t"] = team
                    rec["g"] = sorted([r for r in rec["g"] if r[8] != gid] + [row],
                                      key=lambda r: (r[0], r[8]), reverse=True)[:KEEP]
                games_done.add(gid)
                added += 1
                time.sleep(0.3)
            if all_final:
                dates_done.add(ds)
            time.sleep(0.2)
        d += timedelta(days=1)

    data.update(dates_done=sorted(dates_done), games_done=sorted(games_done),
                updated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                fields=["date", "opp", "home", "min", "pts", "reb", "ast", "fg3m", "game_id", "team"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"{season}: added {added} games; {len(games_done)} total; {len(players)} players; {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
