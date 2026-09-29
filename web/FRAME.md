# FRAME: site wireframe (structure, not visuals)

This is the structural spec for the website. It fixes **what exists, where it sits, what it reads and how it
behaves**. Everything visual is deliberately left open and belongs to the design owner: colour, type, motion,
and how storms are drawn.

- **Content inventory and numbers:** `web/BRIEF.md`.
- **Data schema:** `docs/SITE_DATA.md`. Data paths below are relative to `data/`.
- **Slot names** are written as `Slot`. Use them in code and in discussion.

---

## 1. Decisions (29 Sep 2026)

| Topic | Decision |
|---|---|
| Shape | **Product / service, demo-first.** No story page, no "how it works", no team page. |
| Scores | **Not on the site.** Scorecard, ablations and India mode live in the slides. So the `metric_note` rule doesn't apply. |
| Disclosures | `manifest.honest_label` is **one quiet line, always visible**. Everything else (sources, limits, the proxy note, provenance) is in the **ⓘ About drawer**, opened on demand. |
| Past runs | **As if live, with an `archived` badge.** Reached through a **run picker** showing the issue time in IST. |
| Density | Show one level at a time and use tabs. Someone new to the job must understand every screen without help. |
| Canvas | A map in v1, maybe a globe later. **The slot is fixed; the look is not.** Keep room for creative depictions. |
| Intensity | **Continuous.** How strongly a region is drawn follows its forecast values; nothing is on/off. A calm run (Delhi) simply looks calm, with no special all-clear screen. |
| Satellite | **INSAT-3DR is primary; GK2A is the cross-check.** |
| 6 h seam | **Visible but quiet.** One timeline with dense ticks for 0–3 h, sparse ticks for 3–6 h and a small divider. Playback goes from 10-min steps to hourly. |
| Device | Desktop first. Phones get a stacked fallback (§9). |
| Onboarding | A one-line plain-English hint on each panel, plus an always-on legend. No walkthrough. |
| Language | English only. The top bar keeps an empty slot for a language switch. |
| Look (29 Sep) | `web/DESIGN.md`, applied strictly. Where it is silent, only the data ramps add colour. |
| Build (29 Sep) | Vite + React + TS + `maplibre-gl` in `web/`. `publicDir` is `../site/public`, so the export ships at `/data`. |
| Base map (29 Sep) | None. India is drawn only from the SoI states: `canvas-soft` fill, `canvas-mid` hairlines. |
| Intensity look (29 Sep) | Glow + slow pulse at L0: colour from the lightning ramp at `p_tile_max`, with size, opacity and pulse rising with it. At L1 the glow stays inside the tile and gives way to the overlay where maps exist. |
| INSAT endpoint (29 Sep) | The site defines it (§7) and main fills it. |

## 2. Scope change from BRIEF

| BRIEF section | Where it goes |
|---|---|
| §4.2 India forecast viewer | **The whole product** (§3–§7 here) |
| §4.3 cases | The **runs** in the run picker. No stories: the `description` text goes in the About drawer. |
| §4.8 data readiness, §4.9 limits | **About drawer** |
| §4.1 hero, §4.4 scorecard, §4.5 ablations, §4.6 India mode, §4.7 how it works, §4.10 team | **Not on the site.** A repo link plus a one-line credit sit in the drawer. |

## 3. Terms and disclosure levels

**Terms:**
- A **run** is every forecast issued at one time: `manifest.forecasts[]` grouped by `issue_utc`.
- A **region** is one forecast in that run: one city tile of 384 km, one `forecasts/<id>.json`.
- Today every run holds exactly one region. The structure must not assume that (see §8, multi-region).

**Levels.** Each level adds one layer and never replaces the one before it.

| Level | The user sees | Got there by |
|---|---|---|
| **L0 Run overview** | India on the `Canvas`, every region of the run drawn at its intensity, the `TimeBar`, the `Legend` | Page load (newest run) or `RunPicker` |
| **L1 Region** | `RegionPanel` slides in: the region header and six `HourCards`. The canvas focuses on the tile. | Click a region on the canvas, or its label |
| **L2 Detail** | `DetailTabs` in the panel: `Timeline` · `Risk curve` · `Inputs` · `Storm check` | "More detail" in the panel, or a tab |
| **Drawer** | `AboutDrawer` over everything | ⓘ in `TopBar` or `StatusStrip`, at any level |

