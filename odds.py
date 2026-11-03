"""Kurzy na LoL zápasy z predikčních trhů (Polymarket, Kalshi) -> data/odds.json

Výstup: {"updated": ISO čas, "matches": [{"a", "b", "pa", "source", "title", "url"}]}
  pa = tržní pravděpodobnost výhry týmu a v sérii (bez marže, normalizováno).
Názvy týmů se mapují na jména používaná v modelu (Leaguepedia).
"""
import json, re, sys, datetime as dt
import requests

S = requests.Session(); S.headers["User-Agent"] = "rift-prognoza/0.2"
ALIAS = {
    "karmine corp": "Karmine Corp", "kc": "Karmine Corp", "movistar koi": "Movistar KOI", "mkoi": "Movistar KOI", "koi": "Movistar KOI",
    "los": "LØS", "løs": "LØS", "lyon": "LYON (2024 American Team)", "hanwha life esports": "Hanwha Life Esports", "hle": "Hanwha Life Esports",
    "hanwha life": "Hanwha Life Esports", "bilibili gaming": "Bilibili Gaming", "blg": "Bilibili Gaming", "gen.g": "Gen.G", "geng": "Gen.G",
    "gen": "Gen.G", "dplus kia": "Dplus Kia", "dk": "Dplus Kia", "t1": "T1", "top esports": "Top Esports", "tes": "Top Esports",
    "invictus gaming": "Invictus Gaming", "ig": "Invictus Gaming",
    "dplus": "Dplus Kia", "lyon gaming": "LYON (2024 American Team)", "lyon24": "LYON (2024 American Team)", "kcorp": "Karmine Corp",
}
def norm(name):
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    return ALIAS.get(n) or ALIAS.get(n.replace(" esports", "")) or None


def polymarket():
    out = []
    for q in ["League of Legends Worlds", "LoL Worlds 2026", "League of Legends"]:
        try:
            r = S.get("https://gamma-api.polymarket.com/public-search", params={"q": q, "limit_per_type": 50, "events_status": "active"}, timeout=30)
            evs = r.json().get("events", []) or []
        except Exception as e:
            print("polymarket", e, file=sys.stderr); continue
        for ev in evs:
            for m in ev.get("markets", []) or []:
                try:
                    outs = json.loads(m.get("outcomes") or "[]"); prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                except Exception:
                    continue
                if len(outs) != 2 or len(prices) != 2 or m.get("closed"):
                    continue
                a, b = norm(outs[0]), norm(outs[1])
                title = (m.get("question") or ev.get("title") or "")
                if not (a and b) or re.search(r"game \d|map \d|handicap|total|kills", title, re.I):
                    continue
                s = sum(prices) or 1
                out.append(dict(a=a, b=b, pa=round(prices[0] / s, 4), source="Polymarket", title=title,
                                url="https://polymarket.com/event/" + (ev.get("slug") or "")))
    return out


def kalshi():
    out = []
    try:
        r = S.get("https://api.elections.kalshi.com/trade-api/v2/events",
                  params={"series_ticker": "KXLOLGAME", "status": "open", "with_nested_markets": "true", "limit": 200}, timeout=30)
        evs = r.json().get("events", []) or []
    except Exception as e:
        print("kalshi", e, file=sys.stderr); return out
    for ev in evs:
        mk = ev.get("markets", []) or []
        teams = []
        for m in mk:
            name = m.get("yes_sub_title") or m.get("subtitle") or ""
            f = lambda k: float(m[k]) if m.get(k) not in (None, "") else None
            bid, ask, last = f("yes_bid_dollars"), f("yes_ask_dollars"), f("last_price_dollars")
            p = (bid + ask) / 2 if bid and ask else last
            if norm(name) and p:
                teams.append((norm(name), p))
        if len(teams) == 2:
            s = teams[0][1] + teams[1][1]
            out.append(dict(a=teams[0][0], b=teams[1][0], pa=round(teams[0][1] / s, 4), source="Kalshi",
                            title=ev.get("title", ""), url="https://kalshi.com/markets/kxlolgame"))
    return out


if __name__ == "__main__":
    ms = polymarket() + kalshi()
    seen, uniq = set(), []
    for m in ms:   # jeden trh na dvojici a zdroj
        k = (frozenset((m["a"], m["b"])), m["source"])
        if k in seen: continue
        seen.add(k); uniq.append(m)
    res = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), matches=uniq)
    json.dump(res, open("data/odds.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
