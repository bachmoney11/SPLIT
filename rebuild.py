"""Oprava dat podle auditu: znovu stáhne stránky useknuté limitem, odstraní duplicity mezi stránkami."""
import os, re, csv, sys, glob
import scrape
from bs4 import BeautifulSoup

def full(tour):
    txt = '{{#invoke:MatchHistoryGame|main|preload=Tournament|tournament=%s|limit=3000}}' % tour
    j = scrape.api(action='parse', text=txt, title='X', contentmodel='wikitext', prop='text', formatversion=2)
    return j['parse']['text']

def redirects(ts):
    """Které z titulů jsou na wiki jen přesměrování – prop=info, 50 titulů na 1 API volání (nic se nestahuje)."""
    out, ts = set(), sorted(ts)
    for i in range(0, len(ts), 50):
        j = scrape.api(action='query', titles='|'.join(ts[i:i + 50]), prop='info', formatversion=2)
        q = j.get('query', {})
        norm = {n['to']: n['from'] for n in q.get('normalized', [])}
        for p in q.get('pages', []):
            if p.get('redirect'): out.add(norm.get(p['title'], p['title']))
    return out

def subpages(t, titles):
    tour = t.split('/Match History')[0]
    return [o for o in titles if o != t and o.startswith(tour + '/') and o.endswith('/Match History')]

jobs = []
for pre in scrape.INTL_PREFIXES:
    for t in scrape.match_history_pages(pre): jobs.append((t, 'intl', ''))
for pre, reg in scrape.LEAGUES.items():
    for t in scrape.match_history_pages(pre): jobs.append((t, 'domestic', reg))
titles = {t for t, _, _ in jobs}
# allpages vrací i přesměrování -> zjistit, které podstránky jsou jen redirect (typicky 1-3 API volání)
redir = redirects({o for t in titles for o in subpages(t, titles)})
print('redirect subpages', len(redir), file=sys.stderr)
rows = []; refetched = 0
for t, kind, reg in jobs:
    if t in redir: continue  # přesměrování nemá vlastní hry
    # rodičovská stránka, pokud existují SKUTEČNÉ podstránky (Play-In / Main Event) -> přeskočit
    tour = t.split('/Match History')[0]
    if any(o not in redir for o in subpages(t, titles)):
        continue
    html = scrape.fetch(t)
    m = re.search(r'Limit: ?(\d+)', html)
    g = scrape.parse(html, tour)
    if m and len(g) >= int(m.group(1)) - 1:
        fn = os.path.join(scrape.CACHE, 'FULL_' + re.sub(r'[^\w.-]', '_', tour) + '.html')
        if not os.path.exists(fn):
            h2 = full(tour)
            if len(scrape.parse(h2, tour)) > len(g): open(fn, 'w').write(h2); refetched += 1
            else: fn = None
        if fn: g = scrape.parse(open(fn).read(), tour)
    for x in g:
        x.update(kind=kind, league_region=reg)
        for k in ('blue_bans', 'red_bans'):
            x[k] = '|'.join(c for c in x[k].split('|') if c and c != 'None')
    rows += g
print('refetched', refetched, 'rows', len(rows), file=sys.stderr)
# duplicity mezi stránkami (stejná hra na dvou stránkách) – uvnitř stránky nic nemažeme
key = lambda x: (x['date'], x['blue'], x['red'], x['blue_picks'], x['red_picks'], x['winner'])
seen = {}
for i, x in enumerate(rows):
    seen.setdefault(key(x), set()).add(x['tournament'])
out, used = [], {}
for x in rows:
    k = key(x); best = max(seen[k], key=len)
    if x['tournament'] != best: continue
    out.append(x)
keys = ["tournament", "kind", "league_region", "date", "patch", "blue", "red", "winner",
        "blue_bans", "red_bans", "blue_picks", "red_picks", "blue_roster", "red_roster"]
with open('data/games.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(out)
print('final', len(out), file=sys.stderr)
