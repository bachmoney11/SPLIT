"""Stáhne V5 timeline profi her z Leaguepedie a uloží stav hry po minutách -> data/tl/<id>.json (malé)."""
import json, sys, re, os, time
from concurrent.futures import ThreadPoolExecutor
import scrape
titles = json.load(open("data/v5_titles.json"))
by = {}
for t in titles:
    srv, num = t.split(":")[1].split()
    by.setdefault(srv, []).append((int(num), t))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 700
pick = [t for srv in by for _, t in sorted(by[srv])[-N:]]
LANE = {"TOP_LANE": "top", "MID_LANE": "mid", "BOT_LANE": "bot"}

def extract(tl):
    info = tl.get("info", tl); frames = info["frames"]
    win = None; ev_all = []
    for f in frames:
        for e in f.get("events", []):
            ev_all.append(e)
            if e.get("type") == "GAME_END": win = e.get("winningTeam")
    if win not in (100, 200): return None
    team = lambda pid: 100 if int(pid) <= 5 else 200
    out = []
    for f in frames:
        pf = f["participantFrames"]
        g = {100: 0, 200: 0}; xp = {100: 0, 200: 0}; cs = {100: 0, 200: 0}; lv = {100: 0, 200: 0}
        for pid, p in pf.items():
            t = team(pid); g[t] += p.get("totalGold", 0); xp[t] += p.get("xp", 0); cs[t] += p.get("minionsKilled", 0) + p.get("jungleMinionsKilled", 0); lv[t] += p.get("level", 0)
        out.append(dict(m=round(f["timestamp"] / 60000, 2), g=g[100] - g[200], gt=g[100] + g[200], xp=xp[100] - xp[200], cs=cs[100] - cs[200], lv=lv[100] - lv[200]))
    evs = []
    for e in ev_all:
        ty = e.get("type"); ts = round(e.get("timestamp", 0) / 60000, 2)
        if ty == "CHAMPION_KILL":
            evs.append([ts, "k", team(e["killerId"]) if e.get("killerId", 0) > 0 else (300 - team(e["victimId"]))])
        elif ty == "ELITE_MONSTER_KILL":
            evs.append([ts, e.get("monsterType", ""), e.get("killerTeamId"), e.get("monsterSubType", "")])
        elif ty == "BUILDING_KILL":
            # teamId = tým, kterému budova patřila
            evs.append([ts, e.get("buildingType", ""), 300 - e.get("teamId", 100), e.get("towerType", ""), LANE.get(e.get("laneType"), "")])
        elif ty == "DRAGON_SOUL_GIVEN":
            evs.append([ts, "SOUL", e.get("teamId"), e.get("name", "")])
        elif ty == "TURRET_PLATE_DESTROYED":
            evs.append([ts, "PLATE", 300 - e.get("teamId", 100)])
    return dict(win=win, frames=out, ev=evs, start=info.get("gameStartTimestamp") or next((e.get("realTimestamp") for f in frames for e in f.get("events", []) if e.get("realTimestamp")), None))

def job(t):
    gid = t.split(":")[1].replace(" ", "_")
    fn = f"data/tl/{gid}.json"
    if os.path.exists(fn): return 1
    try:
        j = scrape.api(action="query", prop="revisions", titles=t + "/Timeline", rvprop="content", rvslots="main", formatversion=2)
        c = j["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
        x = extract(json.loads(c))
        json.dump(x or {}, open(fn, "w")); time.sleep(1.0)
        return 1
    except Exception as e:
        print("ERR", t, str(e)[:80], flush=True); return 0
with ThreadPoolExecutor(1) as ex:
    for i, r in enumerate(ex.map(job, pick)):
        if i % 200 == 0: print(i, len(pick), flush=True)
print("done", flush=True)
