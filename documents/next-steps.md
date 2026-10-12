# Ďalšie kroky

## Hotové
- [x] Návrh architektúry (2026-10-01)
- [x] Rozhodnuté otvorené otázky: poloha zmiešavača, dotlak, okno, prepnutie režimu (2026-10-04)
- [x] Okná ako zapínateľný modul, Window Climate sa zlúči (2026-10-04)

## Hotové – krivka (2026-10-04)
- [x] `image.<okruh>_weather_curve` (SVG kreslené integráciou, otvára sa kliknutím na entitu) a 10 `number.<okruh>_heating_curve_*` / `cooling_curve_*` na okruh. Zmena parametra sa zapíše do subentry a prejaví bez reloadu. Nasadené, overené v dome (F1 strmosť 1.3 → 1.5 → 1.3), 84 testov. Plán: [krivka](../documents/decisions.md).

## Hotové (2026-10-05)
- [x] Senzor stavu okruhu s dôvodom a zónami, záznamy v Aktivite – nasadené, overené
- [x] Fyzikálna krivka kúrenia (návrhový bod + exponent), chladenie lineárne – nasadené, overené (F1: −15 °C → 50 °C, n 1,3)
- [x] Interaktívna karta `custom:climate-circuits-curve-card`, obrázok krivky iba pre aktuálny režim – nasadené
- [x] Dokumentácia v Markdowne: [architecture.md](architecture.md), [README.md](README.md)

## Hotové (2026-10-05, večer)
- [x] Number entity kriviek zrušené, krivku mení karta cez službu `climate_circuits.set_curve`; 25 osirelých `number.*_curve_*` zmazaných z registra
- [x] Karta ako Lovelace resource, pohľad **Climate Circuits** na `/lovelace-configuration/climate-circuits` (dom, F1, GF s kartami kriviek)
- [x] Cirkulácia TUV v integrácii: hysteréza, zariadenie Hot water (stav, prah, delta, prepínač), Aktivita, spínanie len pri `control_equipment`. 113 testov, ruff OK. Nahraté na HA.

## Hotové 2026-10-07 (večer, nasadené)
- [x] Hysteréza cirkulácie podľa skutočného čerpadla (v dry run sa už nerozchádza s čerpadlom)
- [x] Premenované entity: `sensor.hot_water_circulation_state`, `switch.hot_water_circulation_enabled`
- [x] Delta, korekcia a hysteréza v °C (nie K)

## Ostrý štart (2026-10-07)
Kód hotový lokálne (151 testov, ruff OK): čerpadlá okruhov, vlastná poloha zmiešavačov a regulácia, ochrany, potvrdzovanie povelov, tolerancia 60 s. Detaily: [decisions.md](decisions.md).

- [x] Tolerancia 60 s pri nedostupnom senzore po štarte HA
- [x] Čerpadlá okruhov (`binary_sensor.<okruh>_pump`)
- [x] Zmiešavače: poloha z behu relé, regulácia, interlock, strážca, homing, uloženie polohy
- [x] Potvrdzovanie povelov (Relay)
- [x] Ochrany: pauza kúrenie/chladenie, kondenzácia, protáčanie
- [x] Súbory nahrané na HA (2026-10-07, 16 súborov, veľkosti sedia); reštart robí používateľ
- [ ] Po reštarte kontrola v dry run (návrhy v Aktivite, poloha zmiešavača sedí s `cover`)
- [x] Zapínač okruhu `circuit_control` (F1 sa dá spustiť samostatne)
- [ ] GF: `switch.gf_circuit_control` ostáva vypnutý (čerpadlo `relay_8` v okruhu ostáva, ručne ho zapína používateľ); časovač pre okruh bez zón až neskôr
- [ ] Min krivky F1 (17,5 °C) potvrdiť
- [x] 2026-10-08: `control_equipment` zapnutý; vypnuté `water_heating_cycle`, `hvac_mode_switch`, `control_obehovky`
- [x] F1 aj GF ostro (2026-10-08): staré automatizácie vypnuté, prepínače okruhov zapnuté, GF zóna = `climate.gf_thermostat`
- [ ] Vypnúť `OnHomeAssistantStarted` (homing robí integrácia)
- [ ] Sledovať prvé reálne kúrenie F1 a GF v Aktivite
- [ ] Pôvodný zoznam starých na vypnutie: `water_heating_cycle`, `hvac_mode_switch`, `control_obehovky`, `on_obehovky_temperatures_change`, `script.mixerautomation`, `script.homezmiesavace`, `mixers_homing_guard`, `onhomeassistantstarted`
- [ ] Návrat späť: vypnúť `control_equipment`, zapnúť staré automatizácie
- [ ] Ochrana pred mrazom (nerobené, čaká na zadanie)

