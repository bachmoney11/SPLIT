/* SPLIT – živá data z lolesports (verze mimo Claude).
   Nahrazuje „čtení přenosu“: místo Clauda čte veřejný feed, který používá web lolesports.com.
   - esports-api.lolesports.com: běžící zápas Worlds, hry v sérii, strany a týmy
   - feed.lolesports.com/livestats: každých 10 s zlato, killy, věže, draci, barony, inhibitory a šampioni s rolemi (window)
     + po hráčích K/D/A, CS, zlato, úroveň a předměty (details) -> renderScoreboard()
   Feed vrací 400 pro startingTime mladší než ~60 s -> LAG 75 s a při 400 zkusit o 30 s starší čas (max 3×).
   Bany ani picky během champion selectu feed nemá -> bany dál z Leaguepedie, picky naskočí při načtení hry.
   Test bez živého zápasu: ?replay=<gameId>&min=15 (přehraje uloženou hru od dané minuty).
   Vkládá build_standalone.py za hlavní skript stránky; používá jeho globální funkce (applyBroadcast, renderScoreboard, DS, ORDER…). */
(() => {
  const KEY = '0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z';   // veřejný klíč webu lolesports.com, není to tajemství
  const API = 'https://esports-api.lolesports.com/persisted/gw/', FEED = 'https://feed.lolesports.com/livestats/v1/';
  const LEAGUE = 'worlds', TICK = window.__STANDALONE__ ? 10000 : 15000, FIND_EVERY = 60000, LAG = 75000, BACK = 30000, RETRY = 3;
  const ROLE = { top: 0, jungle: 1, mid: 2, bottom: 3, support: 4 };
  const FIX = { MonkeyKing: 'Wukong', Nunu: 'Nunu & Willump', Renata: 'Renata Glasc', Kaisa: "Kai'Sa", KSante: "K'Sante", Belveth: "Bel'Veth", Chogath: "Cho'Gath", Khazix: "Kha'Zix", Velkoz: "Vel'Koz", Kogmaw: "Kog'Maw", Reksai: "Rek'Sai" };
  const qs = new URLSearchParams(location.search), REPLAY = qs.get('replay'), REPLAY_MIN = +(qs.get('min') || 15);
  const LF = { timer: null, game: null, lastFind: 0, busy: false, replayT: null };
  const SA = !!window.__STANDALONE__;            // GitHub verze = přímý fetch; v Claude jde všechno přes vestavěný prohlížeč
  const PROBE = 'https://bachmoney11.github.io/SPLIT/?probe=1';   // GitHub stránka v režimu probe vypíše běžící hru jako JSON
  const BT = { tab: null };
  async function browserText(url, wait) {        // Claude: otevřít URL ve vestavěném prohlížeči a vrátit text stránky
    const mcp = await cu('mcp'); if (!mcp) throw { code: 'not_granted' };
    if (!BT.tab) { const r = await mcp.callTool('host:claude_browser', 'preview_start', { url }); const m = JSON.stringify(r.payload ?? r.content).match(/tabId ([\w-]+)/); BT.tab = m ? m[1] : null; }
    else await mcp.callTool('host:claude_browser', 'navigate', { url, tabId: BT.tab });
    for (let k = 0; k < (wait || 1); k++) {
      if (k) await new Promise(r => setTimeout(r, 1500));
      const r = await mcp.callTool('host:claude_browser', 'get_page_text', BT.tab ? { tabId: BT.tab, max_chars: 400000 } : { max_chars: 400000 });
      const t = (typeof r.payload === 'string' ? r.payload : (r.content || []).map(c => c.text || '').join('\n')).split('\n\nTab Context')[0];
      const i = t.indexOf('{'), j = t.lastIndexOf('}');
      if (i >= 0 && j > i) { try { return JSON.parse(t.slice(i, j + 1)); } catch (e) {} }
    }
    return null;
  }
  const api = p => fetch(API + p + (p.includes('?') ? '&' : '?') + 'hl=en-US', { headers: { 'x-api-key': KEY }, cache: 'no-store' })
    .then(r => { if (!r.ok) throw { code: 'api ' + r.status }; return r.json(); });
  // 200 -> JSON, 400 -> 400 (čas je moc čerstvý), jinak null
  const feed = (kind, gid, t) => { const url = FEED + kind + '/' + gid + (t ? '?startingTime=' + t : '');
    if (!SA) return browserText(url).then(j => j && j.frames ? j : 400);   // chybová stránka feedu (400) nemá JSON se snímky
    return fetch(url, { cache: 'no-store' }).then(r => r.status === 200 ? r.json() : r.status === 400 ? 400 : null); };
  const iso10 = ms => { const d = new Date(ms); d.setUTCMilliseconds(0); d.setUTCSeconds(Math.floor(d.getUTCSeconds() / 10) * 10); return d.toISOString(); };
  // při 400 zkusit o 30 s starší čas, nejvýš 3×; vrací {w, t} nebo null
  async function feedAt(kind, gid, t) {
    for (let k = 0; k <= RETRY; k++) { const tt = t - k * BACK, w = await feed(kind, gid, iso10(tt)); if (w !== 400) return w ? { w, t: tt } : null; }
    return null;
  }
  const ch = id => champ(FIX[id] || id) || FIX[id] || id;
  const known = id => id && typeof T !== 'undefined' && T[id];

  function note(t) { let n = document.getElementById('sa-bc-note'); const st = document.getElementById('au-status');
    if (!n && st) { n = document.createElement('p'); n.id = 'sa-bc-note'; n.className = 'au-st ok'; st.after(n); }
    if (n) n.textContent = t; }

  // najde rozehranou hru Worlds -> {gid, n, blue, red, codes} (týmy jako id stránky, codes = zkratky z lolesports)
  async function findGame() {
    if (REPLAY) return LF.game || { gid: REPLAY, n: 1, blue: null, red: null, codes: {}, replay: true };
    if (!SA) { const j = await browserText(PROBE + '&_=' + Date.now(), 8); if (!j || !j.probe) throw { code: 'probe' }; return j.none ? null : j; }
    const live = await api('getLive'); const ev = (live.data.schedule.events || []).find(e => e.league && e.league.slug === LEAGUE && e.state === 'inProgress');
    if (!ev) return null;
    const det = await api('getEventDetails?id=' + ev.id), m = det.data.event.match, code = {};
    m.teams.forEach(t => code[t.id] = t.code);
    const wins = m.teams.map(t => t.code + ' ' + ((t.result && t.result.gameWins) || 0)).join(' : ');   // skóre série z lolesports
    const g = m.games.find(x => x.state === 'inProgress') || null; if (!g) return { gid: null, waiting: m.games.filter(x => x.state === 'completed').length + 1, teams: m.teams.map(t => t.code), wins };
    const sc = s => code[(g.teams.find(t => t.side === s) || {}).id] || null;
    const tid = c => { const id = teamId(c); return known(id) ? id : null; };   // tým mimo data stránky -> nechat výběr, jak je
    return { gid: g.id, n: g.number, blue: tid(sc('blue')), red: tid(sc('red')), codes: { blue: sc('blue'), red: sc('red') }, wins };
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
    const drk = t => (t.dragons || []).filter(d => d !== 'elder').length, soul = t => drk(t) >= 4;
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

  // window snímek + details snímek -> vstup renderScoreboard
  function scoreboard(G, f, df, min) {
    if (typeof renderScoreboard !== 'function' || !G.md) return;
    const det = {}; ((df && df.participants) || []).forEach(p => det[p.participantId] = p);
    const side = (s, t, meta) => {
      const live = {}; (t.participants || []).forEach(p => live[p.participantId] = p);
      const short = known(G[s]) ? T[G[s]].short : null;
      const tc = G.codes[s] || short || ((meta.participantMetadata[0] || {}).summonerName || '').split(' ')[0] || (s === 'blue' ? 'MODRÁ' : 'ČERVENÁ');
      const players = meta.participantMetadata.map(m => { const p = live[m.participantId] || {}, d = det[m.participantId] || {}, nm = m.summonerName || '';
        const pre = nm.split(' ')[0]; const name = nm.includes(' ') && (pre === tc || pre === G.codes[s] || pre === short) ? nm.slice(pre.length + 1) : nm;
        return { name, champ: ch(m.championId), role: m.role, k: d.kills ?? p.kills, d: d.deaths ?? p.deaths, a: d.assists ?? p.assists,
          cs: d.creepScore ?? p.creepScore, gold: p.totalGold ?? d.totalGoldEarned, lvl: d.level ?? p.level, items: d.items || [] }; });
      return { team: tc, gold: t.totalGold, kills: t.totalKills, towers: t.towers, dragons: t.dragons || [], barons: t.barons, inhib: t.inhibitors, players };
    };
    renderScoreboard({ minute: min, blue: side('blue', f.blueTeam, G.md.blueTeamMetadata), red: side('red', f.redTeam, G.md.redTeamMetadata),
      src: 'lolesports.com · zpoždění ~1 min' + (df ? '' : ' · předměty se načítají') });
  }

  async function tick() {
    if (LF.busy) return; LF.busy = true;
    try {
      if (!LF.game || !LF.game.gid || Date.now() - LF.lastFind > FIND_EVERY) {
        LF.lastFind = Date.now(); const g = await findGame();
        if (!g) { LF.game = null; note('Živá data lolesports: teď se žádný zápas Worlds nehraje. Draft a výsledky dál z Leaguepedie.'); return; }
        if (!g.gid) { LF.game = null; note(`Série ${g.wins} · ${LF.last ? LF.last + ' · ' : ''}čeká se na hru ${g.waiting}. Picky naskočí, jakmile hra začne (feed nemá champion select).`); return; }
        if (!LF.game || LF.game.gid !== g.gid) LF.game = { ...g, t0: null, meta: null, md: null, bar: {}, barAt: null };
        LF.game.wins = g.wins;
      }
      const G = LF.game;
      if (!G.t0) {   // první okno hry: start a šampioni
        const w = await feed('window', G.gid); if (!w || w === 400 || !w.frames || !w.frames.length) { note(`Série ${G.wins || ''} · ${LF.last ? LF.last + ' · ' : ''}hra ${G.n}: champion select / čeká se na start. Picky a scoreboard naskočí se startem hry (~1,5 min zpoždění).`); return; }
        G.t0 = new Date(w.frames[0].rfc460Timestamp).getTime();
        const md = w.gameMetadata, mp = t => t.participantMetadata.map(p => ({ c: ch(p.championId), r: ROLE[p.role] ?? null }));
        G.md = md; G.meta = { blue: mp(md.blueTeamMetadata), red: mp(md.redTeamMetadata) }; G.patch = md.patchVersion;
        if (G.blue && G.red) { $('ld-blue').value = G.blue; $('ld-red').value = G.red; $('ld-game').value = String(G.n); }
        if (G.replay) LF.replayT = G.t0 + REPLAY_MIN * 60000;
        applyDraft(G);
      }
      const t = G.replay ? (LF.replayT += TICK) : Date.now() - LAG;
      const ws = await feedAt('window', G.gid, t), f = ws && ws.w.frames && ws.w.frames[ws.w.frames.length - 1];
      if (!f) { note('Živá data lolesports: čekám na další data…'); return; }
      const ds = await feedAt('details', G.gid, ws.t).catch(() => null), df = ds && ds.w.frames && ds.w.frames[ds.w.frames.length - 1];
      const min = applyFrame(G, f);
      scoreboard(G, f, df, min);
      const st = f.gameState === 'finished' ? 'hra skončila' : f.gameState === 'paused' ? 'pauza' : `${Math.floor(min)}. minuta`;
      const teams = known(G.blue) && known(G.red) ? T[G.blue].short + ' – ' + T[G.red].short : G.codes.blue ? G.codes.blue + ' – ' + G.codes.red : '';
      note(`Živá data lolesports · ${G.wins ? 'série ' + G.wins + ' · ' : ''}${teams ? teams + ' · ' : ''}hra ${G.n} · ${st} · ${new Date().toLocaleTimeString('cs-CZ')} (zpoždění ~${Math.round((Date.now() - ws.t) / 60000 * 2) / 2 || 1} min)`);
      if (f.gameState === 'finished') {   // poslední scoreboard nechat viditelný, vítěz podle zničeného Nexu = víc zlata/inhibitorů není jisté -> skóre série z API při dalším hledání
        LF.last = `hra ${G.n} skončila (${teams || 'konečný stav nahoře'}, killy ${f.blueTeam.totalKills}:${f.redTeam.totalKills})`;
        LF.game = null; LF.lastFind = 0; }
    } catch (e) { console.warn('live_feed', e); note('Živá data lolesports se nepodařilo načíst (' + ((e && e.code) || 'síť') + '), zkusím znovu.'); }
    finally { LF.busy = false; }
  }
  // tlačítko „Zapnout živý draft“ volá bcPoll a pak ho opakuje (BC.timer); vlastní 10s smyčka běží, dokud je BC.timer zapnutý
  window.bcPoll = async () => { if (LF.timer) return; tick();
    LF.timer = setInterval(() => { if (!BC.timer) { clearInterval(LF.timer); LF.timer = null; return; } tick(); }, TICK); };
  if (REPLAY) setTimeout(() => $('au-on').click(), 500);
  if (SA && qs.get('probe')) findGame().then(g => { document.body.innerText = JSON.stringify(Object.assign({ probe: 1 }, g || { none: 1 })); })
    .catch(e => { document.body.innerText = JSON.stringify({ probe: 1, error: (e && e.code) || 'síť' }); });
})();
