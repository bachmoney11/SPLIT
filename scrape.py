"""Stahovač dat z Leaguepedie (lol.fandom.com) – Match History stránky.

Pro každý turnaj stáhne všechny hry: datum, patch, modrý/červený tým, vítěz,
bany, picky a soupisky. Výsledek: data/games.csv
"""
import json, re, sys, time, os
import requests
from bs4 import BeautifulSoup

API = "https://lol.fandom.com/api.php"
WIKI = "https://lol.fandom.com/wiki/"
S = requests.Session()
S.headers["User-Agent"] = "lol-intl-predictor/0.1 (personal research project)"
CACHE = os.path.join(os.path.dirname(__file__), "data", "html")
os.makedirs(CACHE, exist_ok=True)

INTL_PREFIXES = ["Season 1 World Championship", "Season 2 World Championship",
                 "Season 3 World Championship"]
for y in range(2014, 2027):
    INTL_PREFIXES.append(f"{y} Season World Championship")
for y in range(2015, 2027):
    INTL_PREFIXES.append(f"{y} Mid-Season Invitational")
for y in range(2025, 2027):
    INTL_PREFIXES.append(f"{y} First Stand")

# domácí ligy (klíč = prefix stránky, hodnota = region)
LEAGUES = {
    "LCK/": "KR", "Champions/": "KR", "OGN Champions/": "KR",
    "LPL/": "CN", "Tencent LoL Pro League/": "CN",
    "LEC/": "EU", "EU LCS/": "EU", "EU LCS Season/": "EU",
    "LCS/": "NA", "NA LCS/": "NA", "LTA North/": "NA", "LTA/": "AM",
    "LTA South/": "BR", "CBLOL/": "BR",
    "LMS/": "TW", "PCS/": "PCS", "LCP/": "PCS", "GPL/": "SEA",
    "VCS/": "VN", "LJL/": "JP", "LLA/": "LAT", "LLN/": "LAT", "CLS/": "LAT",
    "TCL/": "TR", "LCL/": "CIS", "OPL/": "OCE", "LCO/": "OCE",
}


def api(**params):
    params.update(format="json")
    for attempt in range(6):
        try:
            r = S.get(API, params=params, timeout=90)
            j = r.json()
        except Exception:
            time.sleep(5 * (attempt + 1)); continue
        if "error" in j and j["error"].get("code") == "ratelimited":
            time.sleep(10 * (attempt + 1)); continue
        return j
    raise RuntimeError("ratelimited")


def list_pages(prefix):
    out, cont = [], {}
    while True:
        j = api(action="query", list="allpages", apprefix=prefix, aplimit=500, **cont)
        out += [p["title"] for p in j["query"]["allpages"]]
        if "continue" in j:
            cont = {"apcontinue": j["continue"]["apcontinue"]}
        else:
            return out


def match_history_pages(prefix):
    return [t for t in list_pages(prefix) if re.search(r"/Match History(/|$)", t)]


def fetch(title):
    fn = os.path.join(CACHE, re.sub(r"[^\w.-]", "_", title) + ".html")
    if os.path.exists(fn):
        return open(fn, encoding="utf-8").read()
    j = api(action="parse", page=title, prop="text", formatversion=2)
    if "parse" not in j:
        raise RuntimeError(f"fetch failed {title} {j.get('error')}")
    html = j["parse"]["text"]
    open(fn, "w", encoding="utf-8").write(html)
    time.sleep(0.5)
    return html


def titles(cell):
    return [x.get("title") for x in cell.select("[title]") if x.get("title")]


def parse(html, tournament):
    soup = BeautifulSoup(html, "lxml")
    games = []
    for table in soup.select("table.wikitable"):
        header = None
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            texts = [c.get_text(" ", strip=True) for c in cells]
            if "Blue" in texts and "Red" in texts and "Winner" in texts:
                header = texts; continue
            if not header or len(cells) != len(header):
                continue
            idx = {}
            for i, h in enumerate(header):
                idx.setdefault(h, []).append(i)
            try:
                date = texts[idx["Date"][0]]
                if not re.match(r"\d{4}-\d{2}-\d{2}", date):
                    continue
                blue = (titles(cells[idx["Blue"][0]]) or [""])[0]
                red = (titles(cells[idx["Red"][0]]) or [""])[0]
                win = (titles(cells[idx["Winner"][0]]) or [""])[0]
            except (KeyError, IndexError):
                continue
            if not blue or not red or win not in (blue, red):
                continue
            g = dict(tournament=tournament, date=date,
                     patch=texts[idx["P"][0]] if "P" in idx else "",
                     blue=blue, red=red, winner=win)
            b = idx.get("Bans", []); p = idx.get("Picks", [])
            g["blue_bans"] = "|".join(titles(cells[b[0]])) if len(b) > 1 else ""
            g["red_bans"] = "|".join(titles(cells[b[1]])) if len(b) > 1 else ""
            g["blue_picks"] = "|".join(titles(cells[p[0]])) if len(p) > 1 else ""
            g["red_picks"] = "|".join(titles(cells[p[1]])) if len(p) > 1 else ""
            r = idx.get("Blue Roster", []); rr = idx.get("Red Roster", [])
            g["blue_roster"] = "|".join(titles(cells[r[0]])) if r else ""
            g["red_roster"] = "|".join(titles(cells[rr[0]])) if rr else ""
            games.append(g)
    return games


def main():
    import csv
    jobs = []  # (title, kind, region)
    for pre in INTL_PREFIXES:
        for t in match_history_pages(pre):
            jobs.append((t, "intl", ""))
    for pre, reg in LEAGUES.items():
        for t in match_history_pages(pre):
            jobs.append((t, "domestic", reg))
    print(len(jobs), "pages", file=sys.stderr)
    rows, seen = [], set()
    for i, (t, kind, reg) in enumerate(jobs):
        tour = t.split("/Match History")[0]
        try:
            gs = parse(fetch(t), tour)
        except Exception as e:
            print("ERR", t, e, file=sys.stderr); continue
        for g in gs:
            key = (g["date"], g["blue"], g["red"], g["blue_picks"], g["winner"], tour)
            if key in seen: continue
            seen.add(key)
            g.update(kind=kind, league_region=reg); rows.append(g)
        if i % 25 == 0:
            print(i, t, len(gs), len(rows), file=sys.stderr, flush=True)
    keys = ["tournament", "kind", "league_region", "date", "patch", "blue", "red", "winner",
            "blue_bans", "red_bans", "blue_picks", "red_picks", "blue_roster", "red_roster"]
    with open(os.path.join(os.path.dirname(__file__), "data", "games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)
    print("done", len(rows), file=sys.stderr)


if __name__ == "__main__":
    main()
