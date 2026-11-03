"""Statická verze stránky pro hosting mimo Claude: site/index.html (+ odds.json, ingame.json, matches.json).

Šablonu page_template.html NEMĚNÍ – do výstupu jen vloží shim, který nahradí Claude runtime (cu):
  db     -> fetch odds.json / ingame.json / snapshots.json ze stejné složky, obnova každých 5 min
  mcp    -> živý draft přímo z Leaguepedie (api.php ... &origin=*), odpověď ve tvaru, který čte poll()
  sample -> nedostupné, čtení přenosu se vypne s hláškou
Spuštění z kořene repozitáře:  python3 build_standalone.py
Data: data/results.json + data/app_data.json (po pipeline), jinak záložně data/page_data.json.
"""
import json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'deploy' else HERE
SITE = os.path.join(ROOT, 'site')
P = lambda *a: os.path.join(ROOT, *a)


def page_data():
    """Stejná data jako build_page.py (bez zápisu jeho výstupů)."""
    if not (os.path.exists(P('data/results.json')) and os.path.exists(P('data/app_data.json'))):
        return json.load(open(P('data/page_data.json'), encoding='utf-8'))
    r = json.load(open(P('data/results.json'))); a = json.load(open(P('data/app_data.json')))
    keep = dict(games_test=r['games_test_2021'], series=r['series'], by_year=r['by_year'], ablation=r['ablation'],
                calibration=r['calibration'], upsets=r['upsets'], region_by_year=r['region_by_year'], regions_now=r['regions_now'],
                n=dict(total=r['n_games_total'], intl=r['n_intl_games'], tours=r['n_tournaments'], ev=r['n_eval_games'], test=r['n_test_games']))
    keep.update(a)
    if os.path.exists(P('data/icons.json')): keep['icons'] = json.load(open(P('data/icons.json')))
    if os.path.exists(P('data/market_eval.json')): keep['market'] = json.load(open(P('data/market_eval.json')))
    for f in ('data/items.json', 'seed/items.json'):   # sprite předmětů (items.py); v repozitáři leží v seed/
        if os.path.exists(P(f)): keep['items'] = json.load(open(P(f))); break
    return keep


def matches(d):
    """Přehled zápasů play-off pro snapshot.py (tipy před zápasem a doplnění vítězů)."""
    out = []
    for lv in ('qf', 'sf', 'f'):
        for m in d.get('bracket', {}).get(lv, []):
            if not (m.get('a') and m.get('b')): continue
            out.append({k: m.get(k) for k in ('stage', 'a', 'b', 'bo', 'utc', 'time', 's1', 's2', 'winner', 'p')})
    return dict(updated=d.get('updated'), shrink=d.get('shrink'), matches=out)


SHIM = r"""<script>
/* standalone shim: náhrada Claude artifact runtime pro statický hosting */
(() => {
  const REFRESH = 5 * 60 * 1000;
  const FILES = { 'live/odds': 'odds.json', 'live/ingame': 'ingame.json', 'live/snapshots': 'snapshots.json' };
  const db = { doc: path => ({ onSnapshot(cb, err) {
    const file = FILES[path]; if (!file) { err && err({ code: 'not_found' }); return () => {}; }
    let last = null;
    const load = () => fetch(file + '?_=' + Date.now(), { cache: 'no-store' })
      .then(r => { if (!r.ok) throw { code: 'http_' + r.status }; return r.text(); })
      .then(t => { if (t === last) return; last = t; const d = JSON.parse(t); cb({ exists: true, id: path, data: () => d }); })
      .catch(e => err && err(e));
    load(); const id = setInterval(load, REFRESH); return () => clearInterval(id); } }) };

  // vestavěný prohlížeč -> přímý CORS fetch na Leaguepedii; poll() dostane JSON jako text stránky
  const tabs = {}; let seq = 0;
  const lpUrl = u => { const x = new URL(u); if (x.hostname !== 'lol.fandom.com') throw { code: 'not_in_manifest' };
    x.searchParams.set('origin', '*'); return x.toString(); };
  const mcp = { async callTool(server, tool, args = {}) {
    if (server !== 'host:claude_browser') throw { code: 'server_not_connected' };
    if (tool === 'preview_start') { const id = 'sa' + (++seq); tabs[id] = lpUrl(args.url); return { content: [{ type: 'text', text: 'Started tabId ' + id }] }; }
    if (tool === 'navigate') { const id = args.tabId || Object.keys(tabs).pop(); tabs[id] = lpUrl(args.url); return { content: [{ type: 'text', text: 'ok' }] }; }
    if (tool === 'get_page_text') { const url = tabs[args.tabId || Object.keys(tabs).pop()]; if (!url) throw { code: 'no_tab' };
      let r; try { r = await fetch(url, { credentials: 'omit', cache: 'no-store' }); } catch (e) { throw { code: 'síť' }; }
      if (!r.ok) throw { code: 'HTTP ' + r.status };
      const t = await r.text(); return { payload: t.slice(0, args.max_chars || t.length) }; }
    throw { code: 'not_in_manifest' }; } };

  window.__STANDALONE__ = true;
  window.__standaloneUse = n => Promise.resolve(n === 'db' ? db : n === 'mcp' ? mcp : null);  // sample -> null
})();
</script>
"""

