"""Worlds 2026: aktuální síla týmů, simulace zbytku turnaje a data pro živý draft."""
import json, math, random, collections, datetime as dt
import numpy as np, pandas as pd
import model as M
import draft_model as DM

res = json.load(open("data/results.json"))
kw = res["params"]
df = M.load()
eng, F = M.run(df, **kw)
wb, wd = res["weights_base"], res["weights"]

# --- korekce sérií: hry v sérii nejsou nezávislé -> pravděpodobnost hry stáhnout k 50 % ---
S = pd.read_csv("data/intl_series_predictions.csv")
S["pg"] = S.p_game_base
best = (9, 1.0)
sub = S[(S.year < S.year.max()) & (S.bo > 1)]   # jen Bo3/Bo5, bez aktuální sezóny (walk-forward)
for k in np.linspace(0.6, 1.0, 41):
    p = [M.bo_prob(0.5 + k * (g - 0.5), n) for g, n in zip(sub.pg, sub.bo)]
    best = min(best, (M.logloss(sub.yA.values, np.array(p)), k))
SHRINK = round(float(best[1]), 3)

W = df[df.tournament.str.startswith("2026 Season World Championship/Main Event")]
roster, org = {}, {}
for r in W.itertuples():
    roster[r.blue] = r.blue_roster; roster[r.red] = r.red_roster
    org[r.blue] = r.org_blue; org[r.red] = r.org_red
SHORT = {"Dplus Kia": "DK", "Gen.G": "GEN", "Invictus Gaming": "iG", "T1": "T1", "Top Esports": "TES",
         "Bilibili Gaming": "BLG", "Hanwha Life Esports": "HLE", "Karmine Corp": "KC",
         "LYON (2024 American Team)": "LYON", "LØS": "LØS", "Movistar KOI": "MKOI",
         "CTBC Flying Oyster": "CFO", "G2 Esports": "G2", "Team Liquid": "TL",
         "Anyone's Legend": "AL", "Team Secret Whales": "TSW"}
REGION_LABEL = {"KR": "LCK", "CN": "LPL", "EU": "LEC", "NA": "LCS", "BR": "CBLOL", "PCS": "LCP", "VN": "VCS"}
teams = {}
for t, ros in roster.items():
    pr, n = eng.roster_rating(ros)
    reg = eng.region(t)
    teams[t] = dict(name=t.split(" (")[0], short=SHORT.get(t, t[:4]), region=reg, org=org[t],
                    league=REGION_LABEL.get(reg, reg), roster=ros.split("|"),
                    player=pr, team=eng.T[org[t]], reg=eng.R[reg], exp=math.log1p(n),
                    form=eng.form[org[t]])
H2H = {a: {b: eng.h2h[(teams[a]["org"], teams[b]["org"])][0] / (eng.h2h[(teams[a]["org"], teams[b]["org"])][1] + 4)
           for b in teams if b != a} for a in teams}


def feat(a, b):
    A, B = teams[a], teams[b]
    return dict(player_diff=(A["player"] - B["player"]) / 100, team_diff=(A["team"] - B["team"]) / 100,
                region_diff=(A["reg"] - B["reg"]) / 100, exp_diff=A["exp"] - B["exp"],
                form_diff=A["form"] - B["form"], h2h=H2H[a][b])


def p_game(a, b):
    """Neutrální strana: průměr pravděpodobnosti za modrou a za červenou."""
    def side(x, y):
        f = feat(x, y)
        z = wb["intercept"] + sum(wb[k] * f[k] for k in M.FEATS_BASE)
        return 1 / (1 + math.exp(-z))
    return 0.5 * (side(a, b) + 1 - side(b, a))


def p_series(a, b, n):
    g = p_game(a, b)
    return g if n == 1 else M.bo_prob(0.5 + SHRINK * (g - 0.5), n)


# --- Swiss: bilance spočítané přímo z dat ---
sw = W[W.tournament.str.endswith("Main Event")]
rec = collections.defaultdict(lambda: [0, 0])
# ve Swissu se dvojice nikdy neopakuje -> série = všechny hry dané dvojice (datumy přecházejí přes půlnoc UTC)
for pair, g in sw.groupby(sw.apply(lambda r: frozenset((r.blue, r.red)), axis=1)):
    w = collections.Counter(g.winner); win = w.most_common(1)[0][0]; lose = [t for t in pair if t != win][0]
    rec[win][0] += 1; rec[lose][1] += 1
REC = {t: f"{a}-{b}" for t, (a, b) in rec.items()}

# --- Vyřazovací část podle rozpisu Leaguepedie (schedule.py -> data/schedule.json) ---
SCH = json.load(open("data/schedule.json"))
CODE = {"KCORP": "Karmine Corp", "LYON24": "LYON (2024 American Team)", "LOS": "LØS", "Dplus": "Dplus Kia", "DK": "Dplus Kia",
        "GEN": "Gen.G", "GEN.G": "Gen.G", "TES": "Top Esports", "IG": "Invictus Gaming", "BLG": "Bilibili Gaming", "T1": "T1",
        "HLE": "Hanwha Life Esports", "MKOI": "Movistar KOI", "G2": "G2 Esports", "TL": "Team Liquid", "CFO": "CTBC Flying Oyster",
        "AL CN": "Anyone's Legend", "TSW": "Team Secret Whales"}