## Prevádzka po štarte (2026-10-09)
- [x] Cirkulácia TÚV: porovnanie so starou automatizáciou; nastavené prah 36 / delta 0,5 (pásmo 35,5–36 °C), overené ~4,8 štartu/h oproti ~8,6/h
- [x] Výpadky dosky SA8R-011 rozobraté: nereštartuje, nesúvisia so spínaním relé, IP konflikt vylúčený
- [x] `sa8r-011.yaml`: logger INFO, `use_input: false`, `restore_mode: ALWAYS_OFF`, bez interlocku (rozhodnutie). Flashnuté 18:32, všetko nabehlo
- [ ] Skontrolovať loop time dosky (po štarte 66 ms, predtým 25 ms) a počet výpadkov za deň (predtým ~22)
- [x] Debounce krátkeho `unavailable` relé počas pohybu zmiešavača (5 s) + oprava `last_move` pri výpadku v kľude – kód a testy hotové (2026-10-11)
- [x] `const.py`, `outputs.py` nahraté na HA (2026-10-11, veľkosti a riadky sedia)
- [x] Nastavenie „Homovať zmiešavače pri štarte HA“ – kód, preklady, testy (2026-10-11)
- [x] Nahraté (6 súborov, obsah overený) a HA reštartovaný 2026-10-11 16:03: integrácia `ok`, log bez chýb, zmiešavače bez homingu (0 %, `idle`), nové pole v Ochranách viditeľné
- [ ] Zapnúť „Homovať zmiešavače pri štarte HA“, ak ho chceš (prejaví sa pri ďalšom štarte HA)
- [ ] Ak výpadky ostanú: skúsiť iný kábel/port switcha

## Čaká na teba
- [x] Reštart HA (2026-10-05), log čistý
- [ ] Vyskúšať ťahanie kriviek na `/lovelace-configuration/climate-circuits` (prvýkrát Ctrl+Shift+R)

## Prepínanie termostatov pri zmene režimu (2026-10-06)
- [x] Kód a testy hotové lokálne (`core/zones.py`, `ZoneSwitcher`, sekcia „Zone thermostats“), 126 testov, ruff OK
- [x] Refaktor (6. 10.): menej kódu, bez obrázka krivky – 118 testov
- [x] Karta: bod izby ostáva v grafe aj pri vyššej izbovej teplote (os X sa rozširuje) – čaká na nasadenie spolu s ostatným
- [x] Karta: hodnoty pod grafom sa menia kliknutím, chyby služby sa zobrazia na karte – čaká na nasadenie
- [x] Nasadené 2026-10-06: všetky súbory, zmazané `image.py` a `core/curve_svg.py`, reštart, log čistý, z registra odstránené `image.f1_weather_curve` a `image.gf_weather_curve`
- [x] Plány kúrenia doplnené v options domu (5× `switch.schedule_*`)
- [x] Skúška v dry run (6. 10.): override cool → Aktivita „Switching to cooling: turning off 8 (…), then turning on 8 (…) (dry run)“, nič sa fyzicky nepohlo; vrátené na auto
- [ ] Ostrý test až s tvojím súhlasom (zapína `control_equipment`, ten ovláda aj cirkuláciu TUV); potom vypnúť `automation.hvac_mode_switch`