# po hlavním skriptu: čtení přenosu (sample) neexistuje -> tichá vypínka s hláškou, nepřepisuje stav Leaguepedie
AFTER = r"""<script>
(() => {
  const note = () => { let n = document.getElementById('sa-bc-note'); const st = document.getElementById('au-status');
    if (!n && st) { n = document.createElement('p'); n.id = 'sa-bc-note'; n.className = 'au-st';
      n.textContent = 'Čtení přenosu (pick po picku a stav hry) je dostupné jen v aplikaci Claude. Tady se draft načítá z Leaguepedie po hrách, stav hry zadáš ručně.';
      st.after(n); } };
  window.bcPoll = async () => { try { stopBC(); } catch (e) {} note(); };
})();
</script>
"""

CU_RE = re.compile(r"const cu = n => \(window\.claude && window\.claude\.use\)[^\n;]*;")


def main():
    tpl = open(P('page_template.html'), encoding='utf-8').read()
    if '__DATA__' not in tpl: sys.exit('šablona nemá __DATA__')
    html, n = CU_RE.subn("const cu = n => window.__standaloneUse(n);", tpl, count=1)
    if n != 1: sys.exit('definice cu() v šabloně nenalezena – uprav CU_RE')
    i = html.find('<script>'); j = html.rfind('</script>') + len('</script>')
    if i < 0 or j < len('</script>'): sys.exit('hlavní <script> nenalezen')
    lf = ''   # živý feed lolesports (window + details -> in-game + scoreboard); přepisuje bcPoll z AFTER, proto až za ním
    for c in (P('live_feed.js'), P('deploy/live_feed.js')):
        if os.path.exists(c): lf = '<script>\n' + open(c, encoding='utf-8').read() + '\n</script>\n'; break
    html = html[:i] + SHIM + html[i:j] + AFTER + lf + html[j:]
    d = page_data()
    html = html.replace('__DATA__', json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    if '<!doctype' not in html[:200].lower():   # šablona je fragment (skeleton dodává Claude) -> doplnit pro statický hosting
        html = ('<!doctype html>\n<html lang="cs">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
                + html + '\n</body>\n</html>\n')
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8').write(html)
    json.dump(matches(d), open(os.path.join(SITE, 'matches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if os.path.exists(P('data/odds.json')):
        shutil.copyfile(P('data/odds.json'), os.path.join(SITE, 'odds.json'))
    if os.path.exists(P('data/ingame_model.json')):   # stejný tvar jako live/ingame (feats, coef, intercept, n_games)
        shutil.copyfile(P('data/ingame_model.json'), os.path.join(SITE, 'ingame.json'))
    if not os.path.exists(os.path.join(SITE, 'snapshots.json')):
        json.dump(dict(matches=[]), open(os.path.join(SITE, 'snapshots.json'), 'w'))
    print('standalone ok', os.path.join(SITE, 'index.html'), len(html))


if __name__ == '__main__':
    main()
