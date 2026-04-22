# Realistic Operational Value Ranges — Commercial Building, Boston MA (ASHRAE Zone 5A)

Reference document for regenerating value generators in the BACnet/Modbus simulator.
All temperatures °F, pressures psi/inWC, airflow CFM, power kW unless noted. "Typical" =
middle of normal operating envelope during occupied hours; "Peak design" = sizing value a
contractor would use; "Alarm" thresholds = points at which a building operator is likely to
be paged or a BAS will latch an alarm.

## Boston design conditions (ASHRAE 169 / NOAA KBOS, climate zone 5A)

| Condition | Value | Source |
|---|---|---|
| Winter 99.6% heating dry-bulb | **0 °F** | ASHRAE 169-2021 Climatic Data, Boston Logan |
| Winter 99% heating dry-bulb | **5 °F** | ASHRAE 169-2021 |
| Summer 1% cooling dry-bulb | **91 °F** | ASHRAE 169-2021 |
| Summer 1% mean coincident wet-bulb | **73 °F** | ASHRAE 169-2021 |
| Summer 0.4% dry-bulb / MCWB | **93 °F / 75 °F** | ASHRAE 169-2021 |
| Annual mean | **51 °F** | NOAA 1991–2020 normals, KBOS |
| January mean dry-bulb | **29 °F** | NOAA 1991–2020 normals |
| July mean dry-bulb | **74 °F** | NOAA 1991–2020 normals |
| January mean daily low / high | **22 / 37 °F** | NOAA 1991–2020 normals |
| July mean daily low / high | **66 / 82 °F** | NOAA 1991–2020 normals |
| Annual heating degree days (base 65) | ~5,600 HDD65 | NOAA KBOS |
| Annual cooling degree days (base 65) | ~780 CDD65 | NOAA KBOS |
| Mean annual wind speed | 12 mph | NOAA KBOS (coastal, windier than inland MA) |
| Prevailing winter wind | WNW, 14 mph | NOAA KBOS |
| Prevailing summer wind | SW, 11 mph | NOAA KBOS |

**Interpretation**: Boston is heating-dominated (~7× more HDD than CDD). Shoulder seasons
(Apr, Oct) have wide diurnal swings and economizer operation dominates. Simulator OAT
generator should spend ~60% of the year below 50°F.

## Typical occupied schedule (DOE medium office prototype, 53,628 sqft, 3 floors)

| Day type | Occupied hours | Notes |
|---|---|---|
| Weekday | 7:00 a.m. – 7:00 p.m. (peak 9 a.m. – 5 p.m., 95% occ) | Morning ramp 6–9 a.m., evening decay 5–8 p.m. |
| Saturday | 7:00 a.m. – 6:00 p.m. at 30% occupancy | Partial HVAC |
| Sunday / holidays | Unoccupied, setback only | ~5% lights for security/cleaning |
| Unoccupied setback | Heat 60°F, cool 85°F | ASHRAE 90.1 night-setback |
| Occupied setpoints | Heat 70°F, cool 75°F, 2°F deadband | DOE medium office default |

All time-of-day patterns in the tables below reference this schedule unless stated otherwise.

---

## 1. AHU — Air Handling Unit (VAV, central, ~20,000 CFM design)

Typical: DOE medium office has one ~20k-CFM AHU per floor serving ~30 VAV boxes.
Control: ASHRAE Guideline 36 trim-and-respond SAT reset, OA economizer, DX or CHW coil.

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Supply air temp (SAT) | °F | 58–65 (reset high, reheat at zones) | 55–58 (cooling) | 55 | 45 | 75 | Occupied only; night = fan off | G36 §5.16 SAT reset 55–68°F |
| Return air temp (RAT) | °F | 68–72 | 72–76 | — | 60 | 85 | Tracks space temp | DOE medium office |
| Mixed air temp (MAT) | °F | 40–60 (economizer closed at design) | 65–80 (economizer when OAT<65) | MAT ≥ 45 freezestat | 38 (freezestat trip) | 95 | Tracks (OA%·OAT + RA%·RAT) | ASHRAE Handbook Apps Ch. 47 |
| Outdoor air damper | % open | 15–30 (min OA) | 15–100 (economizer) | 100 (economizer) | — | — | Min OA when occupied, closed when unoccupied | G36 §5.16.4, ASHRAE 62.1 |
| Supply fan speed | % | 30–70 | 50–90 | 100 | — | 95 for >30 min | Ramp 6–7 a.m. to 100%, decay 7–9 p.m. | VFD field data, G36 |
| Supply fan status | bool | On 6 a.m.–8 p.m. weekday, off otherwise | same | — | Off when cmd on (fail) | — | Occupied schedule | — |
| Return fan speed | % | 25–65 (tracks SF −10 pts) | 45–85 | 100 | — | — | Follows supply fan | Trane AHU IOM |
| Supply static pressure | inWC | 1.0–1.5 (reset low with few zone reqs) | 1.2–2.0 | 2.5 | 0.3 (fan fail) | 3.5 | Reset per G36 trim-respond | G36 §5.16.3 duct SP reset 0.5–2.5 inWC |
| Supply airflow | CFM | 6,000–14,000 (part load) | 12,000–19,000 | 20,000 | 2,000 (fan min) | 22,000 | Tracks zone demand | DOE medium office IDF |
| Filter diff pressure | inWC | 0.4–0.8 (clean) rising | same | — | — | 1.5 (change filter) | Monotonic rise between changes | Trane/Carrier filter spec |
| Heating valve (HW) | % open | 20–80 (cold morning 100%) | 0–10 | 100 @ 0°F OAT | — | 100% stuck >30 min | High at AM warmup | G36 §5.16.5 |
| Cooling valve (CHW) | % open | 0 (locked out <50°F OAT) | 30–90 | 100 @ design | — | Stuck 100 >30 min | Evening peak hottest | G36 |
| Preheat coil discharge | °F | 45–55 | — | 45 min | 38 (freezestat) | — | Active winter only | ASHRAE Handbook |
| OA airflow (measured) | CFM | 3,000 (min OA ~20% of design) | 3,000–19,000 (economizer) | 4,000 (ASHRAE 62.1 Vbz) | 2,000 (ventilation fail) | — | Stepped by occupancy | ASHRAE 62.1 (5 cfm/pp + 0.06 cfm/sqft) |
| Mixed air humidity | %RH | 15–30 | 45–60 | 60 | — | 75 (condensation risk) | — | ASHRAE 55 |

