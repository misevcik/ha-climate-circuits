# Denník rozhodnutí – integrácia riadenia vykurovania a chladenia

Architektúra: [architecture.md](architecture.md) (pôvodný Claude Docs dokument z 1. 10. je zastaraný)
Názov: **Climate Circuits**, doména `climate_circuits`, repozitár `ha-climate-circuits`.

## 2026-10-09 – upratanie nepoužívaných helperov v HA
- Pred zmazaním záloha HA `00cd5380` („Before_helpers_cleanup_2026-10-09“).
- Kontrola: automatizácie, skripty, scény, ostatné helpery, všetkých 5 dashboardov, options a subentries Climate Circuits, Energy, HomeKit, Scheduler, lokálne projekty v `~/work`; aj vyhľadávanie podľa častí názvov (dynamicky skladané entity_id). Neoverené: YAML template senzory v `configuration.yaml` (cez MCP sa nedajú čítať).
- **Zmazaných 36 helperov** (125 → 89). Pre tento projekt dôležité: staré helpery kúrenia `binary_sensor.cfg_f1_poziadavka`, `sensor.cfg_hvac_mode`, `input_number.cfg_circular_temperature_threshold` / `cfg_circular_pump_delta` (cirkuláciu riadi integrácia, 36 / 0,5), ekvitermika `minimal_external_temperature`, `max_water_temperature`, `returned_water_temperature`, `parallel_shift`, `expected_room_temperature_cooling`, `thermal_exponent_cooling`, `cfg_zone_heating_sleep_time`, `cycle_start/stop_time`, `switch.gf_sw_bedroom_heat`. Ďalej nepoužívané rolety, zavlažovanie, bazén a skupiny (`terrace_motion`, `f1_presence_sensors`, `ac_monitored_windows`, `f1_kitchen_illumination_all`, `proximity_home`, `home_consumption` atď.).
- Z dashboardu Configuration odstránené karty zmazaných helperov (Rolets, Heating – dlaždice starej cirkulácie, Pool) a badge hibernácie v pohľade Pool hlavného dashboardu.
- Ponechané: zónové termostaty `*_cool`, `climate.gf_thermostat` a jeho pomocné entity (používa ich integrácia), `binary_sensor.f1_occupancy` (nejednoznačné vyhľadávanie).
- **Čaká:** `switch.gf_sw_bedroom_cool` a `light.cfg_wintergarden_stairs` sa nezmazali (zablokované povolením v Claude Code) – zmazať ručne v Settings → Helpers, alebo povoliť nástroj.

## 2026-10-11 – voliteľný homing zmiešavačov pri štarte HA
- Otázka používateľa: „pri reštarte by sa mali vždy zahomovať?“ Doteraz sa pri štarte homovalo len pri neznámej polohe (uložená poloha sa prevezme). Homing trvá jeden zdvih (~125 s) a zatvorí prívod, preto nie vždy.
- Nové nastavenie domu `protection.home_mixers_on_start` (**Homovať zmiešavače pri štarte HA**), predvolene vypnuté. Zapnuté: pri štarte Home Assistanta sa uložená poloha zahodí a zmiešavač sa ~30 s po štarte zahomuje (len okruh, ktorý integrácia ostro ovláda). Pri reloade integrácie (zmena nastavení) nie – rozlišuje sa podľa `hass.is_running` pri vytvorení `House`.
- Zvažovaná alternatíva: homovať len po dlhšom výpadku HA (napr. > 30 min) – zatiaľ nerobené.
- Testy: 161 (3 nové). Nasadenie čaká.

## 2026-10-11 – zmiešavač prežije krátky výpadok relé
- Relé, ktoré je počas pohybu zmiešavača `unavailable`, sa toleruje `MIXER_RELAY_GRACE` = 5 s (doska SA8R-011 vypadáva ~20× denne na ~0,3 s). Vráti sa `on` → pohyb sa počíta ďalej od pôvodného štartu; vráti sa `off` → pohyb končí v čase návratu (chyba ≤ dĺžka výpadku). Poloha sa zahodí (→ homing) až keď je relé preč dlhšie ako 5 s.
- Oprava popri tom: návrat relé `off` po výpadku v kľude už neprepíše `last_move`. Predtým každý výpadok vyzeral ako pohyb, takže protáčanie zmiešavača po 7 dňoch nečinnosti by sa pri ~20 výpadkoch denne nikdy nespustilo.
- Relé, ktoré stálo a po výpadku sa vráti `on`, sa berie ako skutočný štart (niekto ho zapol počas výpadku).
- Testy: 158 (3 nové: výpadok v kľude nie je pohyb, krátky výpadok počas pohybu, návrat `off` po výpadku; test straty relé čaká 5 s). Nasadenie na HA čaká.

