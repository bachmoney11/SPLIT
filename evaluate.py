"""Zpětný test (walk-forward) na mezinárodních turnajích + export výsledků."""
import json, itertools, sys, math, collections
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
import model as M

df = M.load()
df["sid"] = M.series_ids(df)
intl_mask = df.kind == "intl"


def tune():
    """Ladění hyperparametrů jen na mezinárodních hrách 2013–2020 (2021+ = čistý test)."""
    grid = dict(k_player=[12, 16, 24], k_region=[22, 30, 40, 55], season_regress=[0.1, 0.2, 0.3], k_intl_player=[12, 24, 36])
    m = intl_mask & df.year.between(2013, 2020)
    best = None
    for vals in itertools.product(*grid.values()):
        kw = dict(zip(grid, vals))
        _, F = M.run(df, **kw)
        ll = M.logloss(df.y[m].values, F.p_elo[m].values)
        print(kw, round(ll, 4), file=sys.stderr, flush=True)
        if best is None or ll < best[0]:
            best = (ll, kw)
    return best[1]


best_kw = tune() if "--tune" in sys.argv else json.load(open('data/best_kw.json'))
print("best", best_kw, file=sys.stderr); json.dump(best_kw, open("data/best_kw.json", "w"))
eng, F = M.run(df, **best_kw)
D = pd.concat([df, F], axis=1)
I = D[intl_mask].copy()
I["start"] = I.groupby("tournament").date.transform("min")

# základní "regionální" baseline: historická úspěšnost regionu proti regionu před turnajem
def region_prior(train, rb, rr):
    a = train[(train.reg_b == rb) & (train.reg_r == rr)]
    b = train[(train.reg_b == rr) & (train.reg_r == rb)]
    w = a.y.sum() + (len(b) - b.y.sum()); n = len(a) + len(b)
    return (w + 5) / (n + 10)

ABL = {"forma+vzajemne": ["form_diff", "h2h"], "forma": ["form_diff"], "vzajemne": ["h2h"], "patch": ["draft_champ", "draft_patch"],
       "synergie": ["draft_champ", "draft_syn"], "protipicky": ["draft_champ", "draft_ctr"], "draft_v0": ["draft_champ", "draft_comfort"], "vse_draft": ["draft_champ", "draft_comfort", "draft_patch", "draft_syn", "draft_ctr"]}
preds = {k: np.full(len(I), np.nan) for k in ["lr_v1", "lr_base", "lr_draft", "region"] + ["abl_" + a for a in ABL]}
I = I.reset_index(drop=True)
for (tour, start), g in I.groupby(["tournament", "start"], sort=False):
    train = I[I.date < start]
    if len(train) < 150:
        continue
    sets = [("lr_v1", M.FEATS_V1), ("lr_base", M.FEATS_BASE), ("lr_draft", M.FEATS_DRAFT)] + [("abl_" + a, M.FEATS_V1 + f) for a, f in ABL.items()]
    for name, feats in sets:
        lr = LogisticRegression(C=1.0).fit(train[feats].values, train.y.values)
        preds[name][g.index] = lr.predict_proba(g[feats].values)[:, 1]
    preds["region"][g.index] = [region_prior(train, a, b) for a, b in zip(g.reg_b, g.reg_r)]
for k, v in preds.items():
    I[k] = v

E = I[I.lr_base.notna() & (I.year >= 2015)].copy()
E["blue_rate"] = 0.5
for y in sorted(E.year.unique()):
    E.loc[E.year == y, "blue_rate"] = I[I.year < y].y.mean()

models = {"Hod mincí (50 %)": None, "Modrá strana": "blue_rate", "Jen region vs. region": "region",
          "Elo (hráči+tým+region)": "p_elo", "Model v0.1": "lr_v1", "Model (bez draftu)": "lr_base", "Model + draft": "lr_draft"}