Esc or ← goes back one level. Switching runs always returns to L0.

## 4. Desktop layout

### L0: run overview
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TopBar  [brand]   Issued 02 Sep 2023, 13:30 IST ▾  [archived]                │
│                   Valid until 19:30 IST                     [lang·] [ⓘ]      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Canvas (full width, full height)                            ┌────────────┐  │
│                                                              │ Legend     │  │
│           India, SoI state boundaries                        │ lightning  │  │
│                                                              │ chance ramp│  │
│                            ◎ Bhubaneswar                     └────────────┘  │
│                            (drawn by intensity)                              │
│                                                                              │
│   hint: "Coloured areas show where lightning is likely in the next 6 hours.  │
│          Click one for the hour-by-hour forecast."                           │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ TimeBar  ▶  |·|·|·|·|·|·|·|·|·|·|·|·|·|·|·|·|·|  ¦   |    |    |             │
│             0 h        1 h        2 h        3 h ¦  4 h  5 h  6 h            │
│             13:30                          16:30 ¦ outlook                   │
├──────────────────────────────────────────────────────────────────────────────┤
│ StatusStrip  Trained on US GLM lightning, adapted to INSAT/GFS, not yet   [ⓘ]│
│              verified against Indian lightning observations                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### L1: region selected
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TopBar (unchanged)                                                           │
├───────────────────────────────────────────────────┬──────────────────────────┤
│ Canvas (focused on the 384 km tile)               │ RegionPanel          [×] │
│                                                   │ Bhubaneswar              │
│   ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐                          │ Odisha lightning outbrk  │
│     tile overlay at t                             │ Peak: HIGH               │
│   │        ◎ city       │                         │ hint: "Chance of light-  │
│                                                   │  ning near the city,     │
│   └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘            [Legend]     │  each hour"              │
│                                                   │ ┌──────────────────────┐ │
│                                                   │ │ HourCard 1 13:30–14:30│ │
│                                                   │ │ MOD  0.47   advice…   │ │
│                                                   │ ├──────────────────────┤ │
│                                                   │ │ HourCard 2 … HIGH     │ │
│                                                   │ │ HourCard 3 … MOD      │ │
│                                                   │ ├ ─ ─ outlook ─ ─ ─ ─ ─┤ │
│                                                   │ │ HourCard 4–6 (tier 2) │ │
│                                                   │ └──────────────────────┘ │
│                                                   │ [ More detail → ]        │
├───────────────────────────────────────────────────┴──────────────────────────┤
│ TimeBar (unchanged; the cursor highlights the matching HourCard)             │
├──────────────────────────────────────────────────────────────────────────────┤
│ StatusStrip                                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### L2: detail tabs (they replace the card list; the cards collapse to a compact strip)
```
                                                    ┌──────────────────────────┐
                                                    │ RegionPanel          [←] │
                                                    │ Bhubaneswar · HIGH       │
                                                    │ ▁▃█▅▄▄  (HourStrip)      │
                                                    │ ┌Timeline┬Risk curve┬    │
                                                    │ │Inputs┬Storm check┐     │
                                                    │ ├──────────────────────┤ │
                                                    │ │ tab body             │ │
                                                    │ │ + one-line hint      │ │
                                                    │ └──────────────────────┘ │
                                                    └──────────────────────────┘
```

## 5. Slots

Each slot lists what it reads, its hint text, and how it behaves at each level. The hints are draft copy; the design owner may reword them, but every panel keeps one.

### `TopBar`
- **Brand:** name and mark are still to be decided.
- **`RunPicker`:**
  - The label is `Issued <issue_ist as "DD Mon YYYY, HH:MM"> IST ▾`, with `Valid until <valid_until_ist HH:MM> IST` beneath it.
  - The list comes from `manifest.forecasts[]` grouped by `issue_utc`, newest first. Each row shows the date and time, the region names, and the highest `peak_risk` in the run as a chip.
  - Hidden runs are already excluded by the export.