**Notes**: Boston winter OAT of 0°F with 30% OA gives MAT of ~50°F (mixed with 72°F RA),
so freezestat trip at 38°F should only fire on damper failure or stuck economizer.

---

## 2. VAV — Variable Air Volume Box (zone-level, reheat, ~600 CFM design)

Typical VAV serves ~400 sqft of office with hot-water reheat coil. Single-maximum control
per Guideline 36 (airflow rides cooling loop, reheat activates at minimum airflow).

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Zone temp | °F | 68–73 (occ), 55–60 (unocc) | 72–76 (occ), 80–85 (unocc) | — | 60 (occ) | 85 (occ) | Setback night/weekend | G36 zone setpoints |
| Zone cooling setpoint | °F | 75 | 75 (74 at peak) | 74 | — | — | Static during occ | G36 default |
| Zone heating setpoint | °F | 70 (occ), 60 (unocc) | 70 | 72 | — | — | Setback outside 6 a.m.–10 p.m. | G36 default |
| Supply airflow | CFM | 120–200 (VAV min) | 250–600 | 600 (cooling design) | 80 (below min OA) | 700 (overshoot) | Min all occ hours, modulates on cooling | G36 §5.6 |
| VAV damper position | % open | 15–35 | 40–100 | 100 | — | — | Tracks airflow | — |
| Reheat valve | % open | 30–90 morning, 0–40 mid-day | 0 | 100 | — | Stuck 100 >1 hr | AM warmup highest | G36 §5.6.4 |
| Discharge air temp | °F | 85–95 (reheating) | 55–58 (cooling, no reheat) | 90 max reheat | — | 120 (valve stuck) | Heating dominant Boston 5 am–9 am | G36 §5.6.4 max DAT |
| CO2 (if sensed) | ppm | 400–900 | 400–1000 | — | — | 1100 (DCV call for more OA) | Rises 9 a.m., peaks 2 p.m. | ASHRAE 62.1 DCV |
| Occupancy sensor | bool | True 8 a.m.–6 p.m., sparse evenings | same | — | — | — | — | — |

**Boston note**: Perimeter VAVs on the N/E walls run heating into June mornings. Interior
zones are cooling-dominant year-round (plug + lighting load).

---

## 3. Chiller — Water-Cooled Centrifugal (300 ton design)