## Hotové 2026-10-07 (nasadené)
- [x] Okruh: `sensor.<okruh>_calling_zones` a `sensor.<okruh>_mixer_position`; pole „Mixer position“ nastavené (F1 → `cover.gf_mixer_up`, GF → `cover.gf_mixer_down`)
- [x] Popisky v karte: Room Temp.:, Min. External Temp.:, Water at Min. Ext. Temp.:
- [x] Teplota cirkulácie TUV ako vlastný senzor na zariadení Hot water
- [x] Reštart HA, log čistý, 122 testov

## Čaká na teba
- [ ] Ikona integrácie (`brand/icon.png`, `icon@2x.png`): cez MCP sa nedá nahrať (binárny súbor). Nahrať ručne cez File editor (Upload) do `/homeassistant/custom_components/climate_circuits/brand/`, reštart HA

## Po reštarte
- [x] Cirkulácia nastavená v options domu (`sensor.gf_heating_cycle_temperature`, `switch.gf_heating_cycle_pump`, 37 / 1); entity zariadenia Hot water existujú, prvý záznam v Aktivite: „On – circulation 35.9 °C is below 36.0 °C (dry run)“
- [ ] Pár dní porovnať `sensor.hot_water_circulation_state` (dry run) s dnešnou automatizáciou `Water Circulation Cycle`
- [ ] Potom: vypnúť `automation.water_heating_cycle` a zapnúť `control_equipment` – pozor, ten zatiaľ ovláda iba cirkuláciu, okruhy ešte nie

## Čaká na rozhodnutie
- [x] Názov: Climate Circuits (2026-10-04)
- [x] Porovnanie s Hydronicus: [hydronicus-porovnanie.md](hydronicus-porovnanie.md) (2026-10-04)
- [x] Mechanizmy z Hydronicus doplnené do architektúry (2026-10-04)
- [x] Vlhkomery: na poschodí v každej miestnosti (2026-10-04)

## Ďalej
- [x] Míľnik 1 – kostra a sledovanie (2026-10-04): config flow domu, subentry okruhu, režim + override, status, control_equipment, požiadavka a cieľ vody okruhu; jadro `core/` (režim, krivky, rosný bod, požiadavka, model a regulácia zmiešavača). 69 testov, ruff OK. Necommitnuté.
- [x] Nasadený míľnik 1 v dome (2026-10-04): súbory cez File editor do `/homeassistant/custom_components/climate_circuits/`, reštart HA, entry `<entry_id>`, okruhy F1 a GF. Prvé hodnoty sa zhodujú s dnešnou logikou (režim heat, F1 požiadavka off, cieľ 35 °C).
- [ ] Oprava `via_device` → `via_device_id` je nahratá na HA, prejaví sa pri najbližšom reštarte HA
- [ ] Pár dní porovnávať `sensor.climate_circuits_mode` / `binary_sensor.f1_demand` / `sensor.f1_target_water_temperature` s `sensor.cfg_hvac_mode` / `binary_sensor.cfg_f1_poziadavka` / `sensor.ekvitermicka_teplota_vody_radiatorov`
- [ ] Nasadzovanie: zatiaľ ručne cez File editor; neskôr GitHub repo + HACS
- [ ] Míľnik 2 – výstupy: čerpadlá, zmiešavač nad relé (vlastná poloha, interlock, max doba), potvrdzovanie povelov, dry run s `proposed`, ozbrojovanie výstupov, homing, number entity kriviek
- [ ] Míľnik 2b – bezpečnosť: pauza heat↔cool, kondenzačný guard, mráz, protáčanie, zdroj tepla
- [ ] Míľnik 3 – modul okien z ha-window-climate
- [ ] Dry run v dnešnom dome, porovnanie navrhovaných povelov s dnešnou logikou, potom ozbrojovanie výstupov po jednom
- [ ] Prepnutie dnešného domu na integráciu a odstránenie starých automatizácií

## Súvisiace, mimo integrácie
- [ ] SA8R-011: overiť po novom firmvéri, či sa pri výpadkoch nuluje `Uptime`, počet výpadkov za deň
- [ ] SA8R-011: osadiť RC členy na servopohony zmiešavačov

