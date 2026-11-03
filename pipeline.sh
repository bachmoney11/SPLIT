#!/bin/bash
# Celá obnova dat a modelu (cca 30–40 min bez cache). Spouštět ve složce s kódem.
set -e
mkdir -p data/html
python3 scrape.py            # Match History všech turnajů -> data/games.csv (+ cache)
python3 rebuild.py           # doplní useknuté stránky, odstraní duplicity
python3 pb.py                # pořadí draftů 2025–2026
echo '{"k_player": 12, "k_region": 30, "season_regress": 0.1, "k_intl_player": 12}' > data/best_kw.json
python3 evaluate.py > data/eval.log
python3 draft_model.py > /dev/null
python3 schedule.py
python3 simulate.py
python3 market_hist.py || true
python3 market_eval.py || true
python3 icons.py || true
python3 build_page.py