tid = lambda c: CODE.get(c, next((t for t in teams if teams[t]["short"].lower() == (c or "").lower() or t.lower() == (c or "").lower()), None)) if c else None
KO = {"Quarterfinals": [], "Semifinals": [], "Finals": []}
for m in SCH:
    if m["tab"] in KO: KO[m["tab"]].append(m)
QF_ORDER = [1, 2, 3, 4]           # SF1 = vítěz QF1 (DK–BLG) proti vítězi QF2 (KC–T1), SF2 = QF3 proti QF4 (Leaguepedia pavouk)
qf = sorted(KO["Quarterfinals"], key=lambda m: QF_ORDER.index(m["order"]) if m["order"] in QF_ORDER else 9)
sf = sorted(KO["Semifinals"], key=lambda m: m["order"]); fi = KO["Finals"]
def res(m):
    w = m.get("winner"); return (tid(m["t1"]) if w == "1" else tid(m["t2"]) if w == "2" else None)

def winner(a, b, n, rng):
    return a if rng.random() < p_series(a, b, n) else b

def sim(N=40000, seed=7):
    rng = random.Random(seed)
    cnt = {k: collections.Counter() for k in ["sf", "final", "champ"]}
    slot = collections.defaultdict(collections.Counter)
    for _ in range(N):
        w1 = [res(m) or winner(tid(m["t1"]), tid(m["t2"]), 5, rng) for m in qf]
        for i, t in enumerate(w1): cnt["sf"][t] += 1; slot[f"SF{i // 2 + 1}{'ab'[i % 2]}"][t] += 1
        w2 = []
        for i in range(2):
            a, b = w1[2 * i], w1[2 * i + 1]
            m = sf[i] if i < len(sf) else None
            r = res(m) if m and tid(m["t1"]) else None
            w2.append(r or winner(a, b, 5, rng))
        for i, t in enumerate(w2): cnt["final"][t] += 1; slot[f"F{'ab'[i]}"][t] += 1
        r = res(fi[0]) if fi and tid(fi[0]["t1"]) else None
        cnt["champ"][r or winner(w2[0], w2[1], 5, rng)] += 1
    return {k: {t: v / N for t, v in c.items()} for k, c in cnt.items()}, {k: {t: round(v / N, 4) for t, v in c.most_common(4)} for k, c in slot.items()}

SIM, SLOT = sim()
inko = {tid(m["t1"]) for m in qf} | {tid(m["t2"]) for m in qf}
out_teams = []
for t, d in teams.items():
    r = REC.get(t, "0-0")
    lost = any(res(m) and res(m) != t and t in (tid(m["t1"]), tid(m["t2"])) for m in qf + sf + fi)
    status = "vyřazen" if (t not in inko or lost) else "ve hře"
    out_teams.append(dict(id=t, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()},
                          rec=r, status=status, qf=1.0 if t in inko else 0.0, sf=round(SIM["sf"].get(t, 0), 4),
                          final=round(SIM["final"].get(t, 0), 4), champ=round(SIM["champ"].get(t, 0), 4)))
out_teams.sort(key=lambda x: (-x["champ"], -x["sf"], -x["player"]))
import zoneinfo
PRG = zoneinfo.ZoneInfo("Europe/Prague")
def prague(u):
    if not u: return ""
    x = dt.datetime.fromisoformat(u.replace("Z", "+00:00")).astimezone(PRG); return f"{x.day}. {x.month}. {x:%H:%M}"
ROLE = ["top", "jungle", "mid", "ADC", "support"]
last = pd.Timestamp(df.date.max())
def why(a, b):
    """Fakta pro krátké zdůvodnění tipu (z pohledu týmu a)."""
    if not (a and b): return None
    A, B = teams[a], teams[b]; f = feat(a, b)
    contrib = {k: round(wb[k] * f[k], 3) for k in M.FEATS_BASE}
    def form(t):
        o = teams[t]["org"]; g = df[(pd.to_datetime(df.date) >= last - pd.Timedelta(days=45)) & ((df.org_blue == o) | (df.org_red == o))]
        w = int(((g.org_blue == o) & (g.y == 1)).sum() + ((g.org_red == o) & (g.y == 0)).sum()); return [w, int(len(g) - w)]
    def star(t):
        ros = teams[t]["roster"]; i = int(np.argmax([eng.P[p] for p in ros])); return [ros[i].split(" (")[0], ROLE[i] if i < 5 else ""]
    oa, ob = A["org"], B["org"]
    h = df[((df.org_blue == oa) & (df.org_red == ob)) | ((df.org_blue == ob) & (df.org_red == oa))]
    h = h[pd.to_datetime(h.date) >= last - pd.Timedelta(days=730)]
    hw = int(((h.org_blue == oa) & (h.y == 1)).sum() + ((h.org_red == oa) & (h.y == 0)).sum())
    return dict(contrib=contrib, form_a=form(a), form_b=form(b), star_a=star(a), star_b=star(b), h2h=[hw, int(len(h) - hw)],
                rec_a=REC.get(a, ""), rec_b=REC.get(b, ""))