Typical: One 300-ton water-cooled chiller for ~50,000 sqft cooling-only. Locked out below
~55°F OAT (water-side economizer or dry cooler takes over). Boston chillers run May–Oct
peak, with ~1,000–1,400 equivalent full-load hours/yr.

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Chilled water supply (CHWS) | °F | 44 (reset high or off) | 42–44 | 42 | 38 (freeze) | 50 (loss of control) | Reset up on low load | ASHRAE 90.1 §6.5.4.4 CHW reset |
| Chilled water return (CHWR) | °F | 48–52 | 52–58 | 54 | — | 65 | Tracks load | 10–14°F ΔT design |
| CHW ΔT | °F | 6–10 (low load) | 10–14 | 14 | — | Low ΔT <6°F sustained | Rises with load | ASHRAE 90.1 15°F ΔT rule |
| Condenser water supply (CWS) | °F | 65–75 (economize to 65°F min) | 80–85 | 85 | — | 95 (tower undersized) | Floats with OAT/WBT | ASHRAE 90.1 §6.5.5 |
| Condenser water return (CWR) | °F | 75–85 | 92–95 | 95 | — | 105 | Tracks load | 10°F range design |
| Compressor kW | kW | 50–150 (light load) | 150–300 | 330 | — | 360 (surge) | Rises 10 a.m.–4 p.m. | Trane RTHF/CVHF catalogue |
| Part-load ratio (PLR) | % | 20–50 | 40–100 | 100 | — | — | Tracks cooling load | — |
| kW per ton | kW/ton | 0.55–0.75 (low-load penalty) | 0.50–0.58 | 0.55 (AHRI 550/590 full-load) | — | >0.9 (fouled) | Best at 60–80% PLR | ASHRAE 90.1 path A/B |
| COP | — | 5.0–6.0 | 6.0–6.8 | 6.3 (IPLV) | — | — | Inverse of kW/ton | AHRI 550/590 |
| Evap approach | °F | 2–4 | 3–5 | 5 | — | 8 (fouling) | — | Trane IOM |
| Cond approach | °F | 3–6 | 5–8 | 8 | — | 12 (fouled tubes) | Drifts up over months | Trane IOM |
| CHW flow | GPM | 400–600 | 600–720 | 720 (300 tons × 2.4 gpm/ton) | 200 (flow switch) | — | Primary pump constant; secondary VFD | Industry std 2.4 gpm/ton |
| CW flow | GPM | 750–900 | 850–900 | 900 (300 tons × 3 gpm/ton) | 300 | — | Usually constant | Industry std 3 gpm/ton |
| Chiller status | enum | Off Nov–Apr | Running 80% of occupied cooling hrs | — | Tripped | — | — | — |

**Note**: Condenser water reset down to 65°F in shoulder seasons is a big energy lever;
most Boston buildings hold 70–75°F min to avoid oil return issues on older chillers.

---

## 4. Boiler — Condensing Hot-Water (2.5 MMBtu/hr gas, hydronic)

Typical for 50,000 sqft: two lead-lag 1.5-MMBtu/hr condensing boilers sized for design
0°F. Boston boilers run 6 months/yr with design-day firing only 1–2% of hours. Outdoor
air reset (OAR) curve keeps supply water 120°F (mild) to 180°F (design cold).

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| HW supply temp (HWS) | °F | 140–170 (reset by OAR) | 110–120 (DHW only) or off | 180 @ 0°F OAT | 100 (loss of control) | 200 (safety trip 210) | Ramps with OAT | Deppmann/HPAC OAR curves |
| HW return temp (HWR) | °F | 120–140 | 100–110 | 140 | — | 170 (low ΔT) | — | 20–40°F design ΔT |
| ΔT | °F | 15–35 | 10–20 | 30 | — | <10°F (low-ΔT syndrome) | — | Condensing design 30–40°F ΔT |
| Firing rate | % | 20–90 (modulating) | 0 or 10–20 (DHW only) | 100 @ 0°F | — | 100% sustained >2 hr (undersized) | Peak at 5–8 a.m. warmup | Condensing boiler turndown 5:1–10:1 |
| Stack temp | °F | 100–140 (condensing) | 110–130 | 160 | — | 300 (heat exchanger fouled) | Tracks firing rate | Viessmann/Lochinvar spec |
| Efficiency | % | 92–97 (condensing mode) | 88–92 (non-condensing) | 95 (AHRI) | <85 (problem) | — | Higher at low fire | AHRI BTS-2000 |
| Gas input | ft³/hr | 500–2200 | 0–300 | 2,500 (2.5 MMBtu ÷ 1000 Btu/ft³) | — | — | Peaks at AM warmup | ASHRAE Fundamentals |
| Pump speed (primary) | % | 40–100 (variable primary) | 0 or 30–40 | 100 | — | — | On with call | ASHRAE 90.1 variable-speed pump |
| Pump status | bool | Running Oct–May | Off or short DHW cycles | — | Off w/cmd on | — | — | — |
| OAT (used for reset) | °F | −5 to 45 | 50–95 | 0 (design) | −10 | 100 | Fetched from local sensor | ASHRAE 169 |
| Boiler status | enum | Firing | Standby | — | Lockout | — | — | — |

**OAR curve (standard Tekmar/Heat-Timer shape)**: 180°F supply at 0°F OAT, linear down
to 120°F supply at 60°F OAT, off above 65°F OAT with 3°F WWSD hysteresis.

---

## 5. Cooling Tower — Open-Loop Crossflow (300 ton / 900 GPM)

