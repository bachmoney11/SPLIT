"""Track record tipů pro GitHub verzi -> site/snapshots.json (stejný tvar jako db live/snapshots v Claude).

  python3 snapshot.py tips     – před zápasem uloží finální odhad (průměr modelu a trhu), existující tipy nepřepisuje
  python3 snapshot.py results  – doplní vítěze a skóre dohraných zápasů (z site/matches.json po ranní obnově)

Vstupy: site/matches.json (z build_standalone.py), site/odds.json (z odds.py).
Tvar: {"matches": [{a, b, p, p_market, p_model, winner, score, stage, time, utc, saved}]}, p = šance týmu a na sérii.
"""
import json, os, sys, datetime as dt

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site')
WINDOW_H = 3.0          # tip se uloží, když zápas začíná do 3 hodin (Kurzy běží každé 2 h)
load = lambda f, d: json.load(open(os.path.join(SITE, f), encoding='utf-8')) if os.path.exists(os.path.join(SITE, f)) else d
key = lambda a, b: frozenset((a, b))


def market(odds, a, b):
    ks = [m['pa'] if m['a'] == a else 1 - m['pa'] for m in odds.get('matches', []) if key(m['a'], m['b']) == key(a, b)]
    return round(sum(ks) / len(ks), 4) if ks else None


def tips(snap, ms, odds, now):
    have = {key(s['a'], s['b']) for s in snap['matches']}
    added = 0
    for m in ms['matches']:
        if m.get('winner') or not m.get('utc') or m.get('p') is None or key(m['a'], m['b']) in have: continue
        start = dt.datetime.fromisoformat(m['utc'].replace('Z', '+00:00'))
        hours = (start - now).total_seconds() / 3600
        if not 0 < hours <= WINDOW_H: continue
        mk = market(odds, m['a'], m['b'])
        p = m['p'] if mk is None else (m['p'] + mk) / 2
        snap['matches'].append(dict(a=m['a'], b=m['b'], p=round(p, 4), p_market=mk, p_model=m['p'], winner=None, score='',
                                    stage=m.get('stage', ''), time=m.get('time', ''), utc=m['utc'], saved=now.isoformat(timespec='minutes')))
        added += 1
    return added


def results(snap, ms):
    done = {key(m['a'], m['b']): m for m in ms['matches'] if m.get('winner')}
    n = 0
    for s in snap['matches']:
        m = done.get(key(s['a'], s['b']))
        if s.get('winner') or not m: continue
        sa, sb = (m.get('s1'), m.get('s2')) if m['a'] == s['a'] else (m.get('s2'), m.get('s1'))
        s['winner'] = m['winner']; s['score'] = f'{sa}-{sb}' if sa not in (None, '') else ''
        n += 1
    return n


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'tips'
    snap = load('snapshots.json', {'matches': []}); snap.setdefault('matches', [])
    ms = load('matches.json', {'matches': []})
    now = dt.datetime.now(dt.timezone.utc)
    n = tips(snap, ms, load('odds.json', {}), now) if mode == 'tips' else results(snap, ms)
    snap['updated'] = now.isoformat(timespec='minutes')
    if n:
        json.dump(snap, open(os.path.join(SITE, 'snapshots.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(mode, n, 'změn,', len(snap['matches']), 'tipů celkem')
