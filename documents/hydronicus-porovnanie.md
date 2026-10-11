# Porovnanie: Climate Circuits vs. Hydronicus

Stav k 2026-10-04. Hydronicus [v0.3.0](https://github.com/brumi1024/ha-hydronicus), licencia MIT, vyžaduje HA 2026.9+, ~10 400 riadkov Pythonu.
Náš návrh: [architektúra Climate Circuits](https://claude.ai/code/artifact/81911fb1-a778-4b1f-8cc1-8477411ab975).

## Záver

Hydronicus nemôže nahradiť Climate Circuits v našom dome. Rieši iné jadro problému:
- **Hydronicus** koordinuje zónové ventily, čerpadlá a požiadavku na zdroj, aby sa to dialo v bezpečnom poradí.
- **Climate Circuits** reguluje zmiešavač podľa ekvitermickej krivky.

Hydronicus nemá zmiešavač, krivku ani teplotu výstupu („does not set a flow temperature yet“). Má však niekoľko bezpečnostných mechanizmov, ktoré stojí za to prevziať.

## V čom sú podobné

| Oblasť | Obe riešenia |
|---|---|
| Konfigurácia | jedna config entry na dom/systém, zóny alebo okruhy ako subentries, všetko cez UI |
| Termostaty | existujúce `climate` entity iba čítajú, požiadavka z `hvac_action` |
| Vlastník výstupu | každý výstup má jednu rolu a jedného vlastníka, integrácia pravidelne zosúlaďuje skutočný stav s požadovaným |
| Chýbajúce dáta | nedostupný senzor znamená bezpečný stav, nie výpočet s nulou |
| Kúrenie / chladenie | ten istý okruh robí oboje, nikdy naraz |
| Okno | okenné senzory na zónu s oneskorením |
| Prečo sa rozhodlo | atribúty `reason` na entitách |
| Distribúcia | HACS |

## V čom sa líšia

| Oblasť | Climate Circuits (náš návrh) | Hydronicus |
|---|---|---|
| Zmiešavač | 3-bodový alebo 0–10 V, regulácia na cieľovú teplotu vody, homing, dotlak, ochrana motora | žiadny, iba ventily otvor/zatvor (`switch` / `valve`) |
| Teplota vody | ekvitermická krivka na okruh, pre kúrenie aj chladenie | nenastavuje |
| Režim domu | automaticky zo zdroja (climate tepelného čerpadla, nádrž, vonkajšia teplota) + ručný override | iba ručný `select`, automatiku treba dorobiť automatizáciou |
| Zónové ventily | prepína `generic_thermostat`, integrácia ich neovláda | ovláda Hydronicus, má aj vlastné digitálne termostaty |
| Poradie štartu | čerpadlo s oneskorením (napr. 3 min) po požiadavke | ventily → po potvrdení otvorenia a 3 min čerpadlo → po potvrdení behu zdroj; vypínanie v opačnom poradí s dobehom čerpadla |
| Potvrdenie povelov | nie je navrhnuté | povel platí až keď ho HA ukáže v stave; opakovanie s backoff, po 3 pokusoch Repair a stav `degraded` |
| Spustenie naostro | „paralelný beh iba na čítanie“ ako krok migrácie | Dry run + Arm outputs + prepínač Control equipment, natrvalo v produkte |
| Kondenzácia | spodná hranica krivky, voliteľne rosný bod + rezerva | detailná ochrana: rosný bod per zóna, hysteréza 2/3 K, povrchové minimum, max vlhkosť, kondenzačný spínač |
| Zmena heat ↔ cool | okamžite | najprv zastaví starý režim, potom počká 1 h (mode dwell) |
| Ochrana pred mrazom | nie | zóna pod 5 °C sa kúri vždy |
| Proti zatuhnutiu | nie | raz týždenne protočí nečinné čerpadlá a ventily |
| Zdroj tepla | `switch`, OpenTherm s teplotou výstupu (plán) | `switch` požiadavky + `select` režimu, min. doba behu/pauzy |
| Okno | vypne termostat a obnoví režim; logbook, notifikácie a hlas (z Window Climate) | zóna prestane žiadať, termostat nemení, bez oznamov; nedostupný senzor = zatvorené |
| Zrelosť | návrh | v0.3.0, rozsiahle testy vrátane simulátora |

## Čo prevziať do Climate Circuits

1. **Dry run a arming:** nový dom najprv iba navrhuje povely, výstupy sa „ozbrojujú“ po jednom. Nahradí náš jednorazový paralelný beh.
2. **Potvrdenie povelov:** povel platí až keď ho ukáže stav entity, potom opakovanie a Repair. Priamo to rieši výpadky SA8R-011, keď sa povel stratí.
3. **Čerpadlo až po potvrdenom otvorení:** namiesto pevného oneskorenia čerpadla počkať, kým požiadavka trvá dobu otvárania hlavíc.
4. **Pauza pri zmene heat ↔ cool.**
5. **Ochrana pred mrazom a protáčanie čerpadiel:** lacné na implementáciu, užitočné v každom dome.
6. **Kondenzačná ochrana pri chladení:** rosný bod per zóna namiesto iba spodnej hranice krivky.

Licencia MIT dovoľuje prevziať aj kód, s uvedením autorov.

## Alternatíva

Doplniť zmiešavač a krivku priamo do Hydronicus ako príspevok. Hydronicus však neovláda náš model, kde zónové relé spína `generic_thermostat`. Pridali by sme veľkú časť do cudzieho projektu bez kontroly nad jeho smerovaním. Preto to neodporúčam.
