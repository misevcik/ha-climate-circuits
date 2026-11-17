# Kedy zdroj nestačí – štatistika 5.–11. 11. 2026

Podklad: história `binary_sensor.f1_source_not_enough` a `binary_sensor.gf_source_not_enough`. Zapne sa, keď je zmiešavač 100 % otvorený a prívod je stále pod cieľom. Ďalej história nádrže (`sensor.akumulacna_nadrz_temperature`), nastavenia tepelka (`sensor.akumulacna_nadrz_set_temperature`), výstupu a spiatočky tepelka (`sensor.gf_heatpump_out/in_temperature`), prívodu F1 (`sensor.gf_mixer_up_temperature`) a polohy zmiešavača F1.

## Počty po dňoch

| deň | F1 krát | F1 spolu | F1 5–10 h | F1 najdlhšie | GF krát | GF spolu | GF najdlhšie |
|---|---|---|---|---|---|---|---|
| 5. 11. | 4 | 3,5 h | 3,1 h | 181 min | 3 | 3,3 h | 181 min |
| 6. 11. | 3 | 2,7 h | 2,4 h | 105 min | 3 | 2,8 h | 109 min |
| 7. 11. | 3 | 3,7 h | 3,1 h | 189 min | 4 | 4,0 h | 194 min |
| 8. 11. | 10 | 8,7 h | 3,5 h | 210 min | 4 | 3,3 h | 92 min |
| 9. 11. | 16 | 5,6 h | 2,2 h | 99 min | 5 | 0,3 h | 10 min |
| 10. 11. | 10 | 6,1 h | 3,5 h | 162 min | 4 | 0,8 h | 32 min |
| 11. 11. | 7 | 3,2 h | 2,8 h | 131 min | 4 | 1,5 h | 76 min |
| **spolu** | **53** | **33,5 h (20 %)** | | | **27** | **15,9 h (9 %)** | |

8. 11. bol zlý celý deň, lebo rezerva 2 °C z 0.1.29 nestačila (pozri [f1-curve-check-2026-11-08.md](f1-curve-check-2026-11-08.md)). 9.–10. 11. pridala kompenzáciu zdroja, ktorá privierala zmiešavač (opravené v 0.1.30). GF sa po 9. 11. výrazne zlepšilo.

## Vzorec: každé ráno 5–9 h

Každý deň je jeden dlhý výpadok ráno (1,5–3 h). Cez deň sú len krátke poklesy 7–20 min, každý po ohreve TÚV alebo odmrazovaní, ktoré nádrž ochladia. 11. 11.:
- 09:18 po TÚV 09:07–09:12
- 11:19 po odmrazovaní 11:00–11:06
- 14:40 po TÚV 14:21–14:31
- 20:02 po TÚV 19:45–19:52

## Ráno 11. 11. (06:00–08:30), vonku okolo −2 °C, vlhkosť ~98 %

| | hodnota |
|---|---|
| nastavenie tepelka (od integrácie) | 51 → 53 °C |
| výstup tepelka | priemer 42,9 °C, max 49,8 °C |
| spiatočka tepelka | priemer 38,6 °C (ΔT ~4,3 K) |
| nádrž | 42–43 °C |
| cieľ F1 | 46,5 °C (izba 23 °C z Entry) |
| prívod F1 | priemer 40,2 °C, zmiešavač 100 % celý čas |
| odmrazovanie | 06:05, 06:59, 07:57 (každú hodinu) |

Poobede (12:30–15:30, vonku +5 °C): nastavenie 48 °C, výstup tepelka ~46 °C (ΔT ~7,6 K), zmiešavač F1 78–88 %. Voda stačí.

## Záver

- Riadenie nastavenia funguje: ráno zvýšilo tepelko až na 53 °C.
- Tepelko svoje nastavenie ráno nedosiahne. Výstup má o ~10 K menej a ΔT je polovičné oproti poobediu, čiže dáva výrazne menej výkonu. Zodpovedá to hodinovému odmrazovaniu pri ~0 °C a 98 % vlhkosti (najhoršie podmienky na námrazu), prípadne obmedzeniu výkonu tepelka.
- Eco vylúčené: podľa aplikácie AUX nie je eco zapnuté ani pre kúrenie, ani pre TÚV. `preset_mode: eco` v HA je zlé mapovanie integrácie. Tichý režim je `off`. `hp_auto_wtemp` integrácia nevie prečítať (`unknown`).
- Večer 11. 11. pri +5 °C tepelko nastavenie dosahuje: nastavenie 48 °C, výstup 48,4 °C, nádrž 45 °C.
- Merač `sensor.dtsu666_celkovy_vykon_pt` (možno celý dom) ukazuje hodinové priemery 3,8 / 4,3 / 4,6 / 4,1 / 3,8 kW medzi 4 a 9 h, maximá 5,0–5,4 kW. Cez deň okolo 2 kW. Ráno teda tepelko beží naplno a viac nedá: je to hranica výkonu pri −2 °C a námraze.
- Ranný dopyt zvyšuje nábeh spální z nočného útlmu (14 °C) v rovnakom čase.
- Dopyt zvyšuje izba 23 °C z Entry: celá krivka F1 je o ~1,3 K vyššie než s 22 °C.

## Čo pri −15 °C (odhad, 11. 11.)

- **Tepelná strata domu:** regresia denného priemerného príkonu DTSU666 na dennú priemernú vonkajšiu teplotu (`sensor.bthome_sensor_47f1_temperature`), 12. 10.–10. 11., 30 dní, r = −0,94. Výsledok P_el ≈ 2,99 − 0,170·T kW. Prepočet na teplo cez COP z tabuliek AUX (voda 45 °C, 75 %) a základnú spotrebu domu 0,3–0,7 kW dáva **teplo ≈ 8,8 − 0,53·T kW** (±15 %, vrátane TÚV):
  - pri −2 °C ~9,8 kW;
  - pri −10 °C ~14 kW;
  - pri −15 °C ~16,5 kW.
