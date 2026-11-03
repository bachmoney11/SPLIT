"""Predikce dalšího picku/banu v živém draftu (conditional logit).

Kandidát = šampion, který ještě není zabanovaný/vybraný v této hře ani použitý
v předchozích hrách série (Fearless). Rysy kandidáta:
  meta     – log podílu her, kde byl šampion pickem nebo banem (posledních 60 dní profi scény)
  pool     – zkušenost hráče na otevřené roli s tímto šampionem (posledních 365 dní)
  role     – pravděpodobnost, že šampion sedí na některou z otevřených rolí
  team     – kolikrát ho tým pickl / zabanoval za posledních 120 dní
  counter  – úspěšnost proti už vybranému soupeři na stejné roli
  synergy  – úspěšnost ve dvojici s už vybranými šampiony vlastního týmu
  slot     – jak brzy se šampion na mezinárodní scéně typicky bere (1. fáze = priorita)
Trénink: drafty 2025 (First Stand, MSI, Worlds); test: 2026.
"""
import json, math, collections, datetime as dt
import numpy as np, pandas as pd
import model as M

G = M.load()
G["d"] = pd.to_datetime(G.date)
DR = json.load(open("data/drafts.json"))


def tour_start(t):
    base = t.split("/Picks and Bans")[0]
    sub = G[G.tournament.str.startswith(base.split("/")[0])]
    sub = sub[sub.tournament.str.startswith(base)] if len(sub[sub.tournament.str.startswith(base)]) else sub
    return sub.d.min() if len(sub) else pd.Timestamp("2026-10-15")


class Stats:
    """Statistiky dostupné před datem `asof` (žádný únik z budoucnosti)."""
    def __init__(self, asof):
        self.asof = asof
        H = G[G.d < asof]
        rec = H[H.d >= asof - pd.Timedelta(days=60)]
        n = max(len(rec), 1)
        pres = collections.Counter()
        for c in ("blue_picks", "red_picks", "blue_bans", "red_bans"):
            for x in rec[c]:
                for ch in set(x.split("|")):
                    if ch: pres[ch] += 1
        self.meta = {c: v / n for c, v in pres.items()}
        Y = H[H.d >= asof - pd.Timedelta(days=365)]
        self.role = collections.defaultdict(lambda: np.zeros(5))
        self.pool = collections.Counter()
        self.pool_w = collections.Counter()
        for r in Y.itertuples():
            for picks, ros, win in ((r.blue_picks, r.blue_roster, r.y), (r.red_picks, r.red_roster, 1 - r.y)):
                ps, pl = picks.split("|"), ros.split("|")
                for i, c in enumerate(ps[:5]):
                    self.role[c][i] += 1
                    if i < len(pl):
                        self.pool[(pl[i], c)] += 1; self.pool_w[(pl[i], c)] += win
        for c in self.role:
            self.role[c] = self.role[c] / self.role[c].sum()
        T = H[H.d >= asof - pd.Timedelta(days=120)]
        self.tpick, self.tban = collections.Counter(), collections.Counter()
        for r in T.itertuples():
            for team, picks, bans in ((r.blue, r.blue_picks, r.blue_bans), (r.red, r.red_picks, r.red_bans)):
                for c in picks.split("|"): self.tpick[(team, c)] += 1
                for c in bans.split("|"): self.tban[(team, c)] += 1
        Z = H[H.d >= asof - pd.Timedelta(days=540)]
        self.ctr, self.syn = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0])
        for r in Z.itertuples():
            bp, rp = r.blue_picks.split("|"), r.red_picks.split("|")
            for i in range(min(5, len(bp), len(rp))):
                self.ctr[(bp[i], rp[i])][0] += r.y; self.ctr[(bp[i], rp[i])][1] += 1
                self.ctr[(rp[i], bp[i])][0] += 1 - r.y; self.ctr[(rp[i], bp[i])][1] += 1
            for side, win in ((bp, r.y), (rp, 1 - r.y)):
                for i in range(len(side)):
                    for j in range(i + 1, len(side)):
                        k = tuple(sorted((side[i], side[j]))); self.syn[k][0] += win; self.syn[k][1] += 1
        self.champs = sorted(set(self.meta) | {c for c in self.role if self.role[c].sum() > 0})


def roster_of(team, asof):
    H = G[(G.d < asof + pd.Timedelta(days=40)) & ((G.blue == team) | (G.red == team))].tail(1)
    if not len(H): return [""] * 5
    r = H.iloc[0]
    return (r.blue_roster if r.blue == team else r.red_roster).split("|")