Paired with the chiller above. Boston summer wet-bulb design 75°F; cold-weather operation
needs basin heater or sump draindown (typical below 40°F OAT).

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Entering water temp (EWT, = CWR) | °F | 75–85 (if running) | 92–95 | 95 | — | 105 | — | CTI/ASHRAE |
| Leaving water temp (LWT, = CWS) | °F | 65–75 (reset down) | 82–85 | 85 | 55 (min for chiller) | 95 (cannot reject) | Reset schedule | ASHRAE 90.1 §6.5.5 |
| Range (EWT−LWT) | °F | 5–10 | 8–10 | 10 | <3 (no load) | >12 | — | Design 10°F range |
| Approach (LWT−OAWB) | °F | 10–20 | 7–10 | 7 | — | 15 (fouling/scaling) | Rises with age | BAC/Marley spec sheet |
| Fan speed | % / Hz | 0–50 | 50–100 | 100 (60 Hz) | — | Stuck at 100 | Modulates on LWT | VFD standard |
| Fan status | bool | Off when OAWB<CWSsp | On during chiller run | — | Off w/cmd on | — | — | — |
| Basin temp | °F | 40–60 (basin heater 40°F lo) | 75–85 | — | 35 (freeze risk) | 100 | — | BAC freeze-protection |
| Makeup water flow | GPM | 0 (off) | 5–12 (evap + drift + blowdown) | 15 | — | 25 (leak) | Proportional to load | CTI: 3 GPM/100 tons typical |
| Drift (droplets) | % of flow | 0.001–0.005 | 0.001–0.005 | 0.005 (drift eliminator spec) | — | 0.01 (fouled eliminator) | — | CTI STD-140 |
| Blowdown | GPM | 0 | 1–3 (per cycle count) | 4 | — | — | Controlled on conductivity | ASHRAE Guideline 12 |
| Conductivity | µS/cm | 500–1500 | 1000–2500 | 3000 (bleed setpoint) | — | 3500 (scaling risk) | Rises between blowdowns | ASHRAE 188 |

---

## 6. DHW — Domestic Hot Water (400 gal tank, gas, with recirc)

Typical: one gas-fired storage heater feeding restrooms + kitchenette in medium office.
Legionella mitigation drives ≥140°F tank temp, tempering to 120°F at fixtures.

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Tank temp | °F | 135–145 | 135–145 | 140 setpoint | 120 (legionella risk) | 160 (scald / T&P trip 210) | Drops 8 a.m. rush | ASHRAE Guideline 12 |
| Supply temp (post mix) | °F | 118–122 | 118–122 | 120 | 105 | 135 (tempering valve fail) | — | ASHRAE 188 |
| Recirc return temp | °F | 105–115 (10–15°F drop) | 108–118 | 115 | 100 | 125 | Colder during AM rush | ASHRAE Handbook |
| Burner status | bool | Cycles 30–60 min | Similar | — | — | Stuck-on | Short cycles at night | — |
| Recirc pump status | bool | On continuously | On continuously | — | Off w/cmd on | — | — | ASHRAE 188 |
| Flue/stack temp | °F | 120–200 (condensing) or 300–400 (atmospheric) | same | — | — | 500 | — | Manuf. |
| Gas input | ft³/hr | 50–200 during firing | 50–200 | 250 | — | — | AM peak 7–9 a.m. | — |

---

## 7. FCU — Fan Coil Unit (zone, 400 CFM nominal, 2-pipe or 4-pipe)

Typical: one FCU per small private office or hotel-style room. 2-pipe changeover follows
season; 4-pipe has independent HW/CHW valves.

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Zone temp | °F | 68–73 | 72–76 | — | 60 occ | 85 occ | — | Same as VAV |
| Zone setpoint | °F | 70 | 75 | — | — | — | Occupied | — |
| Fan status | bool | Auto or continuous | Auto or continuous | — | Off w/cmd on | — | Occupied schedule | — |
| Fan speed | enum / % | Low/Med/High or 30–100% | same | 100% | — | — | High at startup | — |
| Heating valve | % open | 20–80 (morning), 0–30 midday | 0 | 100 | — | Stuck 100 | AM warmup | — |
| Cooling valve | % open | 0 | 30–80 | 100 | — | Stuck 100 | Afternoon peak | — |
| Discharge air temp | °F | 90–110 heating | 55–58 cooling | 110 heat / 55 cool | — | 130 (HW stuck) | — | ASHRAE Handbook |

---

## 8. Heat Pump — WSHP or VRF (10-ton condensing unit)

Common alternative to AHU/chiller in renovated Boston offices. COP degrades sharply below
20°F OAT for ASHP; WSHP on a ground loop is flatter.

