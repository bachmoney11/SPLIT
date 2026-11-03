"""Pořadí draftu (picky/bany) z Leaguepedia 'Picks and Bans' stránek -> data/drafts.json"""
import json, scrape
from bs4 import BeautifulSoup
PRE = ['2025 First Stand', '2025 Mid-Season Invitational', '2025 Season World Championship',
       '2026 First Stand', '2026 Mid-Season Invitational', '2026 Season World Championship']
ROLE = {'Top Laner': 0, 'Jungler': 1, 'Mid Laner': 2, 'Bot Laner': 3, 'Support': 4}
def cells(tr, cls):
    return [c for c in tr.find_all('td') if cls in (c.get('class') or [])]
def title(c):
    x = c.select_one('[title]'); return x.get('title') if x else None
games, seen = [], set()
for pre in PRE:
    pages = [t for t in scrape.list_pages(pre) if '/Picks and Bans' in t]
    pages = [t for t in pages if not any(o != t and o.startswith(t + '/') for o in pages)]
    for pg in pages:
        soup = BeautifulSoup(scrape.fetch(pg), 'lxml')
        for tb in soup.select('table.pb'):
            hdr = [tr for tr in tb.find_all('tr') if ' vs ' in tr.get_text(' ', strip=True)]
            if not hdr: continue
            teams = []
            for x in hdr[0].select('[title]'):
                if x['title'] not in teams: teams.append(x['title'])
            bans, picks = [], []
            for tr in tb.find_all('tr'):
                b = cells(tr, 'pb-ban'); p = cells(tr, 'pb-pick')
                if len(b) == 2: bans.append((title(b[0]), title(b[1])))
                if len(p) == 2:
                    roles = [ROLE.get(title(c)) for c in cells(tr, 'pb-role')]
                    picks.append(((title(p[0]), roles[0] if roles else None), (title(p[1]), roles[-1] if roles else None)))
            if len(bans) != 5 or len(picks) != 5 or len(teams) < 2: continue
            seq = []
            for i in range(3): seq += [('F', 'ban', bans[i][0], None), ('S', 'ban', bans[i][1], None)]
            P = picks
            seq += [('F', 'pick') + P[0][0], ('S', 'pick') + P[0][1], ('S', 'pick') + P[1][1],
                    ('F', 'pick') + P[1][0], ('F', 'pick') + P[2][0], ('S', 'pick') + P[2][1]]
            seq += [('S', 'ban', bans[3][1], None), ('F', 'ban', bans[3][0], None),
                    ('S', 'ban', bans[4][1], None), ('F', 'ban', bans[4][0], None)]
            seq += [('S', 'pick') + P[3][1], ('F', 'pick') + P[3][0], ('F', 'pick') + P[4][0], ('S', 'pick') + P[4][1]]
            key = (pg.split('/Picks')[0], teams[0], teams[1], tuple(s[2] for s in seq))
            if key in seen: continue
            seen.add(key)
            games.append(dict(tournament=pg, first=teams[0], second=teams[1], seq=seq))
json.dump(games, open('data/drafts.json', 'w'), ensure_ascii=False)
print(len(games), games[-1])
