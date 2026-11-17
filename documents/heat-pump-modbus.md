# Tepelko AUX – pripojenie cez Modbus RS485

Cieľ: čítať priamo z tepelka výstup a spiatočku vody, nastavenie, frekvenciu kompresora, príkon a odmrazovanie a nastavovať ho lokálne namiesto cez AUX cloud. Rozbor ranného nedostatku je v [source-shortfall-2026-11-11.md](source-shortfall-2026-11-11.md).

## Tepelko

- **AUX ACHP-H14/5R2HA-M(NE)**: R290 monoblok, 14 kW, trojfázový (záložná špirála 9 kW). Patrí do radu, ktorý pokrývajú manuály AUX R290 nižšie. Zdroj typu: `~/work/tepelne cerpadlo/Tepelné čerpadlo Specification.rtf` (export konverzácie s Gemini).
- Ovládanie je cez aplikáciu AC Freedom, v HA cez `aux_cloud`. Nástenný ovládač je zapojený konektorom do **CN15**.
- Plánovaný prevodník je Dingtuang DT-R004 (RS485 → TCP, `rtuovertcp`, 192.168.0.219:502). Na tej istej zbernici je už elektromer DTSU666 (svorky 24 A / 25 B).

## Porty na hlavnej doske hydraulického modulu

Zdroj: Technical and Service manual, Part12, s. 56, fotka dosky s potlačou. Horný rad zľava:

| potlač | čo to je | pre HA |
|---|---|---|
| 0-10V-MV CN45 | výstup 0–10 V | nie |
| D.BL CN24 (+ červený konektor) | č. 2 „Parallel“ – kaskáda | nie |
| **CN23** (2 skrutky, na doske „A1 B1“) | v legende manuálu chýba | **možno** – overiť |
| **485-BUS CN13** (biely konektor) | č. 4 „Refrigerant system communication“ – vnútorná zbernica k vonkajšej jednotke | **NIKDY** – zapojením by sa rozbila komunikácia doska ↔ kompresor (chyba „Communication fault between refrigerant system and water system“) |
| **Modbus CN12** (biely konektor) | v legende chýba, potlač „Modbus“ | **áno – kandidát č. 1** |
| CF CN22 (B A GND 12V) | ? | zatiaľ nie |
| C-MNL1 CN15 (modrý) | káblový ovládač | nie (už zapojený) |

Ďalšia zdokumentovaná cesta je zadná strana **káblového ovládača** (Installation and Commissioning manual, kap. 10.6, obr. 3): svorkovnica `B A | B A 24V GND`. Dvojica ① B/A je „Signal to BMS/Central controller“.

**Overenie CN23:** pri vypnutom tepelku zmerať multimetrom prechod medzi A1/B1 na CN23 a pinmi konektora CN12. Ak sú prepojené, CN23 sú skrutkové svorky toho istého Modbusu a dá sa zapojiť do nich.

## Pozor na rady z Gemini

- Odporúčanie zapojiť RS485 do „svorky č. 4“ je **nebezpečné**: je to CN13, vnútorná zbernica.
- Adresy registrov, parametre (9600 8N1, slave 1), „servisné heslo 234“ a označenie H1/H2 Gemini prevzal z Midea M-Thermal. Sú navzájom nekonzistentné (spiatočka raz na adrese 6, inak 1; adresa 38 raz príkon, raz max. teplota TÚV). Pre AUX nie sú overené a **nepoužívať**. Manuál AUX uvádza servisné heslo **1234**.

## Mapa registrov a parametre – chýbajú

- AUX UK uvádza „Native RS485 Modbus with a documented register map“, ale v stiahnutých dokumentoch mapa nie je. Prezreté: Parameter Description, Unit Operating Parameter, Installation and Commissioning, Technical and Service, Schematics; XK08 a Installation and Operation sú skeny bez textu. Jediná zmienka: „MODBUS allow setting range“ pre automatický režim (kúrenie 25–65 °C, chladenie 5–25 °C).
- Ďalší krok: vyžiadať od AUX UK (info@auxuk.com) alebo od predajcu „Modbus protocol / register map, R290 monoblock ACHP-H14/5R2HA-M(NE), port CN12“.
- Náhradná cesta: po zapojení prečítať rozsahy registrov (napr. `mbpoll` cez DT-R004) a priradiť ich k hodnotám z ovládača a AC Freedom (výstup, spiatočka, T5, vonkajšia teplota, frekvencia).

## Ako zistiť registre bez dokumentácie (postup)

1. **Komunikačné parametre:** skúšať kombinácie rýchlosti (9600, 19200, 4800, 2400) a parity (N, E) a adresy 1–16 jedným čítaním registra 0. Odpoveď alebo Modbus výnimka znamená, že sme trafili.
2. **Mapa adries:** len čítanie (FC03 holding, FC04 input) po blokoch v rozsahu 0–2000. Výnimka 02 (illegal address) ukáže, kde registre nie sú.
3. **Záznam a korelácia:** niekoľko hodín čítať všetky živé registre každých 30 s. Popri tom máme z HA výstup a spiatočku tepelka, nádrž, vonkajšiu teplotu, nastavenie (cloud), TÚV, odmrazovanie a príkon (DTSU666). Skript priradí každému registru najlepšiu zhodu so signálom vrátane mierky (1 / 0,1 / 0,01) a posunu.
4. **Aktívne testy:** zmeniť jednu vec v AC Freedom (nastavenie 48 → 49, TÚV 40 → 41, tichý režim) a porovnať výpis registrov pred a po. Takto sa nájdu registre nastavení. Pomôžu aj predvolené hodnoty a rozsahy z Parameter Description Manual.
5. **Zápis** až po zmapovaní a len do overeného registra nastavenia. Do neznámych holding registrov nikdy, mohli by to byť inštalačné parametre.

Ďalšia možnosť je pasívne odpočúvať zbernicu ovládača (CN15). Ovládač číta všetko, čo zobrazuje, takže ak ide o Modbus, uvidíme adresy a hodnoty. Na to treba prevodník, ktorý iba prijíma a nevysiela (USB-RS485 alebo ESP32).

## Výkon podľa tabuliek AUX (Unit Operating Parameter Manual, s. 24–25, 14 kW, 100 %)

| vonku | voda 40 °C | 45 °C | 50 °C | 55 °C |
|---|---|---|---|---|
| −2 °C | 11,3 kW / 3,9 kW el. | 11,9 / 4,5 | 11,9 / 5,0 | 11,8 / 5,2 |
| +5 °C | 13,1 / 3,5 | 13,4 / 4,0 | 13,5 / 4,4 | 13,5 / 4,8 |

Ráno 11. 11. bol priemerný príkon domu (DTSU666) 4,3–4,6 kW, takže tepelko bežalo blízko 100 %. Tabuľky neobsahujú straty odmrazovaním.

## Zbernica s DTSU666

Zdieľať zbernicu s DTSU666 je možné, iba ak má tepelko rovnakú rýchlosť a paritu a inú adresu ako elektromer. Kým parametre tepelka nepoznáme, je bezpečnejšie skúšať na samostatnom prevodníku, aby sa nerozbilo čítanie elektromera.

Zdroje: <https://auxuk.com/aux-r290-monoblock> (dokumenty `/downloads/heat-pump/aux-r290-heat-pump-*.pdf`), Technical and Service manual V1 (auxcyprus.com), Installation and Commissioning manual V2 (auxsolutions.gr).