| Point | Units | Winter typical (ASHP) | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Compressor status | bool | Cycling or modulating | Running | — | — | Locked out | Continuous in heating | — |
| Suction / return-line temp | °F | 30–45 (heating) | 40–55 (cooling) | — | 20 (low suction trip) | 65 | — | Manuf. |
| Liquid / supply-line temp | °F | 90–110 (heating cond temp) | 95–115 (cooling cond) | 120 | — | 135 (high head) | — | Manuf. |
| Outdoor coil temp (heating) | °F | 10–25 (defrost cycles below 32°F) | n/a | — | — | — | — | — |
| Defrost cycles/hr | count | 1–3 @ 20–30°F OAT, 0 above 40°F | 0 | — | — | >6 (defrost stuck) | — | DOE cold-climate HP studies |
| COP (heating) | — | 2.5–3.5 @ 30°F OAT, 1.8–2.5 @ 10°F | n/a | 3.8 @ 47°F (AHRI 210/240) | <1.5 | — | Best in shoulder | NEEP cold-climate ASHP specs |
| EER (cooling) | Btu/Wh | n/a | 11–14 | 14 | — | — | — | AHRI 340/360 |
| Capacity | % | 60–90 (derated at low OAT) | 80–100 | 100 | — | — | — | Daikin VRV, Mitsubishi Hyper-Heat |

**Boston cold-climate note**: standard ASHPs lose ~40% capacity at 5°F OAT. Cold-climate
"hyper-heat" units hold ~75% capacity to 5°F. Most installed Boston stock (pre-2020) falls
off a cliff below 20°F — simulator should reflect aux-heat staging.

---

## 9. Lighting Controller (per-zone, ~4,000 sqft zone, LED)

Priority-skipped detail per instructions; summary only.

| Point | Units | Typical | Peak | Notes |
|---|---|---|---|---|
| Zone dim level | % | 30–90 occ (with daylight harvest), 0 unocc | 100 | Drops in daylit zones 10 a.m.–3 p.m. |
| Occupancy status | bool | True 8 a.m.–6 p.m. weekdays | — | — |
| Zone power | W/ft² | 0.3–0.8 (LED) | 0.8 (ASHRAE 90.1 2022 LPD office) | — |
| Total floor lighting kW | kW | 5–15 (50k sqft) | 40 (full on) | — |

---

## 10. Electric Meter — Main Switchgear (480V/277V, 3-phase 4-wire, 800A service)

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Voltage L-L | V | 478–488 | 475–485 | 480 nominal | 456 (ANSI −5%) | 504 (ANSI +5%) | Sags slightly at afternoon peak | ANSI C84.1 |
| Voltage L-N | V | 276–282 | 274–280 | 277 | 263 | 291 | — | ANSI C84.1 |
| Voltage imbalance | % | <1 | <1 | — | — | 2 (NEMA derate starts) | — | NEMA MG-1 |
| Current (per phase) | A | 100–350 (heating light) | 300–650 (cooling peak) | 800 (service size) | — | 720 (90% breaker) | Peaks 2–4 p.m. summer | — |
| Real power (kW) | kW | 80–250 | 250–500 | 550 | — | 600 | Summer peak, occupied hrs | DOE medium office EUI 55 kWh/sqft/yr |
| Reactive power (kVAR) | kVAR | 20–60 | 60–150 | 180 | — | — | Tracks motor load | — |
| Apparent power (kVA) | kVA | 85–260 | 260–525 | 575 | — | — | — | — |
| Power factor | — | 0.92–0.98 | 0.90–0.96 | 0.95 utility target | 0.85 (utility penalty) | — | Worst at low load | Utility tariff |
| Frequency | Hz | 59.95–60.05 | 59.95–60.05 | 60 | 59.3 | 60.5 | — | NERC/ISO-NE |
| Accumulated energy | kWh | monotonic | monotonic | — | — | — | Stepped per occupancy | — |
| THD (voltage) | % | 1–3 | 1–3 | <5 (IEEE 519) | — | 8 | — | IEEE 519 |

---

## 11. RTU — Rooftop Unit (DX, 20 ton, gas heat, VAV)

Smaller building alternative to central plant. Boston RTUs need low-ambient kit for heating
(gas furnace section handles 0°F design fine; DX cooling locks out at 55°F OAT return).

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Supply air temp | °F | 85–110 (heating) | 55–60 (DX cooling) | 55 (cool) / 110 (heat) | 45 | 130 | — | G36 / Carrier IOM |
| Return air temp | °F | 68–72 | 72–76 | — | 60 | 85 | — | — |
| Mixed air temp | °F | 40–65 (25% min OA) | 68–85 | — | 38 freezestat | 95 | — | — |
| Supply fan speed | % | 40–80 | 50–100 | 100 | — | — | Occupied | — |
| Supply fan status | bool | Occupied schedule | — | — | — | — | — | — |
| Outdoor damper | % | 15–30 (min OA) | 15–100 (econ) | 100 | — | — | — | — |
| Compressor stage 1 | bool | Off | On 40–80% of cooling hrs | — | — | Short-cycling <3 min | — | Carrier Weathermaker |
| Compressor stage 2 | bool | Off | On 10–30% of cooling hrs | — | — | Short-cycling | Afternoon peak | — |
| Condenser fan | % | 0 | 50–100 | 100 | — | — | Tracks compressor | — |
| Heating stage 1 (gas) | bool | On 5 a.m.–9 a.m. AM warmup | Off | — | — | Stuck on | AM warmup | — |
| Heating stage 2 (gas) | bool | On cold mornings <20°F OAT | Off | — | — | — | — | — |
| Filter DP | inWC | 0.3–0.8 | 0.3–0.8 | — | — | 1.2 | — | — |