def metrics(sub):
    out = {}
    for name, col in models.items():
        p = np.full(len(sub), 0.5) if col is None else sub[col].values
        y = sub.y.values
        acc = float(np.mean((p > 0.5) == (y == 1))) if col else 0.5
        out[name] = dict(acc=round(acc, 4), logloss=round(M.logloss(y, p), 4),
                         brier=round(float(np.mean((p - y) ** 2)), 4))
    return out


res = dict(params=best_kw, n_games_total=int(len(df)), n_intl_games=int(intl_mask.sum()),
           n_tournaments=int(df.tournament.nunique()),
           first_date=df.date.min(), last_date=df.date.max())
res["games_all"] = metrics(E); res["n_eval_games"] = int(len(E))
res["games_test_2021"] = metrics(E[E.year >= 2021]); res["n_test_games"] = int((E.year >= 2021).sum())
T21 = E[E.year >= 2021]
res["ablation"] = {a: dict(ll=round(M.logloss(T21.y.values, T21["abl_" + a].values), 4), acc=round(float(np.mean((T21["abl_" + a] > .5) == (T21.y == 1))), 4)) for a in ABL}
res["ablation"]["v0.1"] = dict(ll=round(M.logloss(T21.y.values, T21.lr_v1.values), 4), acc=round(float(np.mean((T21.lr_v1 > .5) == (T21.y == 1))), 4))

# --- série ---
S = []
for sid, g in E.groupby("sid"):
    g = g.sort_index()
    first = g.iloc[0]
    teamA = first.blue
    wins = collections.Counter(g.winner)
    winner = wins.most_common(1)[0][0]
    lose = sum(wins.values()) - wins[winner]
    if wins[winner] not in (1, 2, 3) or lose >= wins[winner] or (wins[winner] == 1 and len(g) > 1):
        continue  # neplatná rekonstrukce série (tiebreaky apod.) – nehodnotit
    n = {1: 1, 2: 3, 3: 5}[wins[winner]]
    row = dict(sid=sid, tournament=first.tournament, year=first.year, date=first.date,
               A=teamA, B=first.red, winner=winner, bo=n,
               score=f"{wins[teamA]}-{wins[first.red]}", yA=int(winner == teamA),
               regA=first.reg_b, regB=first.reg_r, p_game_base=float(first.lr_base))
    for col in ["p_elo", "lr_v1", "lr_base", "region"]:
        row[col] = M.bo_prob(float(first[col]), n)
    S.append(row)
S = pd.DataFrame(S)
res["series"] = {}
for col, name in (("region", "Jen region vs. region"), ("p_elo", "Elo (hráči+tým+region)"), ("lr_v1", "Model v0.1"), ("lr_base", "Model (bez draftu)")):
    for lab, sub in (("all", S), ("test_2021", S[S.year >= 2021]), ("bo5", S[S.bo == 5])):
        res["series"].setdefault(lab, {})[name] = dict(
            acc=round(float(np.mean((sub[col] > 0.5) == (sub.yA == 1))), 4),
            logloss=round(M.logloss(sub.yA.values, sub[col].values), 4), n=int(len(sub)))

# --- přesnost po letech a po turnajích ---
res["by_year"] = [dict(year=int(y), n=int(len(g)),
                       acc_model=round(float(np.mean((g.lr_base > .5) == (g.y == 1))), 4),
                       acc_region=round(float(np.mean((g.region > .5) == (g.y == 1))), 4),
                       ll_model=round(M.logloss(g.y.values, g.lr_base.values), 4))
                  for y, g in E.groupby("year")]
res["by_tournament"] = [dict(t=t, n=int(len(g)), acc=round(float(np.mean((g.lr_base > .5) == (g.y == 1))), 4),
                             ll=round(M.logloss(g.y.values, g.lr_base.values), 4))
                        for t, g in E.groupby("tournament", sort=False)]
