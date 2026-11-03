"""Model vs. trh (Polymarket, cena těsně před začátkem) na mezinárodních zápasech."""
import json, re, math, numpy as np, pandas as pd
import model as M
MK = json.load(open("data/market_hist.json"))
S = pd.read_csv("data/intl_series_predictions.csv")
E = pd.read_csv("data/intl_predictions.csv")
shrink = json.load(open("data/app_data.json"))["shrink"]
low = lambda x: re.sub(r"[^a-z0-9]", "", str(x).lower().split(" (")[0])
rows = []
for m in MK:
    if m["p_pre"] is None or not (0.01 < m["p_pre"] < 0.99): continue
    d = m["start"][:10]; a, b = low(m["a"]), low(m["b"])
    dates = {d, (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")}
    if m["game"] == 0:
        s = S[S.date.isin(dates) & (((S.A.map(low) == a) & (S.B.map(low) == b)) | ((S.A.map(low) == b) & (S.B.map(low) == a)))]
        if len(s) != 1: continue
        s = s.iloc[0]; flip = low(s.A) != a
        pg = s.p_game_base if not flip else 1 - s.p_game_base
        pm = pg if s.bo == 1 else M.bo_prob(0.5 + shrink * (pg - 0.5), int(s.bo))
        rows.append(dict(kind="série", date=d, a=m["a"], b=m["b"], market=m["p_pre"], model=pm, y=m["winA"], bo=int(s.bo)))
    elif m["game"] == 1:   # jen 1. hra: cena trhu je z doby před sérií, model nesmí znát výsledek předchozí hry
        g = E[E.date.isin(dates) & (((E.blue.map(low) == a) & (E.red.map(low) == b)) | ((E.blue.map(low) == b) & (E.red.map(low) == a)))].sort_index()
        if len(g) < m["game"]: continue
        r = g.iloc[m["game"] - 1]; flip = low(r.blue) != a
        for col, lab in (("lr_base", "hra (před draftem)"), ("lr_draft", "hra (po draftu)")):
            p = r[col] if not flip else 1 - r[col]
            yy = r.y if not flip else 1 - r.y
            if yy != m["winA"]: break   # nesedí párování
            rows.append(dict(kind=lab, date=d, a=m["a"], b=m["b"], market=m["p_pre"], model=p, y=m["winA"], bo=1))
R = pd.DataFrame(rows)
res = {}
for k, g in R.groupby("kind"):
    y = g.y.values
    blend = 0.5 * g.market + 0.5 * g.model
    # sázka 1 jednotky, když model vidí aspoň 5 bodů hodnoty (bez poplatků, kurz = 1/cena)
    pnl = []
    for r in g.itertuples():
        if r.model - r.market >= 0.05: pnl.append((1 / r.market - 1) if r.y == 1 else -1)
        elif r.market - r.model >= 0.05: pnl.append((1 / (1 - r.market) - 1) if r.y == 0 else -1)
    res[k] = dict(n=len(g), period=f"{g.date.min()} – {g.date.max()}",
                  ll_market=round(M.logloss(y, g.market.values), 4), ll_model=round(M.logloss(y, g.model.values), 4), ll_blend=round(M.logloss(y, blend.values), 4),
                  acc_market=round(float(np.mean((g.market > .5) == (y == 1))), 4), acc_model=round(float(np.mean((g.model > .5) == (y == 1))), 4),
                  bets=len(pnl), roi=round(float(np.mean(pnl)), 4) if pnl else None, profit=round(float(np.sum(pnl)), 2) if pnl else 0)
json.dump(res, open("data/market_eval.json", "w"), ensure_ascii=False, indent=1)
R.to_csv("data/market_rows.csv", index=False)
print(json.dumps(res, ensure_ascii=False, indent=1))
