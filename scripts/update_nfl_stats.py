"""Nightly: pull finished NFL box scores from ESPN's public site API and keep each
player's recent game log in data/nfl_logs.json for the NFL parlay builder.

Row: [date, opp, home, pass_yds, pass_tds, rush_att, rush_yds, rush_tds,
      receptions, rec_yds, rec_tds, game_id, team]
Standard library only; incremental like update_stats.py.
"""
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
OUT = Path(__file__).resolve().parent.parent / "data" / "nfl_logs.json"
ET = ZoneInfo("America/New_York")
KEEP = 10
SCHEMA = 1
SKIP_SEASON_TYPES = {1}         # preseason
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/json"}
# ESPN block name -> {key: row index}
BLOCKS = {
    "passing": {"passingYards": 3, "passingTouchdowns": 4},
    "rushing": {"rushingAttempts": 5, "rushingYards": 6, "rushingTouchdowns": 7},
    "receiving": {"receptions": 8, "receivingYards": 9, "receivingTouchdowns": 10},
}


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


def season_start(today):
    year = today.year if today.month >= 3 else today.year - 1
    return date(year, 8, 1), f"{year}"


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_box(summary, game_date, gid):
    comp = summary["header"]["competitions"][0]
    side = {c["team"]["abbreviation"]: c["homeAway"] for c in comp["competitors"]}
    teams = list(side)
    players = {}
    for t in summary.get("boxscore", {}).get("players", []):
        abbr = t["team"]["abbreviation"]
        opp = next((x for x in teams if x != abbr), "")
        for block in t.get("statistics", []):
            cols = BLOCKS.get(block.get("name"))
            if not cols:
                continue
            idx = {k: i for i, k in enumerate(block.get("keys", []))}
            for a in block.get("athletes", []):
                st = a.get("stats") or []
                ath = a.get("athlete") or {}
                if not st or "id" not in ath:
                    continue
                pid = str(ath["id"])
                rec = players.setdefault(pid, {"n": ath.get("displayName", ""), "t": abbr,
                                               "row": [game_date, opp, 1 if side.get(abbr) == "home" else 0,
                                                       0, 0, 0, 0, 0, 0, 0, 0, gid, abbr]})
                for key, col in cols.items():
                    i = idx.get(key)
                    if i is not None and i < len(st):
                        rec["row"][col] = num(st[i])
    return players


def main():
    today = datetime.now(ET).date()
    start, season = season_start(today)
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    if data.get("season") != season or data.get("v") != SCHEMA:
        print("Building the season file from scratch.")
        data = {"season": season, "v": SCHEMA, "dates_done": [], "games_done": [], "players": {}}
    dates_done, games_done, players = set(data["dates_done"]), set(data["games_done"]), data["players"]

    added = 0
    d = start
    while d < today:
        ds = d.isoformat()
        if ds not in dates_done:
            sb = get_json(f"{BASE}/scoreboard?dates={d.strftime('%Y%m%d')}&limit=50")
            all_final = True
            for ev in sb.get("events", []):
                if (ev.get("season") or {}).get("type") in SKIP_SEASON_TYPES:
                    continue
                if not ev.get("status", {}).get("type", {}).get("completed"):
                    all_final = False
                    continue
                gid = str(ev["id"])
                if gid in games_done:
                    continue
                try:
                    box = parse_box(get_json(f"{BASE}/summary?event={gid}"), ds, gid)
                except Exception as err:  # noqa: BLE001
                    print(f"  skip {gid}: {err}", file=sys.stderr)
                    all_final = False
                    continue
                for pid, p in box.items():
                    rec = players.setdefault(pid, {"n": p["n"], "t": p["t"], "g": []})
                    rec["n"] = p["n"] or rec["n"]
                    if not rec["g"] or ds >= rec["g"][0][0]:
                        rec["t"] = p["t"]
                    rec["g"] = sorted([r for r in rec["g"] if r[11] != gid] + [p["row"]],
                                      key=lambda r: (r[0], r[11]), reverse=True)[:KEEP]
                games_done.add(gid)
                added += 1
                time.sleep(0.3)
            if all_final:
                dates_done.add(ds)
            time.sleep(0.15)
        d += timedelta(days=1)

    data.update(dates_done=sorted(dates_done), games_done=sorted(games_done),
                updated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                fields=["date", "opp", "home", "pass_yds", "pass_tds", "rush_att", "rush_yds", "rush_tds",
                        "rec", "rec_yds", "rec_tds", "game_id", "team"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"NFL {season}: added {added} games; {len(games_done)} total; {len(players)} players; {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