---

## 12. Weather Station (on-roof, Davis / Vaisala-class)

Boston Logan (KBOS) 1991–2020 normals used as baseline. Simulator should implement a
diurnal + seasonal sine wave with stochastic noise (±3°F hour-to-hour plausibly).

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Ambient dry-bulb | °F | Jan: mean 29 (night 22 / day 37) | Jul: mean 74 (night 66 / day 82) | 0 (winter) / 91 (summer) | −10 (record low roof sensor) | 100 (record high) | Sinusoidal, min 5–6 a.m., max 2–4 p.m. | NOAA KBOS 1991–2020 |
| Relative humidity | % | 55–70 (mean 65) | 60–75 (mean 70) | 100 | — | — | Min mid-afternoon, max pre-dawn | NOAA KBOS |
| Dew point | °F | 15–25 | 60–68 | 73 (1% MCWB) | — | — | — | ASHRAE 169 |
| Wet bulb | °F | 20–30 | 65–72 | 75 (0.4% WB design) | — | — | — | ASHRAE 169 |
| Wind speed | mph | 10–18 (gusts 25–40) | 8–14 (gusts 20–30) | 50 (30-yr return gust for roof eq.) | — | 60 (damage) | Gustier afternoon | NOAA KBOS |
| Wind direction | deg | WNW dominant (270–315°) | SW dominant (200–240°) | — | — | — | — | NOAA KBOS |
| Solar irradiance (GHI) | W/m² | 0–500 (short days) | 0–900 (midday clear) | 1000 (clear noon June) | — | — | 0 at night, peak solar noon | NREL NSRDB KBOS |
| Barometric pressure | inHg | 29.5–30.5 (larger swings w/ storms) | 29.8–30.2 | 28.5 (storm low) to 31.0 (high) | 28.0 | 31.5 | — | NOAA KBOS |
| Rainfall rate | in/hr | 0–0.2 (snow equiv) | 0–2 (thunderstorms) | 3 (100-yr 1-hr) | — | — | — | NWS BOX |

---

## 13. Demand / Power Meter (Modbus, sub-meter, typical Veris H8035 / Shark 200)

Same signal types as Electric Meter above, but scoped to a sub-panel (e.g. HVAC panel,
lighting panel, tenant meter). Scale currents 50–250 A rather than 800 A.

| Point | Units | Winter typical | Summer typical | Peak design | Alarm | Notes |
|---|---|---|---|---|---|---|
| V L-L | V | 476–486 | 474–484 | 480 | ±5% | — |
| V L-N | V | 275–281 | 273–279 | 277 | ±5% | — |
| I per phase | A | 30–120 | 80–220 | 250 (CT size) | >225 | Peak afternoon summer |
| kW | kW | 25–90 | 70–180 | 200 | — | — |
| kVAR | kVAR | 5–20 | 15–50 | 60 | — | — |
| kVA | kVA | 26–92 | 72–186 | 210 | — | — |
| PF | — | 0.90–0.98 | 0.88–0.95 | — | <0.85 | — |
| kWh | kWh | monotonic | monotonic | — | — | Logs at 15 min |
| THD-I | % | 3–8 | 3–8 | 8 (IEEE 519) | >15 | Higher with VFDs |

---

## 14. Exhaust Fan — VFD-Driven (5 HP, bathroom / kitchen / garage exhaust)

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Output frequency | Hz | 30–50 | 40–60 | 60 | — | — | Ramp with occupancy | ABB/Danfoss VFD docs |
| Motor speed | RPM | 900–1500 (4-pole @ 30–50 Hz) | 1200–1800 | 1800 | — | — | — | — |
| Output current | A | 3–6 | 4–7 | 7.5 (FLA 5 HP @ 480V) | — | 8 (overcurrent) | — | NEMA MG-1 |
| Output voltage | V | 240–400 (V/Hz ratio) | 320–460 | 460 | — | — | — | — |
| Input power (kW) | kW | 1.5–3 | 2–3.5 | 3.7 (5 HP) | — | 4.5 (overloaded) | — | — |
| Runtime hours | hr | monotonic | monotonic | — | — | — | Accumulates | — |
| Status | enum | Running / Stopped / Fault | — | — | — | — | — | — |
| Fault code | int | 0 | 0 | — | — | nonzero | — | VFD-specific |

---

## 15. Pump — Hydronic Circulator (10 HP, CHW or HW secondary, VFD)

