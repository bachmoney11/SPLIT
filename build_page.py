"""Složí data/page_data.json a rift_prognoza.html ze šablony."""
import json, os
r = json.load(open('data/results.json')); a = json.load(open('data/app_data.json'))
keep = dict(games_test=r['games_test_2021'], series=r['series'], by_year=r['by_year'], ablation=r['ablation'],
  calibration=r['calibration'], upsets=r['upsets'], region_by_year=r['region_by_year'], regions_now=r['regions_now'],
  n=dict(total=r['n_games_total'], intl=r['n_intl_games'], tours=r['n_tournaments'], ev=r['n_eval_games'], test=r['n_test_games']))
keep.update(a)
if os.path.exists('data/icons.json'): keep['icons'] = json.load(open('data/icons.json'))
import os
if os.path.exists('data/market_eval.json'): keep['market'] = json.load(open('data/market_eval.json'))
s = json.dumps(keep, ensure_ascii=False, separators=(',', ':'))
open('data/page_data.json', 'w').write(s)
open('rift_prognoza.html', 'w').write(open('page_template.html').read().replace('__DATA__', s))
print('page ok', len(s))
