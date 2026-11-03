"""Predikční model pro mezinárodní LoL zápasy.

Vrstvy:
  1) Elo hráčů – každý hráč má rating, síla týmu = průměr pěti hráčů v sestavě
     (zvládá přestupy i přejmenování týmů).
  2) Elo týmu – klasické Elo podle názvu týmu (kontinuita organizace).
  3) Síla regionu – offset pro každý region, učí se POUZE z mezinárodních her.
  4) Draft (v0) – síla vybraných šampionů na aktuálních patchích + komfort hráče
     na šampionovi.
Kombinace přes logistickou regresi trénovanou jen na minulých mezinárodních hrách
(walk-forward – žádný únik dat z budoucnosti).
"""
import math, collections
import numpy as np
import pandas as pd

REGION_FOLD = {"TW": "PCS", "AM": None}  # AM = LTA společná fáze -> region z North/South
# týmy z doby před regionálními ligami (2011–2014) a pár výjimek
MANUAL_REGION = {"SK Telecom T1": "KR", "Samsung Ozone": "KR", "Azubu Frost": "KR", "NaJin Sword": "KR",
    "Against All authority": "EU", "Fnatic": "EU", "Team gamed!de": "EU", "GamingGear.eu": "EU", "SK Gaming": "EU",
    "Moscow Five": "CIS", "TSM": "NA", "Epik Gamer": "NA", "Counter Logic Gaming": "NA", "Dignitas": "NA",
    "Taipei Assassins": "TW", "Ahq eSports Club": "TW", "Gamania Bears": "TW", "Invictus Gaming": "CN",
    "World Elite": "CN", "OMG": "CN", "Royal Club": "CN", "Mineski": "SEA", "Bangkok Titans": "SEA",
    "MEGA": "SEA", "Team Pacific": "SEA", "Xan": "SEA", "Saigon Jokers": "VN", "Dark Passage": "TR"}
MAJOR = ["KR", "CN", "EU", "NA", "PCS", "VN", "BR", "JP", "LAT", "TR", "CIS", "OCE", "SEA"]


# přejmenované organizace -> jedna identita pro Elo organizace
TEAM_ALIAS = {"SK Telecom T1": "T1", "Samsung Galaxy": "Gen.G", "KSV eSports": "Gen.G",
    "Longzhu Gaming": "DRX", "Kingzone DragonX": "DRX", "Kiwoom DRX": "DRX", "DragonX": "DRX",
    "DAMWON Gaming": "Dplus Kia", "DWG KIA": "Dplus Kia", "Splyce": "Movistar KOI", "MAD Lions": "Movistar KOI",
    "MAD Lions KOI": "Movistar KOI", "Snake Esports": "LNG Esports", "Topsports Gaming": "Top Esports",
    "Suning": "Weibo Gaming", "Suning Gaming": "Weibo Gaming", "GIGABYTE Marines": "GAM Esports",
    "Afreeca Freecs": "DN Freecs", "Kwangdong Freecs": "DN Freecs", "SANDBOX Gaming": "BNK FEARX",
    "Liiv SANDBOX": "BNK FEARX", "FearX": "BNK FEARX", "Fredit BRION": "OKSavingsBank BRION",
    "BRION": "OKSavingsBank BRION", "Team Dynamics": "Nongshim RedForce"}


def _canon(series, extra=None):
    """Sjednotí varianty jmen lišící se velikostí písmen; vybere nejčastější zápis."""
    cnt = collections.Counter(series)
    best = {}
    for name, n in cnt.items():
        k = name.lower()
        if k not in best or n > cnt[best[k]]:
            best[k] = name
    return {name: best[name.lower()] for name in cnt}


def load(path="data/games.csv"):
    df = pd.read_csv(path, keep_default_na=False)
    clean = lambda x: x.replace(" (page does not exist)", "")
    for c in ("blue_roster", "red_roster"):
        df[c] = df[c].map(lambda r: "|".join(clean(p) for p in r.split("|")))
    players = [p for c in ("blue_roster", "red_roster") for r in df[c] for p in r.split("|") if p]
    pm = _canon(players)
    for c in ("blue_roster", "red_roster"):
        df[c] = df[c].map(lambda r: "|".join(pm.get(p, p) for p in r.split("|")))
    tm = _canon(list(df.blue) + list(df.red) + list(df.winner))
    for c in ("blue", "red", "winner"):
        df[c] = df[c].map(lambda t: tm.get(t, t))
    df["org_blue"] = df.blue.map(lambda t: TEAM_ALIAS.get(t, t))
    df["org_red"] = df.red.map(lambda t: TEAM_ALIAS.get(t, t))
    df["row"] = np.arange(len(df))
    # stránka je seřazena od nejnovější hry -> uvnitř dne otočit pořadí
    df = df.sort_values(["date", "row"], ascending=[True, False]).reset_index(drop=True)
    df["year"] = df.date.str[:4].astype(int)
    df["y"] = (df.winner == df.blue).astype(int)
    return df


