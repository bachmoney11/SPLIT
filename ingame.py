"""Model šance na výhru během hry (z pohledu modré strany) z minutových timeline."""
import json, glob, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
import model as M

def snapshots(d, gid):
    rows = []; ev = sorted(d["ev"], key=lambda e: e[0])
    for fr in d["frames"]:
        t = fr["m"]
        if t < 3: continue
        s = dict(gid=gid, m=t, y=int(d["win"] == 100), gd=fr["g"] / 1000, gdr=fr["g"] / max(fr["gt"], 1) * 10, xpd=fr["xp"] / 1000, csd=fr["cs"] / 10)
        k = {100: 0, 200: 0}; tw = {100: 0, 200: 0}; inh = {100: 0, 200: 0}; dr = {100: 0, 200: 0}; hr = {100: 0, 200: 0}; gr = {100: 0, 200: 0}
        ba = {100: 0, 200: 0}; soul = {100: 0, 200: 0}; el = {100: 0, 200: 0}; inhopen = {100: 0, 200: 0}; pl = {100: 0, 200: 0}; at = {100: 0, 200: 0}
        for e in ev:
            if e[0] > t: break
            ty, tm = e[1], e[2]
            if tm not in (100, 200): continue
            if ty == "k": k[tm] += 1
            elif ty == "TOWER_BUILDING": tw[tm] += 1
            elif ty == "INHIBITOR_BUILDING": inh[tm] += 1; inhopen[tm] += 1 if t - e[0] < 5 else 0
            elif ty == "DRAGON":
                if (len(e) > 3 and "ELDER" in str(e[3])):
                    el[tm] += 1 if t - e[0] < 2.5 else 0
                else: dr[tm] += 1
            elif ty == "RIFTHERALD": hr[tm] += 1
            elif ty == "HORDE": gr[tm] += 1
            elif ty == "BARON_NASHOR": ba[tm] += 1 if t - e[0] < 3 else 0
            elif ty == "ATAKHAN": at[tm] += 1
            elif ty == "SOUL": soul[tm] = 1
            elif ty == "PLATE": pl[tm] += 1
        d2 = lambda x: x[100] - x[200]
        s.update(kd=d2(k), twd=d2(tw), inhd=d2(inh), inho=d2(inhopen), drd=d2(dr), hrd=d2(hr), grd=d2(gr), bar=d2(ba), eld=d2(el), soul=d2(soul), atk=d2(at), pld=d2(pl))
        rows.append(s)
    return rows

R = []
for f in glob.glob("data/tl/*.json"):
    d = json.load(open(f))
    if d and d.get("frames"): R += snapshots(d, f.split("/")[-1][:-5])
S = pd.DataFrame(R)
S["mm"] = S.m / 30
for c in ["gd", "gdr", "xpd", "kd", "twd", "drd"]:
    S[c + "_t"] = S[c] * S.mm          # význam se mění s časem
BASE = ["gd"]
FULL = ["gd", "gd_t", "gdr", "xpd", "xpd_t", "csd", "kd", "twd", "twd_t", "inhd", "inho", "drd", "drd_t", "hrd", "grd", "bar", "eld", "soul", "atk", "pld"]
res = {}
for name, feats in (("jen zlato", BASE), ("plný model", FULL)):
    P = np.zeros(len(S))
    for tr, te in GroupKFold(5).split(S, S.y, S.gid):
        m = LogisticRegression(C=0.5, max_iter=2000).fit(S.iloc[tr][feats].values, S.y.iloc[tr].values)
        P[te] = m.predict_proba(S.iloc[te][feats].values)[:, 1]
    S["p_" + name] = P
    out = {}
    for mn in (5, 10, 15, 20, 25):
        g = S[(S.m >= mn - .01) & (S.m < mn + 1)]
        out[mn] = dict(n=len(g), ll=round(M.logloss(g.y.values, g["p_" + name].values), 3), acc=round(float(np.mean((g["p_" + name] > .5) == (g.y == 1))), 3))
    res[name] = out
print("her:", S.gid.nunique(), "snímků:", len(S))
for k, v in res.items(): print(k, v)
m = LogisticRegression(C=0.5, max_iter=2000).fit(S[FULL].values, S.y.values)
json.dump(dict(feats=FULL, coef=[round(float(x), 4) for x in m.coef_[0]], intercept=round(float(m.intercept_[0]), 4), eval=res, n_games=int(S.gid.nunique())), open("data/ingame_model.json", "w"), indent=1)
print(dict(zip(FULL, np.round(m.coef_[0], 3))))
