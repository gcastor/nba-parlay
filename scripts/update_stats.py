"""Nightly: pull finished NBA games' box scores from the NBA's public CDN and keep
each player's recent game log in data/player_logs.json for the parlay builder.

Standard library only. Incremental: games already processed are skipped, so the
first run backfills the season and later runs fetch only the previous night.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "player_logs.json"
KEEP = 25                      # most recent games kept per player
MAX_GAMES_PER_RUN = 450        # enough to backfill a full season in one run
GAME_TYPES = ("002", "004", "005", "006")   # regular season, playoffs, play-in, NBA Cup final
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Accept": "application/json",
}


def get_json(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as err:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url}: {err}", file=sys.stderr)
            time.sleep(2 * (i + 1))


def minutes(iso):
    """'PT25M01.00S' -> 25.0"""
    try:
        s = iso.replace("PT", "")
        m, rest = s.split("M")
        return round(int(m) + float(rest.rstrip("S") or 0) / 60, 1)
    except Exception:  # noqa: BLE001
        return 0.0


def finished_games(schedule):
    ls = schedule["leagueSchedule"]
    out = []
    for day in ls.get("gameDates", []):
        for g in day.get("games", []):
            gid = str(g.get("gameId", ""))
            if g.get("gameStatus") != 3 or not gid.startswith(GAME_TYPES):
                continue
            raw = g.get("gameDate") or day.get("gameDate", "")
            try:
                date = datetime.strptime(raw.split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                date = (g.get("gameDateEst") or "")[:10]
            out.append((gid, date))
    return ls.get("seasonYear", ""), out


def load():
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"season": "", "updated": None, "games_done": [], "players": {}}


def main():
    data = load()
    season, games = finished_games(get_json(SCHEDULE_URL))
    if data.get("season") and data["season"] != season:
        print(f"New season {season}; starting fresh.")
        data = {"season": season, "updated": None, "games_done": [], "players": {}}
    data["season"] = season
    done = set(data["games_done"])
    todo = [g for g in games if g[0] not in done][:MAX_GAMES_PER_RUN]
    print(f"{season}: {len(games)} finished games, {len(todo)} new")

    players = data["players"]
    added = 0
    for gid, date in todo:
        try:
            box = get_json(BOXSCORE_URL.format(gid))["game"]
        except Exception as err:  # noqa: BLE001
            print(f"  skip {gid}: {err}", file=sys.stderr)
            continue
        home, away = box["homeTeam"], box["awayTeam"]
        for team, opp, is_home in ((home, away, 1), (away, home, 0)):
            for p in team.get("players", []):
                if str(p.get("played")) != "1":
                    continue
                st = p.get("statistics", {})
                row = [date, opp["teamTricode"], is_home, minutes(st.get("minutes", "")),
                       st.get("points", 0), st.get("reboundsTotal", 0), st.get("assists", 0),
                       st.get("threePointersMade", 0), gid]
                pid = str(p["personId"])
                rec = players.setdefault(pid, {"n": "", "t": "", "g": []})
                rec["n"] = f'{p.get("firstName", "")} {p.get("familyName", "")}'.strip() or p.get("name", "")
                if not rec["g"] or date >= rec["g"][0][0]:
                    rec["t"] = team["teamTricode"]
                rec["g"] = sorted([r for r in rec["g"] if r[8] != gid] + [row], key=lambda r: (r[0], r[8]), reverse=True)[:KEEP]
        done.add(gid)
        added += 1
        time.sleep(0.25)

    data["games_done"] = sorted(done)
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["fields"] = ["date", "opp", "home", "min", "pts", "reb", "ast", "fg3m", "game_id"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"Added {added} games; {len(players)} players; wrote {OUT.stat().st_size / 1024:.0f} KB")
    if todo and not added:
        sys.exit("Every box score request failed.")


if __name__ == "__main__":
    main()