def mrec(m, stage):
    a, b = tid(m["t1"]), tid(m["t2"])
    return dict(stage=stage, order=m["order"], a=a, b=b, bo=m["bo"], utc=m["utc"], time=prague(m["utc"]),
                s1=m["s1"], s2=m["s2"], winner=res(m), p=round(p_series(a, b, m["bo"]), 4) if a and b else None,
                p_game=round(p_game(a, b), 4) if a and b else None, why=why(a, b))
bracket = dict(qf=[mrec(m, "Čtvrtfinále") for m in qf], sf=[mrec(m, "Semifinále") for m in sf], f=[mrec(m, "Finále") for m in fi], slot=SLOT)
allm = bracket["qf"] + bracket["sf"] + bracket["f"]
upcoming = [m for m in allm if not m["winner"]]
day = upcoming[0]["time"].split(" ")[:2] if upcoming else None
r5 = sorted([m for m in upcoming if m["a"] and m["b"]], key=lambda m: m["utc"] or "")
# --- data pro živý draft ---
ST = DM.Stats(pd.Timestamp(df.date.max()) + pd.Timedelta(days=1))
meta_champs = [c for c in ST.champs if ST.meta.get(c, 0) >= 0.004 or ST.role.get(c, np.zeros(5)).sum() > 0]
rel = set(c for c in meta_champs if ST.meta.get(c, 0) >= 0.01)
cur_patch = W.patch.iloc[-1]
lo = lambda w, n, k: math.log((w + k) / (n - w + k))
champ_tab = {}
for c in meta_champs:
    w, n = eng.champ[c]; pw, pn = eng.patch[(cur_patch, c)]
    champ_tab[c] = dict(m=round(ST.meta.get(c, 0), 4), r=[round(float(x), 3) for x in ST.role.get(c, np.zeros(5))],
                        s=round(lo(w, n, 10), 4), ps=round(lo(pw, pn, 15), 4), w=int(w), n=int(n))
players = {p for t in teams.values() for p in t["roster"]}
pool = collections.defaultdict(dict)
for (p, c), n in ST.pool.items():
    if p in players and c in champ_tab: pool[p][c] = n
comfort = collections.defaultdict(dict)
for (p, c), (w, n) in eng.pc.items():
    if p in players and c in champ_tab and n >= 1: comfort[p][c] = int(n)
tpick = {t: {c: n for (tt, c), n in ST.tpick.items() if tt == t and c in champ_tab} for t in teams}
tban = {t: {c: n for (tt, c), n in ST.tban.items() if tt == t and c in champ_tab} for t in teams}
syn = {f"{a}|{b}": round(lo(w, n, 20), 3) for (a, b), (w, n) in eng.syn.items() if a in rel and b in rel and n >= 2}
ctr = {f"{i}|{a}|{b}": round(lo(w, n, 15), 3) for (i, a, b), (w, n) in eng.ctr.items() if a in rel and b in rel and n >= 2}
# pro predikci picku: protipick/synergie podle okna 540 dní (stejně jako při tréninku)
pctr = {f"{a}|{b}": round(lo(w, n, 6), 3) for (a, b), (w, n) in ST.ctr.items() if a in rel and b in rel and n >= 2}
psyn = {f"{a}|{b}": round(lo(w, n, 8), 3) for (a, b), (w, n) in ST.syn.items() if a in rel and b in rel and n >= 2}
# Fearless: šampioni už použití v sériích Swiss kola 5 (doplní se ručně v nástroji)
dm = json.load(open("data/draft_model.json"))
live = dict(patch=cur_patch, champs=champ_tab, pool=pool, comfort=comfort, tpick=tpick, tban=tban,
            syn=syn, ctr=ctr, pctr=pctr, psyn=psyn, pick_w=dm["final"]["pick"], ban_w=dm["final"]["ban"],
            draft_eval={k: dm[k] for k in ("pick", "ban")})
app = dict(updated=df.date.max(), shrink=SHRINK, teams=out_teams, r5=r5, bracket=bracket, h2h=H2H,
           weights_base=wb, weights_draft=wd, live=live)
json.dump(app, open("data/app_data.json", "w"), ensure_ascii=False, separators=(",", ":"))
for t in out_teams:
    print(f'{t["short"]:5} {t["league"]:6} {t["rec"]:4} pl={t["player"]:.0f} form={t["form"]:+.2f}  QF {t["qf"]:.2f} SF {t["sf"]:.2f} F {t["final"]:.2f} W {t["champ"]:.3f}')
print(r5, "shrink", SHRINK, "patch", cur_patch)
print(len(champ_tab), len(syn), len(ctr), len(pctr), len(psyn), len(json.dumps(app)))
