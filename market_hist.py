"""Historie trhu Polymarket pro LoL zápasy: cena před začátkem zápasu -> data/market_hist.json"""
import requests, json, time, re, sys
import datetime as dt
S = requests.Session()
evs, cur = [], None
while True:
    p = {"tag_slug": "league-of-legends", "closed": "true", "limit": 100, "order": "startDate", "ascending": "false"}
    if cur: p["after_cursor"] = cur
    x = S.get("https://gamma-api.polymarket.com/events/keyset", params=p, timeout=60).json()
    evs += x.get("events", []); cur = x.get("next_cursor")
    last = (evs[-1].get("startDate") or "") if evs else ""
    if not cur or not x.get("events") or last < "2024-12-01": break
print("closed events", len(evs), file=sys.stderr)
out = []
for ev in evs:
    if not re.match(r"lol-", ev.get("slug", "")): continue
    tags = [t.get("slug") for t in ev.get("tags", [])]
    for m in ev.get("markets", []):
        q = m.get("question", "")
        if re.search(r"handicap|total|kills|O/U|first blood|odd|even", q, re.I): continue
        g = re.search(r"Game (\d)", q)
        try:
            outs = json.loads(m["outcomes"]); toks = json.loads(m["clobTokenIds"]); fin = [float(p) for p in json.loads(m["outcomePrices"])]
        except Exception:
            continue
        if len(outs) != 2 or max(fin) < 0.98: continue   # nerozhodnuto / zrušeno
        start = m.get("gameStartTime") or ev.get("startTime")
        out.append(dict(slug=ev["slug"], title=ev.get("title"), q=q, game=int(g.group(1)) if g else 0, a=outs[0], b=outs[1],
                        token=toks[0], winA=int(fin[0] > 0.5), start=start, tags=tags, volume=float(m.get("volume") or 0)))
print("markets", len(out), file=sys.stderr)
# jen zápasy z mezinárodních turnajů v našich datech (stejný den, stejné týmy)
import pandas as pd
G = pd.read_csv("data/games.csv", keep_default_na=False)
G = G[G.kind == "intl"]
low = lambda x: re.sub(r"[^a-z0-9]", "", x.lower().split(" (")[0])
keys = {}
for r in G.itertuples():
    keys.setdefault(r.date, set()).update([low(r.blue), low(r.red)])
def hit(m):
    d = (m["start"] or "")[:10]
    if not d: return False
    for dd in {d, (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()}:
        if dd in keys and low(m["a"]) in keys[dd] and low(m["b"]) in keys[dd]: return True
    return False
out = [m for m in out if hit(m)]
print("intl markets", len(out), file=sys.stderr)
for i, m in enumerate(out):
    try:
        t0 = int(dt.datetime.fromisoformat(m["start"].replace(" ", "T").replace("+00", "+00:00").replace("Z", "+00:00")).timestamp())
    except Exception:
        m["p_pre"] = None; continue
    try:
        h = S.get("https://clob.polymarket.com/prices-history", params={"market": m["token"], "startTs": t0 - 6 * 3600, "endTs": t0, "fidelity": 10}, timeout=60).json().get("history", [])
    except Exception:
        h = []
    m["p_pre"] = h[-1]["p"] if h else None
    if i % 50 == 0: print(i, m["slug"], m["p_pre"], file=sys.stderr)
    time.sleep(0.15)
json.dump(out, open("data/market_hist.json", "w"), ensure_ascii=False)
print("done", sum(1 for m in out if m["p_pre"] is not None), file=sys.stderr)