FEATS = ["meta", "pool", "role", "team", "counter", "synergy"]


def cand_feats(S, c, kind, own, opp, own_ros, opp_ros, own_picks, opp_picks, open_roles, opp_open):
    lo = lambda w, n, k: math.log((w + k) / (n - w + k))
    rp = S.role.get(c, np.zeros(5))
    roles = open_roles if kind == "pick" else opp_open
    ros = own_ros if kind == "pick" else opp_ros
    fit = max([rp[i] for i in roles] or [0])
    pool = max([math.log1p(S.pool[(ros[i], c)]) * (rp[i] > 0.05) for i in roles] or [0]) if ros else 0
    team = math.log1p(S.tpick[(own, c)]) if kind == "pick" else math.log1p(S.tban[(own, c)])
    counter = sum(lo(*S.ctr[(c, o)], 6) for o in opp_picks) if kind == "pick" else 0.0
    syn = sum(lo(*S.syn[tuple(sorted((c, o)))], 8) for o in own_picks) if kind == "pick" else 0.0
    return [math.log(S.meta.get(c, 0) + 0.003), pool, math.log(fit + 0.01), team, counter, syn]


def build(games):
    """Vrátí seznam rozhodnutí: (matice rysů kandidátů, index skutečné volby, typ)."""
    out = []
    cache = {}
    prev_key, used = None, set()
    for g in games:
        base = g["tournament"].split("/Picks and Bans")[0]
        if base not in cache:
            asof = tour_start(g["tournament"]); cache[base] = (Stats(asof), asof)
        S, asof = cache[base]
        pair = (base, frozenset((g["first"], g["second"])))
        if pair != prev_key: used = set()
        prev_key = pair
        ros = {g["first"]: roster_of(g["first"], asof), g["second"]: roster_of(g["second"], asof)}
        taken, picks, oroles = set(), {"F": [], "S": []}, {"F": set(range(5)), "S": set(range(5))}
        for side, kind, champ, role in g["seq"]:
            own = g["first"] if side == "F" else g["second"]; o = "S" if side == "F" else "F"
            opp = g["second"] if side == "F" else g["first"]
            cands = [c for c in S.champs if c not in taken and c not in used]
            if champ in cands and champ:
                X = np.array([cand_feats(S, c, kind, own, opp, ros[own], ros[opp], picks[side], picks[o], oroles[side], oroles[o]) for c in cands])
                out.append((X, cands.index(champ), kind, g["tournament"]))
            if champ:
                taken.add(champ)
            if kind == "pick" and champ:
                picks[side].append(champ)
                if role is not None: oroles[side].discard(role)
        used |= {c for _, k, c, _ in g["seq"] if k == "pick" and c}
    return out


def fit(dec, kind, iters=800, lr=0.25):
    w = np.zeros(len(FEATS))
    D = [(X, y) for X, y, k, _ in dec if k == kind]
    for it in range(iters):
        g = np.zeros_like(w)
        for X, y in D:
            z = X @ w; p = np.exp(z - z.max()); p /= p.sum()
            g += X[y] - p @ X
        w += lr * g / len(D)
    return w


def topk(dec, w, kind, ks=(1, 3, 5)):
    D = [(X, y) for X, y, k, _ in dec if k == kind]
    ranks = [int((X @ w > (X @ w)[y]).sum()) for X, y in D]
    return {f"top{k}": round(float(np.mean([r < k for r in ranks])), 3) for k in ks} | {"n": len(D)}


if __name__ == "__main__":
    train = [g for g in DR if g["tournament"].startswith("2025")]
    test = [g for g in DR if g["tournament"].startswith("2026")]
    dtr, dte = build(train), build(test)
    res = {}
    for kind in ("pick", "ban"):
        w = fit(dtr, kind)
        meta_only = np.zeros(len(FEATS)); meta_only[0] = 1
        res[kind] = dict(weights=dict(zip(FEATS, [round(float(x), 3) for x in w])),
                         test=topk(dte, w, kind), baseline_meta=topk(dte, meta_only, kind))
    # finální váhy natrénované na všem (pro živý nástroj)
    dall = dtr + dte
    res["final"] = {k: [round(float(x), 4) for x in fit(dall, k)] for k in ("pick", "ban")}
    json.dump(res, open("data/draft_model.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
