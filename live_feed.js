/* SPLIT – živá data z lolesports (verze mimo Claude).
   Nahrazuje „čtení přenosu“: místo Clauda čte veřejný feed, který používá web lolesports.com.
   - esports-api.lolesports.com: běžící zápas Worlds, hry v sérii, strany a týmy
   - feed.lolesports.com/livestats: každých 10 s zlato, killy, věže, draci, barony, inhibitory a šampioni s rolemi
   Bany ani picky během champion selectu feed nemá -> bany dál z Leaguepedie, picky naskočí při načtení hry.
   Test bez živého zápasu: ?replay=<gameId>&min=15 (přehraje uloženou hru od dané minuty).
   Vkládá build_standalone.py za hlavní skript stránky; používá jeho globální funkce (applyBroadcast, DS, ORDER…). */
(() => {
  const KEY = '0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z';   // veřejný klíč webu lolesports.com, není to tajemství
  const API = 'https://esports-api.lolesports.com/persisted/gw/', FEED = 'https://feed.lolesports.com/livestats/v1/';
  const LEAGUE = 'worlds', TICK = 10000, FIND_EVERY = 60000, LAG = 45000;
  const ROLE = { top: 0, jungle: 1, mid: 2, bottom: 3, support: 4 };
  const FIX = { MonkeyKing: 'Wukong', Nunu: 'Nunu & Willump', Renata: 'Renata Glasc' };
  const qs = new URLSearchParams(location.search), REPLAY = qs.get('replay'), REPLAY_MIN = +(qs.get('min') || 15);
  const LF = { timer: null, game: null, lastFind: 0, busy: false, replayT: null };
  const api = p => fetch(API + p + (p.includes('?') ? '&' : '?') + 'hl=en-US', { headers: { 'x-api-key': KEY }, cache: 'no-store' })
    .then(r => { if (!r.ok) throw { code: 'api ' + r.status }; return r.json(); });
  const feed = (gid, t) => fetch(FEED + 'window/' + gid + (t ? '?startingTime=' + t : ''), { cache: 'no-store' })
    .then(r => r.status === 200 ? r.json() : null);
  const iso10 = ms => { const d = new Date(ms); d.setUTCMilliseconds(0); d.setUTCSeconds(Math.floor(d.getUTCSeconds() / 10) * 10); return d.toISOString(); };
  const ch = id => champ(FIX[id] || id);

  function note(t) { let n = document.getElementById('sa-bc-note'); const st = document.getElementById('au-status');
    if (!n && st) { n = document.createElement('p'); n.id = 'sa-bc-note'; n.className = 'au-st ok'; st.after(n); }
    if (n) n.textContent = t; }

  // najde rozehranou hru Worlds -> {gid, n, blue, red} (týmy jako id stránky)
  async function findGame() {
    if (REPLAY) return LF.game || { gid: REPLAY, n: 1, blue: null, red: null, replay: true };
    const live = await api('getLive'); const ev = (live.data.schedule.events || []).find(e => e.league && e.league.slug === LEAGUE && e.state === 'inProgress');
    if (!ev) return null;
    const det = await api('getEventDetails?id=' + ev.id), m = det.data.event.match, code = {};
    m.teams.forEach(t => code[t.id] = t.code);
    const g = m.games.find(x => x.state === 'inProgress') || null; if (!g) return { gid: null, waiting: m.games.filter(x => x.state === 'completed').length + 1, teams: m.teams.map(t => t.code) };
    const side = s => teamId(code[(g.teams.find(t => t.side === s) || {}).id]);
    return { gid: g.id, n: g.number, blue: side('blue'), red: side('red') };
  }

  // picky z metadat hry; bany a pořadí kroků z toho, co už načetla Leaguepedia
  function applyDraft(G) {
    if (!G.meta) return;
    const st = state(), bans = { blue: st.blue.bans.slice(), red: st.red.bans.slice() };
    const picks = { blue: G.meta.blue, red: G.meta.red }, used = { blue: { pick: 0, ban: 0 }, red: { pick: 0, ban: 0 } }, steps = [];
    for (const [fs, kind] of ORDER) { const side = sideOf(fs);
      if (kind === 'ban') { steps.push({ c: bans[side][used[side].ban++] || '–', r: null }); continue; }
      const p = picks[side][used[side].pick++]; if (!p) break; steps.push({ c: p.c, r: p.r }); }
    DS.steps = steps; liveUpdate();
  }
  // Leaguepedia (applyGame) by draft přepsala zkratkami -> po ní znovu doplnit picky z feedu
  const _applyGame = window.applyGame;
  window.applyGame = (...a) => { _applyGame(...a); const G = LF.game; if (G && G.meta && $('ld-blue').value === G.blue && $('ld-red').value === G.red) applyDraft(G); };

  function applyFrame(G, f) {
    const b = f.blueTeam, r = f.redTeam, min = (new Date(f.rfc460Timestamp) - G.t0) / 60000;
    const drk = t => t.dragons.filter(d => d !== 'elder').length, soul = t => drk(t) >= 4;
    if (b.barons > (G.bar.blue || 0)) G.barAt = ['blue', min]; if (r.barons > (G.bar.red || 0)) G.barAt = ['red', min];
    G.bar = { blue: b.barons, red: r.barons };
    const baron = G.barAt && min - G.barAt[1] < 3 ? G.barAt[0] : 'none';
    $('ig-s').value = soul(b) ? 1 : soul(r) ? -1 : 0;
    $('ig-i').value = r.inhibitors > b.inhibitors ? -1 : b.inhibitors > r.inhibitors ? 1 : 0;   // inhibitors = kolik jich tým zničil
    const herald = $('ig-h').value, grubs = $('ig-gr').value;   // feed je nemá -> nechat, co zadal uživatel
    applyBroadcast({ phase: 'game', minute: Math.max(1, min), gold_blue: b.totalGold, gold_red: r.totalGold, kills_blue: b.totalKills, kills_red: r.totalKills,
      towers_blue: b.towers, towers_red: r.towers, dragons_blue: drk(b), dragons_red: drk(r), baron });
    $('ig-h').value = herald; $('ig-gr').value = grubs; ingame();
    return min;
  }

  async function tick() {
    if (LF.busy) return; LF.busy = true;
    try {
      if (!LF.game || !LF.game.gid || Date.now() - LF.lastFind > FIND_EVERY) {
        LF.lastFind = Date.now(); const g = await findGame();
        if (!g) { LF.game = null; note('Živá data lolesports: teď se žádný zápas Worlds nehraje. Draft a výsledky dál z Leaguepedie.'); return; }
        if (!g.gid) { LF.game = null; note(`Živá data lolesports: ${g.teams.join(' – ')} · čeká se na hru ${g.waiting} (champion select). Picky naskočí při načtení hry.`); return; }
        if (!LF.game || LF.game.gid !== g.gid) LF.game = { ...g, t0: null, meta: null, bar: {}, barAt: null };
      }
      const G = LF.game;
      if (!G.t0) {   // první okno hry: start a šampioni
        const w = await feed(G.gid); if (!w || !w.frames || !w.frames.length) { note('Živá data lolesports: hra se načítá…'); return; }
        G.t0 = new Date(w.frames[0].rfc460Timestamp).getTime();
        const md = w.gameMetadata, mp = t => t.participantMetadata.map(p => ({ c: ch(p.championId), r: ROLE[p.role] ?? null }));
        G.meta = { blue: mp(md.blueTeamMetadata), red: mp(md.redTeamMetadata) }; G.patch = md.patchVersion;
        if (G.blue && G.red) { $('ld-blue').value = G.blue; $('ld-red').value = G.red; $('ld-game').value = String(G.n); }
        if (G.replay) LF.replayT = G.t0 + REPLAY_MIN * 60000;
        applyDraft(G);
      }
      const t = G.replay ? (LF.replayT += TICK) : Date.now() - LAG;
      const w = await feed(G.gid, iso10(t)); const f = w && w.frames && w.frames[w.frames.length - 1];
      if (!f) { note('Živá data lolesports: čekám na další data…'); return; }
      const min = applyFrame(G, f);
      const st = f.gameState === 'finished' ? 'hra skončila' : f.gameState === 'paused' ? 'pauza' : `${Math.floor(min)}. minuta`;
      note(`Živá data lolesports · ${G.blue ? T[G.blue].short + ' – ' + T[G.red].short + ' · ' : ''}hra ${G.n} · ${st} · ${new Date().toLocaleTimeString('cs-CZ')} (zpoždění ~1 min)`);
      if (f.gameState === 'finished') { LF.game = null; LF.lastFind = Date.now(); }
    } catch (e) { note('Živá data lolesports se nepodařilo načíst (' + ((e && e.code) || 'síť') + '), zkusím znovu.'); }
    finally { LF.busy = false; }
  }
  // tlačítko „Zapnout živý draft“ volá bcPoll a pak ho opakuje (BC.timer); vlastní 10s smyčka běží, dokud je BC.timer zapnutý
  window.bcPoll = async () => { if (LF.timer) return; tick();
    LF.timer = setInterval(() => { if (!BC.timer) { clearInterval(LF.timer); LF.timer = null; return; } tick(); }, TICK); };
  if (REPLAY) setTimeout(() => $('au-on').click(), 500);
})();
