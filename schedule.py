"""Rozpis zápasů turnaje z Leaguepedie (Data:<turnaj>) -> data/schedule.json"""
import re, json, sys, datetime as dt
import scrape
PAGE = sys.argv[1] if len(sys.argv) > 1 else "Data:2026 Season World Championship/Main Event"
TZ = {"PST": -8, "PDT": -7, "CET": 1, "CEST": 2, "KST": 9, "UTC": 0, "EST": -5}

def parse(c):
    out, tab, bo = [], None, 1
    for line in re.split(r"(?=\{\{MatchSchedule[|/])", c):
        m = re.match(r"\{\{MatchSchedule/Start\|tab=([^|]*)\|bestof=(\d)", line)
        if m: tab, bo = m.group(1).strip(), int(m.group(2)); continue
        if not line.startswith("{{MatchSchedule|"): continue
        f = lambda k: (re.search(r"\|\s*" + k + r"\s*=([^|}\n]*)", line) or [None, ""])[1].strip()
        d, t, tz = f("date"), f("time"), f("timezone")
        utc = None
        if d and t:
            utc = (dt.datetime.fromisoformat(f"{d}T{t}") - dt.timedelta(hours=TZ.get(tz, 0) + (1 if f("dst") == "yes" else 0))).isoformat() + "Z"
        games = []
        for g in re.findall(r"\{\{MatchSchedule/Game(.*?)\}\}", line, re.S):
            gf = lambda k: (re.search(r"\|\s*" + k + r"\s*=([^|}\n]*)", g) or [None, ""])[1].strip()
            games.append(dict(blue=gf("blue"), red=gf("red"), winner=gf("winner"), gid=gf("riot_platform_game_id"), first_sel=gf("first_sel")))
        out.append(dict(tab=tab, bo=bo, order=int(f("initialorder") or 0), t1=f("team1"), t2=f("team2"),
                        s1=f("team1score"), s2=f("team2score"), winner=f("winner"), utc=utc, games=[g for g in games if g["blue"] or g["gid"] or g["winner"]]))
    return out

if __name__ == "__main__":
    j = scrape.api(action="query", prop="revisions", titles=PAGE, rvprop="content", rvslots="main", formatversion=2)
    c = j["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    S = parse(c)
    json.dump(S, open("data/schedule.json", "w"), ensure_ascii=False, indent=1)
    for m in S:
        if m["tab"] not in ("Round 1", "Round 2", "Round 3", "Round 4"): print(m["tab"], m["order"], m["t1"], m["t2"], m["s1"], m["s2"], m["winner"], m["utc"], len(m["games"]))