- **Max. výkon tepelka** ACHP-H14 (tabuľky AUX, 100 %, voda 50–55 °C), bez strát odmrazovaním:
  - pri −2 °C 11,9 kW;
  - pri −7 °C 11,5 kW;
  - pri −10 °C 11,0 kW;
  - pri −15 °C 10,7 kW.
- **Bivalentný bod:** pri dennom priemere ~−3 až −5 °C. Pod ním tepelko samo nestačí ani počas dňa a pri −15 °C chýba ~6 kW.
- **Bez záložnej špirály:** model ACHP-H14/5R2HA-M**(NE)** = „No electric heating“ (Technical and Service manual, s. 4 a 9). Používateľ potvrdil, že špirálu nemá. Pod bivalentným bodom teda nič nedopĺňa: pri −10 °C chýba ~3 kW, pri −15 °C ~6 kW.
- **Možnosti:**
  - Doska má výstup „Auxiliary heat source“ (svorka 43, 230 V, cez stykač) a parametre Tao_AHS_ON / t_AHS_DELAY (pôvodne pre plynový kotol). Môže ním spínať externý zdroj, napr. elektrickú vložku v akumulačke.
  - Alebo spínanie z HA podľa „zdroj nestačí“.
  - Alebo iný zdroj tepla v dome.
- **Dôsledok pre integráciu:** pod −5 °C rezerva nad krivkou (nastavenie = cieľ + rezerva) drží nastavenie nad tým, čo tepelko samo dosiahne. Špirála tak môže bežať aj vtedy, keď by stačilo tepelko.

## Doplnenie špirály (rozbor, 11. 11.)

- **Do vonkajšej jednotky – nie.** (NE) je verzia „Basic“ bez vnútornej špirály. Manuály neuvádzajú žiadnu dodatočnú súpravu. Zostava s IBH (svorky č. 11, 14, 25 na doske) je výrobná verzia „Customized“. Jednotka je na R290 (horľavé chladivo), takže zásah do nej môže robiť len servis AUX a stratila by sa certifikácia. Prípadnú prestavbu treba riešiť iba cez AUX.
- **Oficiálna cesta pre (NE):** externý zdroj na výstupe **AHS – „Additional heat source control“** (doska č. 43, 230 V, max 0,2 A → stykač KM6). Installation manual, s. 43: „This part only applies to Basic. For Customized, because there is an internal backup heater in the unit, the indoor unit should not be connected to any additional heat source.“
- **Logika AHS** (Technical and Service manual):
  - zapne, keď je vonku < Tao_AHS_ON (predvolené −5 °C) a výstup hydraulického boxu < TsetAC − dTSH_ON, a to až po t_AHS_DELAY (predvolené 30 min) chodu kompresora;
  - vypne, keď je vonku ≥ Tao_AHS_ON alebo výstup ≥ TsetAC + dTSH_OFF;
  - MODE_GAS = HEAT.
- **Návrh:** elektrická vložka 6–9 kW (3 × 400 V, s vlastným termostatom a bezpečnostnou poistkou) do akumulačky, do hornej časti, odkiaľ idú okruhy. Spínanie stykačom: z AHS, alebo z HA podľa „zdroj nestačí“. Druhá možnosť je prietokový elektrokotol v potrubí. Treba zistiť voľnú nátrubku akumulačky (obvykle G 6/4"), istenie domu a samostatný okruh od elektrikára.
- **Kábel 1,5 mm² Cu (3 × 400 V):** zaťažiteľnosť podľa STN 33 2000-5-52 (PVC, 3 zaťažené vodiče, 30 °C) je 13,5 A v izolovanej stene, 15 A v rúrke na stene a 17,5 A pri voľnom uložení na stene. P = √3 · 400 V · I:
  - 10 A → 6,9 kW;
  - 13 A → 9,0 kW;
  - 16 A → 11,1 kW.

  Vložka 9 kW berie ~13 A na fázu, pri 235–240 V až ~14 A. To je na hrane, nesmie to byť v zväzku s inými káblami a istič môže byť najviac 13 A. Odporúčanie: na 1,5 mm² vložka 6 kW (B10), pre 9 kW kábel 5 × 2,5 mm² (B16). Konečné posúdenie robí elektrikár.

## Cirkulácia TÚV beží stále (11. 11.)

- `switch.gf_heating_cycle_pump` (TUV Circulation Pump) bežal za 24 h **98,5 % času** (23,6 h).
- **Nastavenie:**
  - prah *Circulation threshold* 36 °C, *delta* 1,5 (zapína pod 34,5 °C);
  - TÚV v AC Freedom znížená na 40 °C.
- **Priebeh:**
  - bojler TÚV (`sensor.aux_cloud_…_hp_water_tank_temp`) sa pohybuje medzi 35 a 41 °C a ohrieva sa ~5× za deň;
  - spiatočka cirkulácie má 31–36 °C, hodinové priemery 31,3–35,0 °C;
  - straty v rozvodoch sú ~4–6 K, takže 36 °C sa takmer nedá dosiahnuť.
- **Dôsledok:**
  - stála cirkulácia ochladzuje bojler o ~6 K za ~5 h;
  - tepelko ohrieva TÚV ~5× denne po ~30 min, a vtedy kúrenie nedostáva nič;
  - výpadky „zdroj nestačí“ 09:18, 14:40 a 20:02 nasledovali po ohreve TÚV.
- **Chyba logiky:** keď je bojler chladnejší než prah + straty, čerpadlo nikdy nevypne.