# kalibrace
bins = np.linspace(0.5, 1.0, 6)
fav = np.where(E.lr_base >= .5, E.lr_base, 1 - E.lr_base)
favwin = np.where(E.lr_base >= .5, E.y, 1 - E.y)
res["calibration"] = [dict(lo=round(lo, 2), hi=round(hi, 2), n=int(((fav >= lo) & (fav < hi + 1e-9)).sum()),
                           pred=round(float(fav[(fav >= lo) & (fav < hi + 1e-9)].mean()), 3),
                           actual=round(float(favwin[(fav >= lo) & (fav < hi + 1e-9)].mean()), 3))
                      for lo, hi in zip(bins[:-1], bins[1:]) if ((fav >= lo) & (fav < hi + 1e-9)).sum() > 0]
# největší překvapení (série)
S["fav_p"] = np.maximum(S.lr_base, 1 - S.lr_base)
S["upset"] = ((S.lr_base > .5) != (S.yA == 1))
res["upsets"] = S[S.upset & (S.bo >= 3)].sort_values("fav_p", ascending=False).head(12)[
    ["date", "tournament", "A", "B", "score", "winner", "fav_p", "bo"]].round(3).to_dict("records")

# finální váhy modelu (trénink na všech mezinárodních hrách)
lr = LogisticRegression(C=1.0).fit(I[M.FEATS_DRAFT].values, I.y.values)
res["weights"] = dict(zip(M.FEATS_DRAFT + ["intercept"], [round(float(x), 4) for x in list(lr.coef_[0]) + [lr.intercept_[0]]]))
lr_b = LogisticRegression(C=1.0).fit(I[M.FEATS_BASE].values, I.y.values)
res["weights_base"] = dict(zip(M.FEATS_BASE + ["intercept"], [round(float(x), 4) for x in list(lr_b.coef_[0]) + [lr_b.intercept_[0]]]))

# --- aktuální stav: region, týmy, hráči ---
res["regions_now"] = sorted([dict(region=k, offset=round(v, 1), n=int(eng.Rn[k])) for k, v in eng.R.items() if eng.Rn[k] >= 20],
                            key=lambda x: -x["offset"])
# region po letech (offset na konci každé mezinárodní sezóny) – přepočet
traj = collections.defaultdict(dict)
e2 = M.Engine(**best_kw)
for r in df.itertuples():
    e2.new_season(r.year); e2.update(r)
    if r.kind == "intl":
        for k in M.MAJOR:
            if e2.Rn[k] >= 10:
                traj[r.year][k] = round(e2.R[k], 1)
res["region_by_year"] = {int(y): v for y, v in traj.items()}

last_date = pd.Timestamp(df.date.max())
recent = df[pd.to_datetime(df.date) >= last_date - pd.Timedelta(days=150)]
team_last = {}
for r in recent.itertuples():
    team_last[r.blue] = r.blue_roster; team_last[r.red] = r.red_roster
teams = []
for t, ros in team_last.items():
    rr, n = eng.roster_rating(ros)
    if rr is None: continue
    reg = eng.region(t)
    teams.append(dict(team=t, region=reg, roster=ros, player=round(rr, 1), team_elo=round(eng.T[t], 1),
                      region_off=round(eng.R[reg], 1), exp=round(n, 1)))
res["teams_now"] = sorted(teams, key=lambda x: -(0.6 * x["player"] + 0.4 * x["team_elo"] + x["region_off"]))[:60]
res["players_now"] = sorted([dict(player=p, rating=round(v, 1), games=int(eng.Pn[p]))
                             for p, v in eng.P.items() if eng.Pn[p] >= 60 and any(p in ros.split("|") for ros in team_last.values())],
                            key=lambda x: -x["rating"])[:40]
res["latest_intl"] = df[intl_mask].tournament.iloc[-1]
json.dump(res, open("data/results.json", "w"), ensure_ascii=False, indent=1, default=float)
E.to_csv("data/intl_predictions.csv", index=False)
S.to_csv("data/intl_series_predictions.csv", index=False)
print(json.dumps({k: res[k] for k in ["games_test_2021", "series", "ablation", "weights", "weights_base"]}, ensure_ascii=False, indent=1))