- **`archived` badge:** shown when every forecast in the run has `kind == "case"`. That covers every run today. A future live run (`kind: "run"`) drops the badge, and nothing else changes.
- **Language slot:** empty, but its space is kept.
- **ⓘ:** opens `AboutDrawer`.

### `Canvas`
The contract is in §6.
- **L0:** India fitted to the viewport. Every region of the run is drawn from its intensity at the cursor `t`.
- **L1/L2:** the canvas fits to the selected `tile.corners`. It draws the overlay for `t` (§7), the city marker and the tile outline.
- **Hint (L0):** see the wireframe.

### `Legend`
- **Always:** the lightning-chance ramp, transparent below 0.05, running to 0.8.
- **VIL ramp:** only while `layer == "vil"`. It replaces the lightning ramp.
- **Hint:** "Chance of lightning in each 16 km square", or "Storm intensity" for VIL.

### `TimeBar`
- **Positions:** `t` ∈ {10, 20, … 180} minutes (tier 1), then {240, 300, 360} (tier 2).
  - Tick density follows the data: 18 ticks, then 3.
  - A quiet divider sits at 3 h, labelled "outlook".
  - Time labels are in IST (`issue_ist` + t).
- **Play:** steps through the positions at a constant wall-clock rate per position, so the first 3 h play slowly (10-min steps) and the outlook quickly. Pause at the end.
- **Honest data only:**
  - positions come only from `overlays.steps[].minutes` and the `hours[].lead_hour` values beyond the last step;
  - if `steps` is empty, the bar shows hourly positions only.
- **Hint:** "Drag to see how the forecast changes. Finer detail for the first 3 hours."

### `RegionPanel`
- **Header:** `city`, `title`, and the `peak_risk` chip. `description` doesn't go here; it lives in the drawer.
- **`HourCards`**, one per `hours[]` entry:
  - `window_ist` as a time range;
  - `risk` label;
  - `p_location` as a percentage (e.g. "47 %"), with the raw value kept for detail views;
  - the `advice` sentence;
  - a small `source` tag. Tier 2 cards sit below an "outlook" divider (the same seam as the TimeBar).
  - `p_tile_max` goes in a secondary line, "Highest nearby: 61 %".
- **Cursor sync:** the card for `ceil(t/60)` is highlighted, and clicking a card moves the cursor to its hour.
- **Hint:** "Chance of lightning near the city, each hour. LOW under 20 %, HIGH over 50 %."
- **"More detail →"** goes to L2.

### `DetailTabs` (L2)
| Tab | Reads | Body | Hint |
|---|---|---|---|
| `Timeline` | `overlays.steps[]`, `overlays.hourly` | The layer switch (Lightning / Storm intensity) and the step `time_ist`. Driving the canvas animation is the TimeBar's job, not this tab's. VIL is disabled beyond 3 h, with the reason shown. | "Watch the storm move. 'Storm intensity' shows how strong the storm is." |
| `Risk curve` | `steps[].p_location` (10-min, 0–3 h) and `hours[].p_location` (hourly, 4–6 h) | A line with bands at 0.2 and 0.5, the cursor marker, and the seam at 3 h | "How the chance of lightning at the city changes, minute by minute, then hour by hour." |
| `Inputs` | `inputs.{satellite,radar,lightning,nwp}` | Four badges, each showing its `status` and `source`, plus the satellite scan times and the NWP runs. `missing` looks normal (see §8). The cross-check line reads "GK2A: cross-check" once INSAT is primary. | "What went into this forecast. Radar and lightning feeds for India are not connected yet." |
| `Storm check` | `storm_check.what`, `.hours[]` (1–3) | POD / FAR / CSI per hour and `deep_cells`, titled with `storm_check.what`. Hidden if absent. | "Did storms show up on satellite where we forecast them? This is a check on storm location, not on lightning." |

### `StatusStrip`
- Shows `manifest.honest_label` verbatim, never the per-forecast `honest_label`, which is a longer provenance sentence (it goes in the drawer).
- **Style:** quiet (muted and small), but always visible on every level and not dismissible.
- Also holds ⓘ.

