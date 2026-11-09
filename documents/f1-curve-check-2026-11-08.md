# Kontrola krivky F1 (poschodie) – 2026-11-08

Podklad: história 8 termostatov F1 za 4.–8. 11. 2026 (komfortné hodiny = nastavená teplota ≥ 20 °C), hodinové štatistiky cieľa vody F1, polohy zmiešavača F1 a výstupu z nádrže, `binary_sensor.f1_source_not_enough`. Krivka F1: izba 22 °C, −15 °C → 55 °C (od 8. 11. 55,5 °C, max 55,5), n = 1,3, radiátory; izba z termostatov (najvyššia nastavená teplota kúriacich zón).

## Izby (komfortné hodiny, 5.–7. 11.)

| Zóna | cieľ | kúri | priemer izba − cieľ | poznámka |
|---|---|---|---|---|
| Entry (hallway) | 23 | 94–100 % | −0,8 až −1,2 °C | nikdy nedosiahne cieľ |
| Kids Bathroom | 23–23,5 | 20–34 % | +0,3 až +0,4 | často nad cieľom |
| Kitchen & Livingroom | 23 (noc 22) | 15–20 % | +0,25 až +0,35 | ráno 22 → 23 trvá 5,5–7 h |
| Office | 23 | 8–11 % | +0,9 až +1,2 | prehrieva sa |
| Parents Bathroom | 23–23,5 | 22–28 % | +0,4 až +0,6 | nad cieľom |
| Miska Bedroom | 21,5 (noc 14–16) | 28–33 % | 0 až +0,8 | ranný nábeh ~4,5 h |
| Parents Bedroom | 21,5 (noc 14–16) | 25–41 % | 0 až −0,2 | ranný nábeh 2–4,5 h |
| Romo Bedroom | 21,5 (noc 14–16) | 7–29 % | ~0 | ranný nábeh 3–5 h |

## Voda

- 5.–7. 11.: *Zdroj nestačí* (F1) každé ráno ~6:00–9:00 (1,75–3 h) a krátko v noci (odmrazovanie/TÚV); cez deň zmiešavač F1 priemerne 40–90 %, voda stačila.
- 8. 11. (0.1.29, tepelko = cieľ + 2 °C): *Zdroj nestačí* ~7 h cez deň (9:08–11:08, 12:07–13:06, 16:59–20:29, 21:06–21:22); zmiešavač F1 9:00–21:00 trvalo 100 %, výstup z nádrže 37–40 °C pri cieli 41–44 °C. Výstup z nádrže je ~7–8 °C pod nastavením tepelka.

## Záver

1. **Krivka F1 je v poriadku** – keď voda stačí, izby cieľ dosahujú, termostaty cyklujú (kúria 10–35 % času) a viaceré sú nad cieľom. Zvyšovať ju netreba.
2. **Entry** je výnimka (radiátor / ventil / cieľ 23 °C na chodbu). Kvôli nej nezvyšovať celú krivku. Entry s 23 °C a kúrením ~100 % drží izbovú teplotu krivky F1 trvalo na 23 °C (+~1,5 °C vody pre celé poschodie).
3. **Pomalý ranný nábeh** spální (4–5 h) je hlavne nedostatok vody ráno (*Zdroj nestačí* 6–9 h), nie krivka.
4. **8. 11. chýbala voda celý deň**: rezerva 2 °C nestačí, lebo voda z nádrže je ~7–8 °C pod nastavením tepelka.