def series_ids(df):
    """Seskupí hry do sérií: stejný turnaj, stejná dvojice týmů, stejný den."""
    sid, last, cur = [], {}, 0
    for i, r in df.iterrows():
        k = (r.tournament, frozenset((r.blue, r.red)))
        d = pd.Timestamp(r.date)
        if k in last and (d - last[k][1]).days == 0:
            sid.append(last[k][0]); last[k] = (last[k][0], d)
        else:
            cur += 1; sid.append(cur); last[k] = (cur, d)
    return sid


def p_elo(diff):
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


class Engine:
    def __init__(self, k_player=24, k_team=28, k_region=14, k_intl_player=12,
                 season_regress=0.25, new_player=1450, blue_adv=12):
        self.kp, self.kt, self.kr, self.kip = k_player, k_team, k_region, k_intl_player
        self.reg, self.newp, self.blue_adv = season_regress, new_player, blue_adv
        self.P = collections.defaultdict(lambda: float(self.newp))   # hráči
        self.Pn = collections.Counter()                               # počet her hráče
        self.T = collections.defaultdict(lambda: 1500.0)              # týmy
        self.R = collections.defaultdict(float)                       # regiony (offset)
        self.Rn = collections.Counter()
        self.team_region = {}
        self.year = None
        # draft statistiky
        self.champ = collections.defaultdict(lambda: [0.0, 0.0])      # (výhry, hry) okno
        self.champ_hist = collections.deque()
        self.pc = collections.defaultdict(lambda: [0.0, 0.0])         # hráč+šampion
        self.form = collections.defaultdict(float)                    # forma organizace (EWMA reziduí)
        self.h2h = collections.defaultdict(lambda: [0.0, 0.0])        # vzájemné zápasy (rezidua, počet)
        self.patch = collections.defaultdict(lambda: [0.0, 0.0])      # šampion na konkrétním patchi
        self.syn = collections.defaultdict(lambda: [0.0, 0.0])        # dvojice šampionů ve stejném týmu
        self.ctr = collections.defaultdict(lambda: [0.0, 0.0])        # šampion vs šampion na stejné roli

    # ---------- pomocné ----------
    def new_season(self, year):
        if self.year is not None and year != self.year:
            for d, m in ((self.P, 1500.0), (self.T, 1500.0)):
                for k in d:
                    d[k] = m + (d[k] - m) * (1 - self.reg)
            for k in self.R:
                self.R[k] *= 0.95   # regionální síla se mezi roky jen pomalu vrací k nule (backtest: 0,95 > 0,85)
            for d in (self.h2h, self.syn, self.ctr):
                for k in d:
                    d[k][0] *= 0.5; d[k][1] *= 0.5
            for k in self.form:
                self.form[k] *= 0.5
        self.year = year

    def region(self, team):
        r = self.team_region.get(team) or MANUAL_REGION.get(team, "Other")
        return REGION_FOLD.get(r, r) or "NA"

    def roster_rating(self, roster):
        ps = [p for p in roster.split("|") if p]
        if not ps:
            return None, 0
        return float(np.mean([self.P[p] for p in ps])), float(np.mean([min(self.Pn[p], 200) for p in ps]))

    def draft_score(self, picks, roster):
        """Síla draftu: log-odds šampionů (shrinkage) + komfort hráče na šampionovi."""
        cs, cf = 0.0, 0.0
        ch = [c for c in picks.split("|") if c]
        ps = [p for p in roster.split("|") if p]
        for i, c in enumerate(ch):
            w, n = self.champ[c]
            cs += math.log((w + 10) / (n - w + 10))
            if i < len(ps):
                pw, pn = self.pc[(ps[i], c)]
                cf += math.log1p(pn) / 5.0          # zkušenost s šampionem
        return cs, cf

    def draft_extra(self, r):
        """Patch-meta, synergie a protipicky (z pohledu modré)."""
        bp = [c for c in r.blue_picks.split("|") if c]; rp = [c for c in r.red_picks.split("|") if c]
        lo = lambda w, n, k: math.log((w + k) / (n - w + k))
        pt = sum(lo(*self.patch[(r.patch, c)], 15) for c in bp) - sum(lo(*self.patch[(r.patch, c)], 15) for c in rp)
        sy = 0.0
        for side, s in ((bp, 1), (rp, -1)):
            for i in range(len(side)):
                for j in range(i + 1, len(side)):
                    w, n = self.syn[tuple(sorted((side[i], side[j])))]
                    sy += s * lo(w, n, 20)
        ct = 0.0
        for i in range(min(len(bp), len(rp))):
            w, n = self.ctr[(i, bp[i], rp[i])]
            ct += lo(w, n, 15)
        return pt, sy, ct

    # ---------- predikce / features ----------
    def features(self, r):
        rb, nb = self.roster_rating(r.blue_roster)
        rr, nr = self.roster_rating(r.red_roster)
        if rb is None or rr is None:
            rb, rr, nb, nr = self.T[r.blue], self.T[r.red], 0, 0
        regb, regr = self.region(r.blue), self.region(r.red)
        db, fb = self.draft_score(r.blue_picks, r.blue_roster)
        dr, fr = self.draft_score(r.red_picks, r.red_roster)
        pt, sy, ct = self.draft_extra(r)
        ob, orr = r.org_blue, r.org_red
        hw, hn = self.h2h[(ob, orr)]
        return dict(
            form_diff=self.form[ob] - self.form[orr],
            h2h=hw / (hn + 4),
            draft_patch=pt, draft_syn=sy, draft_ctr=ct,
            player_diff=(rb - rr) / 100.0,
            team_diff=(self.T[ob] - self.T[orr]) / 100.0,
            region_diff=(self.R[regb] - self.R[regr]) / 100.0,
            exp_diff=(math.log1p(nb) - math.log1p(nr)),
            draft_champ=db - dr,
            draft_comfort=fb - fr,
            reg_b=regb, reg_r=regr,
        )

    def elo_prob(self, f):
        """Čistý ratingový odhad (bez učení vah) – hráči + tým + region."""
        d = 100 * (0.6 * f["player_diff"] + 0.4 * f["team_diff"] + f["region_diff"]) + self.blue_adv
        return p_elo(d)

    # ---------- aktualizace ----------
    def update(self, r):
        intl = r.kind == "intl"
        y = r.y
        if not intl and r.league_region:
            reg = REGION_FOLD.get(r.league_region, r.league_region)
            for t in (r.blue, r.red):
                if reg is not None:
                    self.team_region[t] = reg
                elif t not in self.team_region:
                    self.team_region[t] = "NA"
        f = self.features(r)
        p = self.elo_prob(f)
        err = y - p
        kp = self.kip if intl else self.kp
        for roster, s in ((r.blue_roster, 1), (r.red_roster, -1)):
            for pl in [x for x in roster.split("|") if x]:
                k = kp * (2.0 if self.Pn[pl] < 15 else 1.0)
                self.P[pl] += s * k * err
                self.Pn[pl] += 1
        ob, orr = r.org_blue, r.org_red
        self.T[ob] += self.kt * err
        self.T[orr] -= self.kt * err
        self.form[ob] = 0.85 * self.form[ob] + 0.15 * err
        self.form[orr] = 0.85 * self.form[orr] - 0.15 * err
        self.h2h[(ob, orr)][0] += err; self.h2h[(ob, orr)][1] += 1
        self.h2h[(orr, ob)][0] -= err; self.h2h[(orr, ob)][1] += 1
        bp = [c for c in r.blue_picks.split("|") if c]; rp = [c for c in r.red_picks.split("|") if c]
        for side, win in ((bp, y), (rp, 1 - y)):
            for c in side:
                self.patch[(r.patch, c)][0] += win; self.patch[(r.patch, c)][1] += 1
            for i in range(len(side)):
                for j in range(i + 1, len(side)):
                    k = tuple(sorted((side[i], side[j]))); self.syn[k][0] += win; self.syn[k][1] += 1
        for i in range(min(len(bp), len(rp))):
            self.ctr[(i, bp[i], rp[i])][0] += y; self.ctr[(i, bp[i], rp[i])][1] += 1
            self.ctr[(i, rp[i], bp[i])][0] += 1 - y; self.ctr[(i, rp[i], bp[i])][1] += 1
        if intl:
            rb, rr = self.region(r.blue), self.region(r.red)
            if rb != rr:
                self.R[rb] += self.kr * err
                self.R[rr] -= self.kr * err
                self.Rn[rb] += 1; self.Rn[rr] += 1
        # draft statistiky (okno posledních ~4000 her)
        for picks, roster, win in ((r.blue_picks, r.blue_roster, y), (r.red_picks, r.red_roster, 1 - y)):
            ch = [c for c in picks.split("|") if c]
            ps = [p for p in roster.split("|") if p]
            for i, c in enumerate(ch):
                self.champ[c][0] += win; self.champ[c][1] += 1
                self.champ_hist.append((c, win))
                if i < len(ps):
                    self.pc[(ps[i], c)][0] += win; self.pc[(ps[i], c)][1] += 1
        while len(self.champ_hist) > 40000:
            c, w = self.champ_hist.popleft()
            self.champ[c][0] -= w; self.champ[c][1] -= 1
        return f, p


def run(df, **kw):
    """Projde všechny hry chronologicky; vrátí features + elo predikci PŘED každou hrou."""
    e = Engine(**kw)
    out = []
    for r in df.itertuples():
        e.new_season(r.year)
        f, p = e.update(r)
        f["p_elo"] = p
        out.append(f)
    return e, pd.DataFrame(out, index=df.index)


FEATS_V1 = ["player_diff", "team_diff", "region_diff", "exp_diff"]
FEATS_BASE = FEATS_V1
FEATS_DRAFT = FEATS_V1 + ["draft_champ", "draft_patch", "draft_syn"]


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def bo_prob(p, n):
    """Pravděpodobnost výhry série Bo-n z pravděpodobnosti výhry jedné hry."""
    need = n // 2 + 1
    return sum(math.comb(need - 1 + k, k) * p ** need * (1 - p) ** k for k in range(need))