### `AboutDrawer`
Its sections open like an accordion, closed by default except the first.

1. **About this forecast** (per run):
   - `description`;
   - per-forecast `honest_label` (the provenance sentence);
   - `issue_utc`;
   - `model_inputs_used`;
   - `manifest.model` (checkpoint facts).
2. **Data sources:** the BRIEF §4.8 table as prose or a list.
3. **Limits:** BRIEF §4.9.
4. **About the storm check:** it is a proxy and why.
5. **Map boundaries:** "Survey of India", or "not shown" when `boundary == null`.
6. **Credits:** SIH26072 (MoES / IMD) and the repo link.

## 6. `Canvas` contract

The rest of the app talks to the canvas **only** through this, so a globe or any other depiction can replace v1 without changing any other slot.

```ts
type Region = {
  id: string; city: string; lat: number; lon: number;
  corners: [number, number][];            // tile.corners (MapLibre order)
  intensity: (t: number) => number;       // 0..1, continuous; see below
  overlay: (t: number, layer: "lightning" | "vil") => string | null;  // PNG url, §7
};
type CanvasProps = {
  regions: Region[];                      // every region in the current run
  selected: string | null;                // region id, or null at L0
  t: number;                              // minutes from issue
  layer: "lightning" | "vil";
  boundary: GeoJSON | null;               // SoI states; null → draw no borders
  onSelectRegion(id: string): void;
  onHover(id: string | null): void;
};
```

- **`intensity(t)`** is `hours[ceil(t/60)].p_tile_max`: the strongest signal anywhere in the tile, per hour.
  - It is the same measure in both tiers. The steps only carry `p_location` (the city), so they can't be used here.
  - It drives how strongly a region is drawn at L0 (glow, pulse, height, whatever the design chooses). The gradient stays continuous: Delhi's tile max stays at or below 0.234 and looks faint, while Kolkata at 0.695 is loud.
  - The fine spatial gradient inside the tile comes from the overlay PNG itself.
- **v1:** a flat MapLibre map.
  - Overlays are `image` sources placed at `corners`.
  - The boundary is a GeoJSON line layer.
  - The basemap has **no country or state borders** of its own: a plain land/sea base or none.
- **Later:** the MapLibre v5 globe projection works with the same sources and layers. Per-state depiction is possible because the boundary file is state-level ("Odisha: high").

## 7. Shared state

```
{ runKey, regionId | null, level: 0|1|2, tab, t, layer, playing, drawerOpen }
```
- **URL hash** holds `run`, `r`, `tab`, `t` and `layer`, so any view can be shared.
- **Initial `t`:** 10, the first step (or 60 if there are no steps).

**`t` → overlay:**
- if `t ≤ 180` and a step with `minutes == t` exists, use `steps[t].lightning` or `.vil`;
- otherwise use `overlays.hourly[ceil(t/60)]` (lightning only);
- if neither exists, show `null` and the §8 note.

**Resets:**
- a run change sets `regionId = null`, `level = 0`, `t` = initial, and `layer = "lightning"`;
- a region change keeps `t` and `layer`.

**Satellite variant (the INSAT endpoint):**
- **Files:** INSAT runs are exported as `forecasts/<City>_<YYYYmmddTHHMM>_insat.json`, with the same schema and a normal `manifest.forecasts[]` entry.
- **Pairing:** entries with the same `city` and `issue_utc` form one region.
  - The `_insat` one is primary.
  - The other one feeds the `Inputs` cross-check: hourly p at the city, side by side.
- **No `_insat` entry:** GK2A is primary, and its `inputs.satellite.source` says it is a stand-in.
- **Title:** if the INSAT entry only has the auto title (`… IST`), the GK2A entry's title is used.
- **Region id** in the state and URL is the `city`, so links survive the INSAT rollout.

## 8. Edge states