| Point | Units | Winter typical | Summer typical | Peak design | Low alarm | High alarm | Time-of-day | Source |
|---|---|---|---|---|---|---|---|---|
| Speed | % | 40–90 (HW) / 0 (CHW off) | 50–90 (CHW) / 0 (HW off) | 100 | — | 100% sustained | Tracks DP reset | ASHRAE 90.1 |
| Power (kW) | kW | 1.5–6 (cubic law with speed) | 2–6.5 | 7.5 (10 HP) | — | 8.5 (bearing/coupling) | — | Affinity laws |
| Current | A | 3–9 | 4–10 | 14 (FLA 10 HP @ 480V) | — | 15 | — | NEC Table 430.250 |
| Flow (GPM) | GPM | 200–600 | 300–650 | 720 | 100 (dead-head) | — | — | Bell & Gossett curves |
| Discharge pressure | PSI | 20–35 | 25–40 | 45 (pump dead-head) | 10 (suction loss) | 55 (closed valve) | — | — |
| Differential pressure | PSI | 8–20 | 10–25 | 25 (design) | — | 30 | — | — |
| Status | bool | Running | Running | — | Off w/cmd on | — | — | — |

---

## 16. Sensor Rack — Temp / RH / CO2 / Pressure (Modbus, Veris or Johnson)