## 2026-10-09 – výpadky reléovej dosky SA8R-011 (`unavailable`)
- Doska (ESPHome, `sa8r-011.yaml`, ESP32 + ethernet JL1101, pevná IP s DHCP rezerváciou) je ~20–25× denne na zlomok sekundy `unavailable` (celé zariadenie naraz, ~0,3 s).
- **Doska nereštartuje:** uptime rastie bez prerušenia (~8 dní), `api: reboot_timeout: 0s`. Heap ~319 KB, loop time 25 ms – v poriadku. Ide o krátky výpadok ethernet/API spojenia, nie o pád.
- **Nesúvisí so spínaním relé (podozrenie na zlý HW návrh vyvrátené):** za 40 h 42 výpadkov oproti 479 zopnutiam cirkulačného relé; **0 výpadkov do 5 s od zopnutia**, medián vzdialenosti 112 s, nikdy sa počas výpadku nezmenil stav relé. Kontrolované proti najčastejšie spínanému relé (cirkulácia); zmiešavače v tom čase skoro stáli.
- IP konflikt vylúčený (DHCP rezervácia na routeri).
- **Zmena:** `logger: level` DEBUG → INFO (menej prevádzky cez API). Súbor upravený cez File editor; **flash (OTA) spustí používateľ** v ESPHome.
- **Kontrola konfigurácie vs. oficiálna** ([ESPHome Devices: Dingtian DT-R008](https://devices.esphome.io/devices/dingtian-dt-r008/)): v jadre ESPHome natívna podpora nie je, oficiálna stránka používa externý `dtr0xx_io` (kecajtop), doska beží na jeho forku `lucize` (pripnutý commit „convert to polling“). Ethernet (JL1101, piny 23/18, clk GPIO17 out, power 0, phy 1), piny posuvných registrov, UART 1/3 s `logger baud_rate: 0` a RS485 TX enable GPIO33 – v poriadku.
- Mapovanie relé: R1 cirkulácia TÚV, R2 F1 zatvor, R3 F1 otvor, R4 GF otvor, R5 GF zatvor, R6 voľné, R7 F1 čerpadlo, R8 GF čerpadlo.
- **Rozhodnutie používateľa: firmvér bez `interlock`** – doska ostáva bez riadiacej logiky, blokovanie smerov zmiešavača rieši iba integrácia (jedno miesto, viditeľné v Aktivite, platí aj pre iné domy). Ak bude treba poistku nezávislú od softvéru, spraví sa v zapojení (smer cez NC kontakt opačného relé), nie vo FW. Pozn.: interlock 7↔8 z oficiálnej šablóny by tu blokoval dve čerpadlá.
- **Upravené v `sa8r-011.yaml`** (File editor, overené na serveri): `logger` INFO, `use_input: false` na hube `dtr0xx_io` (podľa kódu pripnutej verzie: `update()` sa vtedy hneď vráti, relé sa zapisujú len pri príkaze, RCK latch ostáva), `restore_mode: ALWAYS_OFF` na všetkých 8 relé. Nič z toho nevysvetľuje výpadky API.
- **Flashnuté 2026-10-09 18:32** (OTA, používateľ). Doska nabehla, všetky relé `off`, teploty z modbusu sa vrátili, integrácia bez straty polohy (zmiešavače stáli, 0 %, `idle`), cirkulácia správne `stopped` pri 36,0 °C. Loop time po štarte 66 ms (predtým stabilne 25 ms) – overiť, či sa ustáli; zajtra porovnať počet výpadkov `unavailable` s ~22/deň pred zmenou. Varovania kompilátora (`minimum_chip_revision`, `sram1_as_iram`) sú len optimalizácie, netreba.
- Otvorené: zostávajúce podozrenie je ethernet PHY/kábel/port switcha. Na strane integrácie navrhnutý debounce – krátky `unavailable` (< 5 s) počas pohybu zmiešavača ignorovať, aby blip nespustil zbytočný homing (čaká na súhlas).

## 2026-10-08 – regulácia cirkulačnej teploty TÚV: nová vs. stará

Porovnanie na žiadosť používateľa.

**Predtým** – `automation.water_heating_cycle`, spúšťač každých 10 s, jediná podmienka: `teplota < (threshold − delta)` → zapni, inak vypni. Pri 37 / 1 to bol **jediný bod prepínania na 36 °C bez pásma** (threshold 37 sa ako bod vypnutia reálne nepoužil).

**Teraz** – [core/circulation.py](custom_components/climate_circuits/core/circulation.py), skutočná hysteréza: zapni pod `threshold − delta` (36), vypni pri `threshold` (37), v pásme 36–37 drž predošlý stav. Udalosťami riadené, pozná suchý beh / vypínač cirkulácie, 60 s odklad po štarte, stav v Aktivite (`cold`/`warming`/`reached`/`waiting`). Relé je pamäť hysterézy (suchý beh zrkadlí cudzí pohon).

**Postreh používateľa (z grafu): predtým to bolo presnejšie.** Potvrdené dátami z histórie:
- Stará regulácia (6.–8. 10.): teplota držaná tesne okolo 36 °C (priemer 35,6 °C, min/max 33,3/37,3), ale **~8,6 štartov čerpadla za hodinu** (460 štartov za 53,8 h) – krátke cyklovanie okolo jedného bodu.
- Nová regulácia: pásmo 1 K (36–37) → **výrazne menej štartov** (od zapnutia integrácie čerpadlo nemuselo naštartovať), ale teplota kolíše v celom pásme → **menšia presnosť držania teploty**.

Je to klasický kompromis hysterézy: užšie pásmo = presnejšia teplota, ale viac štartov a opotrebenia; širšie pásmo = menej štartov, väčší rozkmit. Stará automatizácia mala pásmo prakticky nulové (presné, ale cvakalo).

**Zvolené nastavenie (používateľ, 2026-10-08 večer):** `threshold = 36`, `delta = 0,5` → pásmo **35,5–36 °C**. Bod vypnutia 36 °C je rovnaký ako mala stará automatizácia, ale s malým pásmom 0,5 K proti cvakaniu. Aplikovalo sa za behu bez reštartu (tuning).

**Overené 2026-10-09:** pásmo funguje, teplota sa drží okolo 36 °C. Počet štartov čerpadla klesol z pôvodných ~8,6/h na **~4,8/h** (~85 štartov za 18 h), teda zníženie o ~45 % pri podobnej presnosti. Stále cykluje ~každých 5 min (úzke pásmo 0,5 K, slučka chladne rýchlo). Ďalšie zníženie štartov = širšie pásmo (delta 0,8–1,0) za cenu väčšieho rozkmitu — ponechané na používateľovi. Zatiaľ ostáva 0,5.

**Riešenie/ladenie:** presnosť sa dá vrátiť znížením `delta` v nastaveniach domu (sekcia TÚV). Napr. `delta = 0,3` dá pásmo 36,7–37,0 → tesnejšie držanie okolo 37 °C za cenu častejších štartov; `delta → 0` je de facto správanie starej automatizácie. Bod vypnutia je teraz `threshold` (37), nie `threshold − delta` (36) ako predtým, takže slučka sa drží o ~1 °C teplejšia. **Otvorené: nechať používateľa doladiť `delta` podľa toho, čo preferuje (presnosť vs. opotrebenie čerpadla).**

## 2026-10-08 – stav zmiešavača
- Na stránke zariadenia (F1, GF) nie sú vidieť atribúty, preto je stav zmiešavača aj samostatná entita: `sensor.<okruh>_mixer_state` (enum `idle`, `opening`, `closing`, `homing`, `unknown`) popri `sensor.<okruh>_mixer_position` (%). Atribút `movement` na polohe ostáva. Spolu 2 entity na okruh. Homing sa hlási aj v Aktivite.
- Dashboard: karta „Mixer“ ukazuje polohu a `movement`; k nej pribudne aj karta stavu.

## 2026-10-08 – plány kúrenia už integrácia neriadi
- Pole „Plány kúrenia“ (`schedule_switches`) a ich zapínanie/vypínanie pri zmene režimu sú **zrušené**. Používateľ: plány môže riadiť iná integrácia, preto ich integrácia nemá ovládať; kto chce, spraví si automatizáciu.
- Dôsledok: po vypnutí `HVAC Mode Switch` nikto neprepína `switch.schedule_*` s režimom. Pri chladení by plán mohol poslať kúrenárskym termostatom `heat`; integrácia ho po zapnutí znova vypne (záznam „stray“ v Aktivite), ale je lepšie plány pri chladení vypínať vlastnou automatizáciou.
- Uložené `schedule_switches` v options sa ignorujú.

## 2026-10-08 – ostrý beh F1 aj GF
- Používateľ vypol `On Obehovky Temperatures Change`, `Control Obehovky`, `HVAC Mode Switch`, `Water Circulation Cycle` a `Mixers Homing Guard`. Zapnuté `switch.f1_control_pump_and_mixer` aj `switch.gf_control_pump_and_mixer`; integrácia riadi čerpadlá, zmiešavače, cirkuláciu TUV aj prepínanie termostatov.
- Prvé ostré príkazy overené v logbooku (GF zmiešavač zatváraný pri nulovej požiadavke).
- Otvorené: `OnHomeAssistantStarted` ostáva zapnutá (homing pri štarte HA) – odporúčané vypnúť; F1 minimum krivky 23 °C; ochrana pred mrazom; časovač pre okruh bez zón.

## 2026-10-08 – GF termostat ako zóna prízemia
- GF nemá zóny, takže integrácia považovala požiadavku za stálu a chcela riadiť aj ručné čerpadlo. Riešenie: virtuálna zóna `climate.gf_thermostat` (generic thermostat, režim kúrenie/vypnuté), ovláda ju používateľ ručne.
- Pomocné entity (vytvorené cez MCP): `input_number.gf_room_temperature` (stále 15 °C, „prízemie je chladné“), `sensor.gf_room_temperature_sensor` (template z neho), `input_boolean.gf_thermostat_heater` + `switch.gf_thermostat_heater_switch` (prázdny spínač, nič skutočné nespína).
- `climate.gf_thermostat` pridaný do okruhu GF ako kúrenárska zóna; cieľ 21 °C, režim zatiaľ `off`. Kúriť dole = prepnúť termostat na `heat`.
- `switch.gf_control_pump_and_mixer` zapnutý. GF čerpadlo (`relay_8`) odteraz riadi integrácia podľa termostata.
- Čaká sa na vypnutie `On Obehovky Temperatures Change` (používateľ), kým zmiešavače GF aj F1 riadi ešte aj starý skript.

## 2026-10-08 – prechod na ostrý beh (čiastočný)
- Zapnutý `switch.climate_circuits_control_equipment` (17:3x). Ostro: cirkulácia TUV a prepínanie termostatov pri zmene režimu.
- Vypnuté staré automatizácie: `water_heating_cycle`, `hvac_mode_switch`, `control_obehovky`.
- **Nedokončené:** `automation.on_obehovky_temperatures_change` volá `script.mixerautomation` pre GF aj F1 zmiešavač. Úprava (vyhodiť druhú akciu – F1) bola zamietnutá oprávnením, takže zostala. Kým sa to nezmení, `switch.f1_control_pump_and_mixer` ostáva vypnutý (inak by F1 zmiešavač riadili dva regulátory) a **F1 čerpadlo nikto neriadi** (`control_obehovky` je vypnutá).
- Návrat späť: vypnúť `control_equipment`, zapnúť `water_heating_cycle`, `hvac_mode_switch`, `control_obehovky`.
- GF zostáva na starej regulácii zmiešavača; `switch.gf_control_pump_and_mixer` vypnutý (čerpadlo GF zapína používateľ ručne).

## 2026-10-07 – čerpadlá, zmiešavače a ochrany (príprava na ostrý štart)
- Začína sa vykurovacia sezóna, preto sa míľnik 2 robí hneď. Výstupy ostávajú za `control_equipment`; bez neho sa všetko iba ukazuje (dry run) v Aktivite.
- **Dva zapínače, nie tri:** globálny `control_equipment` ovláda všetko (cirkulácia TUV, prepínanie termostatov, čerpadlá, zmiešavače). `hot_water_circulation_enabled` iba povoľuje/zakazuje cirkuláciu, nie je to „ostrý/skúšobný“ prepínač.
- **Čerpadlo okruhu** (`core/pump.py`, `outputs.py`): štart po 180 s požiadavky (ventily zón sa otvoria), dobeh 180 s iba pri kúrení, pri chladení vypnúť hneď. Entita `binary_sensor.<okruh>_pump` (stav = skutočné relé, atribúty: dôvod, čo chce integrácia, či je ovládané).
- **Zmiešavač** (`core/travel.py`, `MixerController`): poloha sa počíta z behu relé (preberané z `cover_time_based`/xknx, MIT), sleduje relé aj keď ho ovláda iný (dry run ukáže, čo by urobila regulácia). Regulácia po 30 s, krok 5–10 %, hysteréza, dotlak 2 s, homing pri neznámej polohe 30 s po štarte.
- **Bezpečnosť zmiešavača:** nikdy obe relé naraz, strážca max. doby behu (dráha + 2 s + 15 s), relé zapnuté bez príkazu sa vypne, pri vypnutí integrácie/HA sa relé vypnú, poloha sa ukladá.
- **Potvrdzovanie povelov:** po príkaze sa overí, že entita naozaj zmenila stav; opakuje sa po 10 s, po 3 pokusoch jedno hlásenie v Aktivite, po 5 min nový pokus.
- **Ochrany:** pauza kúrenie ↔ chladenie (60 min, nie pri návrate do predošlého režimu; prežije reštart), kondenzácia (stop pod rosný bod + 2 K, uvoľnenie od +3 K a po 5 min; bez vlhkosti sa chladenie neblokuje inak než hlásením „bez rosného bodu“ = chladenie sa nespustí), protáčanie čerpadla (60 s) a zmiešavača (homing) po 7 dňoch nečinnosti.
- **Nie je urobené:** ochrana pred mrazom (potrebuje rozhodnutie, čo presne ovládať).
- Tolerancia 60 s pri nedostupnom senzore cirkulácie po štarte HA – hotovo.
- **Zapínač na okruh** (`switch.<okruh>_circuit_control`, predvolene vypnutý, uložený): čerpadlo a zmiešavač okruhu sa ovládajú iba pri zapnutom `control_equipment` **aj** zapnutom zapínači okruhu, takže sa dá spustiť napr. len F1. Cirkuláciu TUV povoľuje `hot_water_circulation_enabled`.
- **GF čerpadlo** (`relay_8`) ostáva v podokruhu GF (rozhodnutie používateľa). Integrácia ho neovláda, kým je vypnutý `switch.gf_circuit_control`; čerpadlo zapína ručne. Časovač pre okruh bez zón – neskôr.
- Pred ostrým zapnutím: GF čerpadlo (`relay_8`) nemá dnes majiteľa a je vypnuté – z podokruhu GF ho odstrániť; min krivky F1 17,5 °C (cieľ 28,2 °C vs. 35,0 °C v starej šablóne) potvrdiť.
- Rozhodnutia o pauze a protáčaní sú nastaviteľné v options domu (sekcia Ochrany), časy čerpadla vo výstupoch okruhu.

## 2026-10-06 – ikona integrácie
- Od HA 2026.x môže vlastná integrácia dodať ikonu v priečinku `brand/` (`icon.png` 256 px, `icon@2x.png` 512 px; logo a tmavé varianty sa doplnia z ikony). Netreba PR do `home-assistant/brands`.
- Ikona: kruh napoly oranžový (kúrenie) a modrý (chladenie), biela ekvitermická krivka s bodom „teraz“ – rovnaké farby ako karta.
- Nasadenie: File editor cez `/api/save` ukladá len text, PNG sa cez MCP nedá nahrať. Nahrá sa ručne cez File editor (Upload) do `custom_components/climate_circuits/brand/`, neskôr príde s HACS automaticky. HA ju načíta po reštarte.

## 2026-10-06 – viditeľnosť okruhu a názvy v karte
- Okruh ukazuje **volajúce zóny** ako vlastnú entitu (stav = mená termostatov), nielen v atribútoch.
- **Poloha zmiešavača** sa zobrazuje v % ako entita okruhu. Kým integrácia nepočíta polohu sama (míľnik 2), číta ju z existujúcej `cover_time_based` entity (nové voliteľné pole „Mixer position“ vo výstupoch okruhu).
- Popisky v karte podľa želania: Room → Room Temp.:, Design outdoor → Min. External Temp.:, Design water → Water at Min. Ext. Temp.: (sk: Izbová tepl.:, Min. vonkajšia tepl.:, Voda pri min. vonk. tepl.:).
- Nasadenie počká, kým používateľ pridá ďalšie zmeny.

## 2026-10-06 – refaktor: menej kódu
- Na želanie: čo najmenej riadkov, bez zbytočných komentárov, bez obrázka krivky.
- **Zrušené:** `image.<okruh>_weather_curve`, `core/curve_svg.py`, body krivky (`curve_points`, atribút `curve`). Krivku kreslí karta sama z parametrov.
- Kľúče options a subentries sú v `settings.py` a `config_flow.py` ako reťazce namiesto ~50 konštánt `CONF_*`/`SECTION_*`; uložené dáta sa nemenia.
- Jedna základná trieda entít, jeden slovník textov na jazyk, spoločné pomocné funkcie v `house.py`.
- `core/mixer.py` ostáva (logika zmiešavača pre míľnik 2), iba zhustená.
- Validácia formulára pri viacerých chybách ukáže prvú, nie poslednú.
- Výsledok: 3 743 → 2 658 riadkov kódu (Python + karta), 118 testov, ruff OK. Prvý commit `2360205` obsahuje stav po refaktore.
- Pri nasadení zmazať na HA `image.py` a `core/curve_svg.py` a z registra entity `image.f1_weather_curve`, `image.gf_weather_curve`.

## 2026-10-07 – názvy entít cirkulácie TUV
- Názvy `sensor.hot_water_circulation` a `switch.hot_water_circulation` sa pliesli so skutočným čerpadlom (`switch.gf_heating_cycle_pump`).
- Premenované: `sensor.hot_water_circulation_state` („Circulation state“, rozhodnutie integrácie) a `switch.hot_water_circulation_enabled` („Circulation enabled“, povolenie, nie čerpadlo).
- Hysteréza cirkulácie berie pamäť zo skutočného stavu čerpadla, nie z vlastného posledného rozhodnutia (v dry run sa inak rozchádzala s čerpadlom, ktoré riadi stará automatizácia).
- Kľúče entít ostali (`circulation`, `circulation_enabled`), aby sa nevytvárali nové entity; ID entít v HA sa premenovali v registri.
- Otvorené: tolerancia 60 s pri nedostupnom senzore po štarte HA (zatiaľ sa pri štarte zapíše krátke „unavailable“).

## 2026-10-06 – prepínanie termostatov pri zmene režimu
- Požiadavka: pri zmene kúrenie ↔ chladenie sa termostaty opačného režimu musia **spoľahlivo vypnúť**. Preberá to integrácia od automatizácie `HVAC Mode Switch`.
- Dôvod prísnosti: kúrenárske aj chladiace termostaty zóny spínajú to isté zónové relé, aktívna smie byť iba jedna sada.
- Postup pri zmene režimu:
  1. Vypnú sa termostaty opačného režimu (pri `off` všetky).
  2. Termostaty nového režimu sa zapnú až keď **všetky** opačné hlásia `off`.
  3. Pri prechode do kúrenia sa zapnú plány (Climate Scheduler); mimo kúrenia sa držia vypnuté.
- **Stráženie:** termostat opačného režimu, ktorý sa neskôr zapne (plán, človek), sa vypne a zapíše do Aktivity.
- Povel sa opakuje každých 30 s, po 3 neúspešných pokusoch sa chyba zapíše do Aktivity a nová sada sa nezapne.
- Termostat v oboch zoznamoch (jedna `climate` na heat aj cool) sa nevypína, iba prepne režim.
- Bez zdroja režimu (`default`) sa termostaty neprepínajú. Zmena počas výpadku HA sa dobehne po štarte (porovnáva sa s uloženým posledným režimom).
- Iba pri zapnutom `control_equipment`, inak dry run so záznamom v Aktivite. Nastavenie: sekcia domu „Zone thermostats“ (zapnuté predvolene, zoznam plánov).
- Kód: `core/zones.py`, `ZoneSwitcher` v `house.py`; 126 testov.

## 2026-10-05 – cirkulácia TUV v integrácii (zmena rozsahu)
- Pôvodne „TUV nerieši“. Teraz integrácia preberá **cirkulačné čerpadlo TUV** (dnes automatizácia `automation.water_heating_cycle` „Water Circulation Cycle“, každých 10 s).
- Dnešná logika: zapni, ak cirkulácia < prah − delta, inak vypni (`input_number.cfg_circular_temperature_threshold` = 37, `cfg_circular_pump_delta` = 1, `switch.gf_heating_cycle_pump`, `sensor.gf_heating_cycle_temperature`). Okolo 36 °C čerpadlo cvaká.
- **Nové: hysterézia.** Zapne pod prah − delta, vypne pri dosiahnutí prahu, medzi tým drží stav (37/1: zap < 36 °C, vyp ≥ 37 °C).
- **Nastavenie:** samostatné zariadenie „Hot water“ s entitami prah a delta (number), prepínač cirkulácie a senzor stavu s dôvodom. Prepínanie a dôvody idú do Aktivity.
- Modul je voliteľný (dom bez cirkulácie ho nezapne). Čerpadlo sa reálne spína iba pri zapnutom `control_equipment`, inak dry run, takže dnešná automatizácia môže bežať súbežne až do prepnutia.
- Prah a delta: zdroj pravdy sú options domu; zmena sa aplikuje bez reloadu (rovnako ako krivky).

## 2026-10-05 – krivka iba cez kartu, karta ako Lovelace resource
- Number entity parametrov krivky sú **zrušené** (na želanie: krivka sa nastavuje kartou). Karta volá entitnú službu `climate_circuits.set_curve` na `sensor.<okruh>_target_water_temperature` (`mode` heat/cool + zmenené parametre). Služba kontroluje min ≤ max a návrh vonku < izba, zapisuje do subentry, mení bez reloadu a každú zmenu zapíše do Aktivity.
- 25 osirelých `number.*_curve_*` zmazaných z registra.
- Karta sa registruje ako **Lovelace resource** (`/climate_circuits_frontend/climate-circuits-curve-card.js?v=<mtime>`), nie cez `add_extra_js_url`. Ten sa načíta pred výmenou registra custom elementov a karta sa potom nenašla.
- Na dashboard `lovelace-configuration` pribudol pohľad **Climate Circuits** (`/lovelace-configuration/climate-circuits`): dom (režim, stav, override, ovládanie zariadení) a F1/GF (stav, cieľ vody, karta krivky).

## 2026-10-05 – dokumentácia v Markdowne
- Všetky rozhodnutia, architektúra a podklady sa píšu do `.md` súborov v `documents/`, aby sa z nich dali generovať dokumenty (pandoc, MkDocs). Diagramy v Mermaid.
- Architektúra je v [architecture.md](architecture.md) podľa aktuálneho kódu, s označením Hotové / Plánované. Pôvodný dokument v Claude Docs (1. 10.) je zastaraný a ďalej sa neudržiava.
- Rozcestník: [README.md](README.md).

## 2026-10-05 – fyzikálna ekvitermická krivka kúrenia
- Lineárna krivka (dnešná šablóna používa `thermal_exponent = 1,3` ako lineárnu strmosť) nezodpovedá skutočnosti: s 1,3 K/K dosiahne max 50 °C už pri 0 °C vonku.
- **Kúrenie:** T_voda = izba + (T_návrh − izba) · φ^(1/n) + korekcia, kde φ = (izba − vonku) / (izba − vonku_návrh), orezané na [min, max].
  - Parametre: izba, návrhová vonkajšia teplota, návrhová teplota vody, exponent n (1,3 radiátory, 1,1 podlahovka), korekcia, min, max.
  - Krivka prechádza bodom (izba, izba) a návrhovým bodom; pri miernom mraze stúpa rýchlejšie, pri silnom sa ohýba (ako katalógové krivky).
- **Chladenie** ostáva lineárne (izba, strmosť, korekcia, min, max).
- F1: návrh −15 °C → 50 °C, radiátory, n = 1,3. GF rovnako, kým sa neupresní.
- Karta: pri kúrení sa ťahá návrhový bod (mení návrhovú teplotu vody) a bod izby (posúva celú krivku ako krivky 15/20/25 °C); pri chladení bod strmosti a korekcia. Čiary min/max v oboch.

## 2026-10-05 – Aktivita a interaktívna krivka
- **Všetko podstatné má byť vidieť v paneli Aktivita.** Integrácia zapisuje vlastné záznamy naviazané na svoje entity:
  - zmena režimu domu aj s tým, čo rozhodlo,
  - zmena stavu okruhu alebo zón, ktoré žiadajú teplo (s dôvodom),
  - zmena parametra krivky,
  - počiatočný stav po štarte.
  Cieľová teplota vody sa nezapisuje, mení sa príliš často.
- Nový senzor `sensor.<okruh>_state` (kúri / chladí / nečinný / vypnutý) s dôvodom a riadkom pre každú zónu.
- Oprava: pri štarte sa na chvíľu zapísal režim „Off“, lebo entity vznikli pred prvým vyhodnotením. Teraz sa vyhodnotí pred vytvorením entít.
- **Krivka:** kúrenie a chladenie v jednom grafe bolo mätúce, ostávajú oddelené. Integrácia prinesie **vlastnú kartu** `custom:climate-circuits-curve-card`:
  - prepínač Kúrenie / Chladenie, predvolene aktuálny režim,
  - ťahanie čiar max/min, bodu strmosti a otočného bodu (korekcia),
  - po pustení sa zapíšu number entity.
  Karta sa načíta automaticky (`add_extra_js_url`), z HACS sa nič neinštaluje.
- Obrázok `image.<okruh>_weather_curve` kreslí iba krivku aktuálneho režimu.

## 2026-10-04 – ekvitermická krivka ako obrázok a number entity
- Vstavané grafy HA majú na osi X čas, krivku (os X = vonkajšia teplota) nevedia. Plugin (ApexCharts) nechceme. Integrácia preto krivku kreslí sama ako SVG v `image` entite okruhu; zobrazí sa kliknutím na entitu, dashboard karta netreba.
- Kúrenie a chladenie majú **samostatné krivky** s vlastnými parametrami; v jednom obrázku sú len preto, že sa ich rozsahy (−20…20 °C a 20…40 °C) neprekrývajú. Aktívna je plnou farbou, druhá vyblednutá. Ak by to prekážalo, dá sa rozdeliť na dva obrázky.
- Parametre krivky sú `number` entity (5 pre kúrenie, 5 pre chladenie). Zdroj pravdy ostáva subentry okruhu; zmena čisto v krivkách sa aplikuje bez reloadu, iné zmeny reloadujú ako doteraz.
- Obrázok sa obnoví iba pri zmene parametrov, režimu, cieľa vody, vonkajšej teploty o 0,5 °C alebo rosného bodu.
- Dnešné `input_number.expected_room_temperature` / `thermal_exponent` / `thermal_correction` ostávajú iba pre starý template senzor.

## 2026-10-04 – prehľad režimu a krivky
- Senzor režimu ukazuje v atribútoch, čo rozhodlo: zdroj, stav a činnosť climate tepelného čerpadla, záložnú teplotu s prahmi, vonkajšiu teplotu a voliteľné „zobrazované senzory“ (nová sekcia domu `display.info_sensors`). U teba: TUV, cieľ TUV, zásobník TUV, výstup/spiatočka tepelného čerpadla, akumulačka výstup, priemer vonku 2 dni.
- Senzor cieľovej teploty vody okruhu má v atribútoch body krivky (`curve`: −20…20 °C pri kúrení, 20…40 °C pri chladení) a jej parametre, na graf v dashboarde.
- Graf krivky potrebuje kartu, ktorá kreslí X/Y (napr. ApexCharts z HACS); vstavané karty HA kreslia iba priebeh v čase.

## 2026-10-04 – nasadenie míľnika 1 v dome
- Nahraté cez app File editor (`/api/save`), bez GitHubu a HACS, kým nie je commit.
- Dom: zdroj `climate.heat_pump_central_heating`, záloha nádrž `sensor.gf_watertank_up_temperature` 28 / 22 °C, vonku `sensor.outside_temperature`, schopnosti heat + cool.
- F1: 8 kúrenárskych a 8 chladiacich termostatov (zoznamy z `cfg_f1_poziadavka`), 8 vlhkomerov z izieb, krivka kúrenia 22 / 1.3 / 35–50 °C, chladenia 24 / 0.5 / 18–22 °C (ako dnešná ekvitermika), výstupy relay_7, `switch.gf_mixer_up_open/close`, `sensor.gf_mixer_up_temperature`.
- GF: bez zón, relay_8, `switch.gf_mixer_down_open/close`, `sensor.gf_mixer_down_temperature`.
- Rozdiel oproti dnešku: krivka sa zatiaľ nastavuje v okruhu, nie z `input_number.expected_room_temperature` / `thermal_exponent` / `thermal_correction`. Zmena týchto helperov sa do integrácie neprenesie, kým nebudú number entity (míľnik 2).
- Pozor: worst-case rosný bod berie najvyššiu vlhkosť zo všetkých izieb vrátane kúpeľní, sprcha ho pri chladení dočasne zdvihne (konzervatívne).
- Oprava pre HA 2027.8: zariadenie okruhu cez `via_device_id`, HACS minimum 2026.8.0.

## 2026-10-04 – implementácia, míľnik 1
- Kód rozdelený na čisté jadro `core/` (bez importu HA, testované priamo) a HA vrstvu (`house.py`, entity, config flow). Vzor od Hydronicus.
- Míľniky: 1 = iba sledovanie (žiadne povely), 2 = výstupy a potvrdzovanie povelov, 2b = ochrany, 3 = okná.
- Regulácia zmiešavača zachováva dnešný `MixerAutomation`: krok `min(5 + round(|odchýlka|), 10) %`, hysteréza, otváranie znamená „viac“ aj pri chladení. Nové: dotlak na doraze najviac raz za 10 min, pri dosiahnutí dorazu dobeh 2 s.
- Záloha podľa vonkajšej teploty (pre kotly) medzi prahmi vracia `off`; záloha podľa nádrže medzi prahmi drží posledný režim.
- Rosný bod okruhu = rosný bod najvyššej teploty termostatov a najvyššej vlhkosti senzorov okruhu (konzervatívne, senzory nie sú párované po izbách).
- Preklady en + sk. Bez commitu, kým nepovieš.

## 2026-10-04 – čo preberáme z Hydronicus
Podklad: [hydronicus-porovnanie.md](hydronicus-porovnanie.md). Doplnené do architektúry, sekcia „Bezpečnosť a prevádzka“.

**Preberáme:**
- Dry run (`switch.<dom>_control_equipment`) a ozbrojovanie výstupov po jednom v options flow. Nahrádza jednorazový paralelný beh pri migrácii.
- Potvrdzovanie povelov podľa stavu entity, opakovanie (10 s → max 5 min), po 3 pokusoch Repair a stav `degraded`. Nepotvrdené vypnutie relé zmiešavača = neistá poloha → homing.
- Čerpadlo až keď požiadavka trvá dobu otvárania hlavíc (3 min), zdroj až po potvrdenom behu čerpadla, dobeh 3 min po kúrení.
- Pauza pri zmene heat ↔ cool (predvolene 1 h), návrat do posledného režimu bez pauzy.
- Ochrana pred mrazom (< 5 °C, +1 K) cez zapnutie kúrenárskeho termostatu zóny.
- Protáčanie: čerpadlá 1 min po 7 dňoch nečinnosti, zmiešavač homing po 7 dňoch bez pohybu.
- Kondenzácia: rosný bod zóny (najvyššia teplota + najvyššia vlhkosť), cieľ vody ≥ rosný bod + 2 K, blokovanie s hysteréziou 2/3 K, voliteľný kondenzačný spínač.
- Reštart HA neposiela povely, stav a časovače sa ukladajú a obnovia.
- Nový `sensor.<dom>_status` s atribútmi `proposed` a `reason`.

**Nepreberáme:** vlastné digitálne termostaty, ovládanie zónových ventilov (spína ich `generic_thermostat`), plant súbor v YAML, pravidlo „nedostupné okno = zatvorené“ (ostáva správanie Window Climate: nič nemení).
Prečo: nesedí s naším modelom, kde termostat ovláda hlavice a integrácia riadi okruhy.

**Overené (2026-10-04):** na poschodí má každá miestnosť vlhkomer, kondenzačná ochrana sa dá nasadiť.

## 2026-10-04 – okná a Window Climate
- **Jedna integrácia:** otvorené okno je súčasť novej integrácie ako modul, ktorý sa zapína a vypína v nastaveniach domu.
- Modul funguje aj v dome bez okruhov (iba termostaty / AC). Preberá funkcie Window Climate (zóny okien, oneskorenia, štítok, obnovenie režimu, logbook, notifikácie, hlas), každá funkcia je voliteľná.
- `ha-window-climate` sa do novej integrácie zlúči a po prechode sa odstráni.
- Názov integrácie: **Climate Circuits** (`climate_circuits`, repo `ha-climate-circuits`). Porovnanie s podobným projektom [Hydronicus](https://github.com/brumi1024/ha-hydronicus) v [hydronicus-porovnanie.md](hydronicus-porovnanie.md).

## 2026-10-04 – otvorené otázky z architektúry
- **Poloha zmiešavača:** integrácia ju počíta sama priamo nad relé. `cover_time_based` sa po prechode odstráni.
  Prečo: jednoduchšia ochrana motora (interlock, max doba zopnutia) a dotlak.
- **Dotlak na doraze (2 s impulz pri 0 % / 100 %):** najviac raz za 10 min, nie v každom 30 s cykle.
  Prečo: dnes ~2 880 spínaní denne na ventil. Spínanie relé zmiešavačov časovo sedí s výpadkami SA8R-011.
- **Otvorené okno:** rieši integrácia, okenné senzory per zóna pre kúrenárske aj chladiace termostaty.
  Skript `kurenie_pri_okne` sa po prechode odstráni.
- **Prepnutie režimu heat↔cool:** zapne celú sadu termostatov nového režimu, vypnuté zóny si nepamätá (ako dnes).

**Otvorené:**

## 2026-10-01 – architektúra a univerzálnosť
- Cieľ: custom integrácia pre ďalšie domy, nezávislá od typu zdroja tepla.
- Režim domu podľa poradia zdrojov: ručný prepínač → entita zdroja tepla → záložná teplota (nádrž / vonkajšia) → posledný režim.
- I/O dosky (SA8R-011) sú čisté remote I/O. Interlocky, max doba zopnutia a stav po reštarte rieši HA/integrácia, nie firmvér.
- Okruhy ako subentries, konfigurácia iba cez UI, distribúcia cez HACS.
- GF čerpadlo zatiaľ bez vlastníka (prízemie nemá zóny). V integrácii bude zapnuté pri režime heat/cool.

## 2026-09-29 – 2026-10-01 – úpravy v dnešnom dome (HA)
- `binary_sensor.cfg_f1_poziadavka` + `Control Obehovky` riadia F1 čerpadlo.
- `script.mixerautomation` s `demand_sensor`: bez požiadavky sa zmiešavač zatvorí.
- `script.homezmiesavace` + `Mixers Homing Guard`: príznak `cfg_mixers_are_homing` zostáva ako zámok.
- `sensor.cfg_hvac_mode` (heat/cool/off), dva zoznamy termostatov (kúrenie / chladenie).
- SA8R-011: statická IP, diagnostika, pripnutý `dtr0xx_io`, bez `web_server`. Výpadky pravdepodobne spôsobuje rušenie od spínania servopohonov, RC členy ešte nie sú osadené.