| Condition | Where | Behaviour |
|---|---|---|
| `has_maps: false` | Canvas, Timeline | The region is drawn as a marker only, still sized or tinted by `intensity`. In place of the overlay: "Map not available for this forecast; hourly risk below." The TimeBar falls back to hourly positions. |
| `boundary: null` | Canvas, drawer | Draw **no** borders. The drawer says so. |
| No `steps` | TimeBar, Risk curve | Hourly positions only. The curve uses hourly points. |
| `t` > 180 with `layer = vil` | Timeline, Legend | Switch to lightning and say "Storm intensity is only available for the first 3 hours". |
| Input `missing` / `partial` / `approximate` | Inputs | Neutral styling, not error red. The status word is always written out. |
| Storm check NaN / `deep_cells == 0` | Storm check | "No storm clouds seen on satellite", never 0 or NaN. |
| No `storm_check` | DetailTabs | Hide the tab. |
| INSAT variant absent | Inputs, drawer | GK2A is primary and the badge says so. No cross-check line. |
| `hours[]` shorter than 6 | HourCards, TimeBar | Render what exists. No empty or zero cards. |
| Run with one region (today) | L0 | Still start at L0. Regions are clickable, and nothing auto-opens. |
| Run with many regions (future) | L0 | All drawn, and `RunPicker` rows list the regions. No other change. |
| Loading | Every panel | Skeletons shaped like the final content. The StatusStrip shows immediately, since the label is static. |
| Fetch error | Panel or page | Say what failed, in plain words, with retry. Never show stale data from another run. |

## 9. Phone fallback (under ~768 px)
- **`TopBar`:** a single line showing the `RunPicker` and ⓘ. Valid-until wraps under it.
- **`Canvas`:** full width, about 60 % of the height.
- **`TimeBar`:** directly under the canvas.
- **`RegionPanel`:** a bottom sheet that is peek at L0 (just the run's regions), half-open at L1 and full at L2. The tabs become a horizontal scroll.
- **`AboutDrawer`:** full-screen.
- **`StatusStrip`:** stays pinned at the bottom, wrapping to two lines if needed.

## 10. Rules checklist

| Rule (BRIEF §2) | Kept by |
|---|---|
| Honest label on every forecast view | `StatusStrip`, on every level, not dismissible |
| `metric_note` under score charts | n/a: there are no score charts |
| IST, issue time and valid-until | `TopBar` / `RunPicker`, `HourCards`, `TimeBar` labels |
| Input badges, missing never hidden | `Inputs` tab, §8 styling |
| Survey of India boundaries only | `Canvas` (the boundary prop only; basemap without borders), §8 |
| Storm check labelled as a proxy | `Storm check` tab title from `storm_check.what`, plus its hint |
| Numbers as measured, no hidden bad case | Every run from the export is in the `RunPicker`, including the partial miss. Percentages round `p` to whole numbers only for display, and the raw value sits in the tooltip or the detail view. |

## 11. Parked (room kept, not built)
- A globe renderer and creative per-region or per-state depiction (§6).
- A language switch (slot in `TopBar`).
- Live runs with many regions (`kind: "run"`, §8).
- "Forecast my city": this would need a server job; out of scope (BRIEF §6).

## 12. Needed from others
- **Main (pipeline owner):**
  - **INSAT endpoint (§7).** In `export_site.py`, also read `results/india_insat/*.json` and write each one with `_insat` appended to the stem, along with its `_gk2a_check.json`.
    - The web check did exactly this on scratch copies, and it works.
  - **`site/cases.json`:**
    - add `_insat` keys whose descriptions match INSAT's numbers; today's descriptions quote GK2A (e.g. Odisha "CSI 0.43");
    - drop the internal note "Add the source for strike and casualty numbers…", which would show on the site.
  - **`NaN` in exported JSON.** The Delhi storm check writes Python `NaN`, which is invalid JSON. The site tolerates it, but `json.dump(..., allow_nan=False)` after mapping NaN → `null` is cleaner.
  - Run the export with `--boundary data/boundaries/india_states.geojson`. SITE_DATA.md still says "Bhuvan".
  - **STEPS.md 12b deploy** becomes `cd web && npm ci && npm run build && npx wrangler pages deploy dist`.
- **Design owner:** the brand name. "Nowcast" is a placeholder (`web/src/TopBar.tsx` `BRAND`).
- **Team:** the credit line, and whether the repo link in the drawer should be public.
