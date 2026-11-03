# SPLIT – predikce profi LoL na vlastní adrese, aktualizace zdarma

Stránka poběží na adrese `https://<tvoje-jmeno>.github.io/split/`.
Data obnovuje GitHub sám na svých serverech: tvůj počítač ani Claude k tomu nejsou potřeba.
Verze v aplikaci Claude běží dál beze změny, tohle je souběžná kopie.

## Jak to funguje

| Úloha (záložka Actions) | Kdy | Co dělá | Doba |
|---|---|---|---|
| **Ranní obnova** | každý den 10:17 | výsledky z Leaguepedie → model → simulace → nová stránka, doplní vítěze k uloženým tipům | 5–10 min (první běh ~40 min) |
| **Kurzy** | každé 2 hodiny | Polymarket + Kalshi → kurzy na stránce; do 3 h před zápasem uloží tip (průměr modelu a trhu) | ~1 min |
| **Minutová data** | 4× denně | dávka her z Leaguepedie → přeučí model „Během hry“ | do 30 min |
| **Publikace stránky** | po každé z úloh | nahraje složku `site/` na GitHub Pages | ~1 min |

Stránka si kurzy, model „Během hry“ a tipy sama načítá každých 5 minut.

## Co stojí co

- **Veřejný repozitář: 0 Kč.** GitHub Actions i GitHub Pages jsou pro veřejné repozitáře zdarma.
  Kód a stránka budou vidět všem. Žádná hesla ani klíče v projektu nejsou a nikdy je tam nedávej.
- Soukromý repozitář se stránkou stojí 4 USD měsíčně (GitHub Pro). Doporučuji veřejný.

## Postup (jednou, asi 20 minut)

1. **Účet:** otevři https://github.com/signup a zaregistruj se (e-mail, heslo, uživatelské jméno). Zvol plán **Free**.
2. **Repozitář:** vpravo nahoře klikni na **+** → **New repository**. Do *Repository name* napiš `split`,
   zvol **Public**, zaškrtni **Add a README file** a klikni **Create repository**.
3. **Nahrát soubory:** rozbal `split-repo.zip` (dvojklik). V repozitáři klikni **Add file → Upload files**.
   Ve Finderu otevři rozbalenou složku `split`, stiskni **Cmd + Shift + tečka** (ukáže skrytou složku `.github`),
   označ vše (**Cmd + A**) a přetáhni to do okna prohlížeče. Počkej, až se načte seznam souborů, a dole klikni **Commit changes**.
   - Kontrola: v repozitáři musí být vidět složka `.github`. Když chybí, vytvoř 4 soubory ručně:
     **Add file → Create new file**, do názvu napiš `.github/workflows/pipeline.yml`, vlož obsah stejnojmenného
     souboru (otevři ho v TextEditu) a klikni **Commit changes**. Totéž pro `odds.yml`, `timelines.yml` a `deploy.yml`.
4. **Povolit zápis a stránku:**
   - **Settings → Actions → General →** dole *Workflow permissions* → **Read and write permissions → Save**.
   - **Settings → Pages →** *Build and deployment* → *Source*: **GitHub Actions**.
5. **První spuštění:** záložka **Actions** → vlevo **Kurzy** → vpravo **Run workflow → Run workflow**.
   Za ~2 minuty je stránka venku. Pak stejně spusť **Ranní obnova** (poprvé až ~40 minut).
6. **Hotovo:** adresu najdeš v **Settings → Pages** („Your site is live at…“). Ulož si ji do záložek
   nebo na plochu telefonu a pošli ji Claudovi, ať zkontroluje první běh.

## Když něco nejde

- Červený křížek v **Actions** = běh selhal (GitHub pošle e-mail). Klikni na běh a pošli Claudovi snímek nebo text chyby.
- Po Worlds: v `.github/workflows/pipeline.yml` přepiš `2026_Season_World_Championship` na aktuální turnaj
  a v `schedule.py` stránku rozpisu (s tím pomůže Claude).
- Plánované běhy se mohou zpozdit o 5–30 minut, to je u GitHubu normální.
- Repozitář bez změny 60 dní GitHub úlohy uspí. Úlohy samy ukládají data, takže se to stane jen při dlouhé pauze;
  pak stačí v **Actions** kliknout na **Enable workflow**.
- Plánované běhy jsou jen pro kurzy a modely. Živá data běží přímo ve tvém prohlížeči, viz níže.

## Živý draft a data ze hry (v reálném čase)

Na záložce **Live draft** klikni **Zapnout živý draft**. Stránka pak sama:
- každých 10 s čte stav hry z lolesports (stejný zdroj jako oficiální přenos, zpoždění ~1 min): zlato, killy, věže, draci,
  Soul, Baron, inhibitory → panel „Během hry“ a šance na výhru se mění samy,
- ve chvíli načtení hry doplní všech 10 picků s rolemi; bany a stav série doplňuje Leaguepedia (po částech).
- Herald a voidgrubs feed neposílá, ty můžeš doplnit ručně tlačítky.
- Picky během champion selectu (před načtením hry) mimo Claude nejdou, žádný veřejný zdroj je nemá.

**Vyzkoušení bez živého zápasu:** otevři adresu stránky s `?replay=115660540726095094&min=15#live` na konci
(přehraje 1. hru BLG–HLE od 15. minuty, data běží po 10 s).
Zdroj lolesports není oficiálně zdokumentovaný; kdyby ho Riot změnil, stránka dál funguje s Leaguepedií a ručním zadáním.

## Pro vývojáře

`pipeline.sh` = celá obnova (scrape → rebuild → pb → evaluate → draft_model → schedule → simulate → trh → ikony → build_page).
`build_standalone.py` vyrobí `site/index.html` ze šablony `page_template.html` (šablona = živá verze artifactu v Claude,
data `__DATA__`) a nahradí Claude runtime `cu()` shimem: db → `odds.json` / `ingame.json` / `snapshots.json`,
mcp → přímý fetch Leaguepedie (`origin=*`), sample → `live_feed.js` (esports-api + feed.lolesports.com/livestats). `snapshot.py tips|results` vede track record tipů.
`seed/` = seznam V5 her a minutová data (rozbalí se do `data/tl`, dál je commitují roboti).