Typical: drop-ceiling zone sensor or duct-mounted Johnson NS series. Simulator should
correlate these with upstream VAV / AHU signals (don't randomize independently).

| Point | Units | Winter typical | Summer typical | Peak design | Alarm | Time-of-day | Notes |
|---|---|---|---|---|---|---|---|
| Space temp | °F | 68–73 | 72–76 | 70–75 setpoint | <60 / >85 | Setback nights | — |
| Space RH | % | 20–35 (low due to winter heating) | 45–60 | 20–60 comfort | <15 / >70 | — | ASHRAE 55 |
| Space CO2 | ppm | 400 (unocc) → 800–1000 (peak) | same | <1100 ASHRAE 62.1 | >1200 | Rises by 11 a.m., decays 5–7 p.m. | DCV trigger |
| Duct/plenum pressure | inWC | 0.05–0.15 (space) / 1.0–1.5 (duct) | same | 0.05 space / 1.5 duct | — | — | — |
| Outside air pressure ref | inWC | 0 (reference) | 0 | 0 | — | — | — |

---

## 17. VFD — Variable Frequency Drive (generic, driving 10 HP motor)

Same signal set as exhaust fan VFD; this is the generic device class covering fan/pump
VFDs where the downstream load is unspecified.

| Point | Units | Typical | Peak | Alarm | Notes |
|---|---|---|---|---|---|
| Output frequency | Hz | 30–55 | 60 | — | Cubic-law with load |
| Output current | A | 5–12 | 14 (FLA 10 HP) | 16 (OC trip) | — |
| Output voltage | V | 240–440 | 460 | — | Tracks V/Hz |
| DC bus voltage | V | 640–680 | 720 | <580 (undervolt) / >780 (overvolt) | Capacitor health |
| Motor temp | °F | 140–190 | 220 (NEMA Class F) | >230 (trip) | NEMA MG-1 Class F 311°F max |
| Heatsink temp | °F | 100–150 | 180 | 195 (VFD trip) | — |
| Runtime hours | hr | monotonic | — | — | — |
| Fault code | int | 0 | — | nonzero | — |
| Status | enum | Running / Stopped / Fault | — | — | — |

---

## 18. Fire Alarm Panel (Modbus / BACnet, read-only flags)

Minimal per instructions.

| Point | Units | Normal | Trouble | Alarm | Notes |
|---|---|---|---|---|---|
| Trouble flag | bool | false | true | — | Power/battery/ground fault — latches |
| Alarm flag | bool | false | — | true | Smoke/heat/pull — latches |
| Supervisory flag | bool | false | true | — | Sprinkler valve, tamper |
| AC power OK | bool | true | false | — | On utility loss |
| Battery OK | bool | true | false | — | Secondary battery check |
| Silence / acknowledged | bool | false | true (after ack) | — | — |

---

## Time-of-day patterns summary (apply across equipment)

- **OAT**: sinusoid with diurnal amplitude ~15°F summer / ~12°F winter; min at 5–6 a.m., max 2–4 p.m. Seasonal sinusoid with annual mean 51°F, amplitude ~22°F.
- **Occupancy**: 0.05 overnight → ramp to 0.95 at 9 a.m. → hold 9 a.m.–5 p.m. → decay to 0.1 by 8 p.m. Weekend 0.05–0.3.
- **Lighting**: 0.05 unocc → 0.9 occupied, daylight-harvested perimeter zones 0.3–0.7.
- **Plug load**: 0.30 unocc (always-on equipment) → 0.85 occupied.
- **AM warmup**: boilers/reheat ramp hard 5 a.m.–8 a.m. in winter; setback catch-up.
- **Afternoon cooling peak**: chiller, cooling tower, electric meter, RTU compressors all peak 2–4 p.m. in summer.
- **Shoulder seasons (Apr, Oct)**: wide diurnal swing — AHU economizer on 70% of hours, chiller off but CHW pumps may purge, boiler on only at night.

## Alarm semantics (simulator should categorize)

- **Normal**: within low/high alarm.
- **Out-of-range (low/high)**: past alarm threshold but within sensor range; amber.
- **In-alarm**: `eventState` in `{low-limit, high-limit, fault}`, `statusFlags.in-alarm = true`; red.
- **Freezestat / trip**: MAT <38°F, CHWS <38°F, tank temp >210°F, compressor suction <15°F — immediate latched fault; red persistent.

## Gaps and judgment calls

- **Boston-specific real trend data is thin publicly**. Mass Save case studies publish
  kWh/sqft EUIs but almost no hour-by-hour telemetry. I used DOE medium-office prototype
  as proxy — it's calibrated nationally, not Boston-specifically, but within ±15%.
- **Cold-climate heat pump derate curves** are vendor-specific. NEEP ccASHP spec list has
  reliable data for 10 models but simulator would need to pick one; I gave generic bounds.
- **Boiler OAR curves vary wildly** by installer preference. The 180°F @ 0°F / 120°F @ 60°F
  linear reset is the Tekmar/Heat-Timer default; a facility with radiators will use steeper
  (200°F @ 0°F), a radiant floor will use shallower (110°F @ 0°F). Pick one for simulator.
- **kVAR / PF** are sensitive to motor load mix. Assumed ~30% motor / 70% non-motor (lighting,
  plug) typical for medium office; heavy-motor buildings (industrial, big pump loads) run
  lower PF (0.80–0.88) and need capacitor correction.
- **THD** varies with VFD count. Values given assume moderate VFD penetration (~30% of load).
  All-VFD retrofits without line reactors can hit 15–25% THD-I.
- **Weather station solar** — used NSRDB Boston for GHI bounds but no direct-normal /
  diffuse-horizontal breakdown; simulator may want to add cloud-cover stochastic modulator.
- **CO2 ramp rate** depends on volume / ACH; 450 ppm/hr rise at design occupancy is typical
  for a meeting room (volume-limited) but office bullpens see 100–150 ppm/hr. I gave 400→900
  over 2 hr as mid-case.
- **Chiller IPLV vs. IEER**: IPLV is the AHRI 550/590 rating at AHRI-weighted part-loads; real
  operation often runs lower PLR than IPLV assumes in Boston (short cooling season, mild
  summer). Expect simulator to spend more hours at 30–50% PLR than IPLV would suggest.

## Primary sources

1. ASHRAE Standard 169-2021 *Climatic Data for Building Design Standards* — Boston Logan
   winter 99.6% = 0°F, summer 1% = 91°F / 73°F MCWB.
2. ASHRAE Guideline 36-2021 *High-Performance Sequences of Operation for HVAC Systems* —
   VAV zone control, SAT reset (55°F min, 68°F max OAT change-point), duct SP reset,
   multi-zone AHU sequences.
3. ASHRAE Standard 90.1-2022 — CHW reset, CW temperature setpoints, 15°F ΔT rule, pump
   power limits, minimum chiller efficiency path A/B.
4. ASHRAE Standard 62.1-2022 — office ventilation 5 CFM/person + 0.06 CFM/sqft, CO2 DCV
   trigger 1100 ppm.
5. ASHRAE Standard 55-2020 — comfort range 68–76°F, 30–60% RH.
6. ASHRAE Standard 188-2018 / Guideline 12 — DHW legionella ≥140°F tank.
7. DOE Commercial Reference Buildings *Medium Office* prototype (EnergyPlus IDF) —
   53,628 sqft, 3 floors, 15 thermal zones, occupancy/lighting/plug schedules, equipment
   sizing. Downloaded from `https://www.energy.gov/eere/buildings/commercial-reference-buildings`
   and OpenEI dataset 389d1.
7. NOAA NCEI 1991–2020 Climate Normals, Boston Logan (KBOS / WBAN 14739) — monthly means,
   wind, HDD/CDD.
8. NREL NSRDB — Boston TMY3 solar irradiance.
9. NEEP Cold-Climate Air Source Heat Pump Specification — cold-climate capacity/COP curves.
10. Trane *Chiller Plant Design* application manual (water-cti.com/pdf/ASHRAE_ChillerPlantDesign.pdf)
    — CW/CHW temperatures, chiller kW/ton.
11. ANSI C84.1-2020 — voltage tolerance bands (±5% normal, ±10% extreme).
12. NEMA MG-1 — motor voltage imbalance derate, insulation class temps.
13. IEEE 519-2022 — THD limits.
14. Manufacturer IOMs — Trane RTHF/CVHF chillers, BAC/Marley cooling towers, Viessmann /
    Lochinvar condensing boilers, Carrier Weathermaker RTU, Bell & Gossett hydronic pumps,
    ABB/Danfoss VFDs, Veris H8035 meter.
15. Deppmann *Monday Morning Minutes* and HPAC Magazine — real-world OAR curve tuning for
    hydronic condensing boilers.