## GitHub a HACS (2026-10-11)
- [x] Verejné repo `misevcik/ha-climate-circuits`, história zlúčená do jedného commitu, citlivé údaje z dokumentov odstránené
- [x] Repo pridané do HACS ako Custom repository (typ Integration), inštalácia cez HACS – 2026-10-12
- [x] Release `v0.1.0` vydaný 2026-10-11 (tag pushnutý, release vytvorený na webe)
- [x] `README.md` prepísaný do angličtiny podľa aktuálneho stavu (funkcie, inštalácia cez HACS, nastavenie, entity, karta, zmiešavač, vývoj) – 2026-10-11
- [ ] Popis a topics repa na GitHube (napr. `home-assistant`, `hacs`, `heating`)

## Regulácia zmiešavačov (2026-10-12)
- [x] Zistené kmitanie GF aj F1 (~75–95 zopnutí/h, ±2,5 K), príčina: krok každých 30 s pri oneskorení 1,5–2,5 min
- [x] Nová regulácia (čas ustálenia, trend, krok úmerný odchýlke, zriedkavý dotlak) + simulácia + testy
- [x] Oprava: čerpadlo znova naskočilo po dobehu; `binary_sensor.<okruh>_pump` `unknown` pri výpadku dosky
- [x] Nahraté na HA (ručne) a reštart 2026-10-12 12:49; push + tag `v0.1.1`
- [x] Ochranná doba 90 s po štarte (čerpadlo vypnuté pri reštarte HA)
- [ ] Release `v0.1.1` na GitHube (odkaz od Clauda) a odteraz update cez HACS
- [x] Ochranná doba po štarte: push + tag `v0.1.2`
- [x] Release `v0.1.2` vydaný; repo pridané do HACS ako custom repository a v0.1.2 nainštalovaná cez HACS (vrátane `brand/` ikon) – 2026-10-12
- [x] Reštart HA 12:57 s v0.1.2 z HACS: GF čerpadlo ostalo bežať (požiadavka chýbala 12:57:31–12:57:59, ochranná doba ju preklenula), log čistý, HACS eviduje v0.1.2
- [ ] Overiť ikonu integrácie v Nastaveniach a správanie zmiešavačov cez noc
- [ ] Opraviť popis repa na GitHube (`Control of heating unde home assistant`), HACS ho zobrazuje
- [ ] Overiť jednu noc: počet zopnutí za hodinu, rozkmit prívodu GF, prípadne doladiť *Mixer settle time*
- [ ] Samoučenie oneskorenia a citlivosti okruhu (nápad používateľa)

## Regulácia podľa zdroja (2026-10-12)
- [x] Analýza večera: vlnenie spôsobuje cyklovanie akumulačky 41–48 °C; okruhy sú radiátory
- [x] `source_sensor` + kompenzácia zmeny zdroja, simulácia, 173 testov
- [x] `v0.1.3` vydaná, nainštalovaná cez HACS, reštart 21:00 (GF čerpadlo ostalo bežať)
- [x] F1 aj GF: *Source temperature* = `sensor.gf_watertank_up_temperature` (21:02), integrácia `ok`, atribút `source_temperature` 44,0 °C
- [ ] Overiť noc: % času v ±0,5 K, zopnutia za hodinu

## Zdroj tepla ako časť integrácie (2026-10-12)
- [x] Návrh v architektúre a denníku
- [x] Subentry `source` (názov, senzor teploty), zariadenie + `sensor.<zdroj>_temperature`, výber zdroja v okruhu (jediný zdroj sa použije automaticky), `source_sensor` okruhu len ako dočasná náhrada; 178 testov
- [x] `v0.1.4` vydaná, nainštalovaná cez HACS, reštart
- [x] V dome: zdroj „Akumulačná nádrž“ = `sensor.gf_watertank_up_temperature` (`sensor.akumulacna_nadrz_temperature`), `source_sensor` z F1 aj GF odstránený; oba okruhy berú zdroj automaticky (41,3 °C)
- [ ] Neskôr: zobraziť prehľadové senzory ako entity; požiadavka na zdroj; záložný senzor režimu presunúť k zdroju
