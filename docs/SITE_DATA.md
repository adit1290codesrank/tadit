# Website data contract

The website never runs the models. The pipeline runs on our server, and `scripts/export_site.py` turns its
outputs into static files. The site (Cloudflare Pages / Vercel) only reads those files.

```bash
python scripts/export_site.py --results results --figures figures --cases site/cases.json \
    --boundary data/boundaries/india_states.geojson --out site/public/data
```

- **Dependencies:** numpy + pyproj only; no GPU.
- **Size:** re-running replaces `forecasts/`. The frozen results export to ~6.5 MB; each forecast with maps adds ~1–2 MB.
- **Where to run it:** on the server, where the `.npz` map files from `nowcast.india.run` exist.
  - Without them (e.g. from git alone), the forecasts still export with their hourly risk, but with no map overlays (`has_maps: false`).

## Files

```
data/
  manifest.json                  entry point: lists everything below
  scores.json                    test-set skill (scorecard, per-10-min curves, ablations)
  forecasts/<id>.json            one India forecast (id = <City>_<YYYYmmddTHHMM> in UTC)
  forecasts/<id>_insat.json      the same forecast run on INSAT (primary on the site)
  forecasts/<id>/hour<h>.png     lightning probability map for lead hour h (seamless tier1/tier2)
  forecasts/<id>/lght_<mmm>.png  tier-1 lightning probability, lead mmm minutes (010 ... 180)
  forecasts/<id>/vil_<mmm>.png   tier-1 storm intensity (VIL) at the same step
  figures/*.png                  slide figures (optional)
  india_boundary.geojson         only if --boundary is given (must be Survey of India)
```

All paths inside the JSONs are relative to `data/`.

## `manifest.json`

| key | meaning |
|---|---|
| `generated_utc` | export time |
| `honest_label` | **must be shown on every forecast screen** |
| `switch_hour` | tier 1 is used up to and including this lead hour; tier 2 after it |
| `model.tier1` / `model.tier2` | checkpoint step / samples / epoch |
| `forecasts[]` | `id, city, lat, lon, title, kind ("case" or "run"), issue_ist, issue_utc, peak_risk, has_maps, file`, newest first |
| `figures[]` | slide figure paths |
| `boundary` | `"india_boundary.geojson"` or `null` |

## `forecasts/<id>.json`

**Metadata**

| key | meaning |
|---|---|
| `title`, `description`, `kind` | from `site/cases.json` if given (otherwise `"<City>, <date time> IST"`) |
| `issue_ist`, `issue_utc`, `valid_until_ist` | times as `YYYY-MM-DDTHH:MM` (IST = UTC + 5:30) |
| `lat`, `lon` | the city |
| `tile.corners` | `[[lon, lat] × 4]` in **MapLibre image-source order**: top-left, top-right, bottom-right, bottom-left. Use these to place every PNG of this forecast. Tiles are 384 km. |
| `peak_risk` | highest risk over the hours |
| `honest_label` | show it |

**`hours[]`**, one entry per lead hour:
- `lead_hour`, and `window_ist` (`[start, end]`)
- `source`: `tier1` or `tier2`
- `p_location` (at the city) and `p_tile_max`
- `risk`: `LOW` / `MODERATE` / `HIGH`, with thresholds 0.2 and 0.5 at the city
- `advice`: plain-language action for that risk

**`inputs`**: `satellite`, `radar`, `lightning`, `nwp`, each with a `status` and details.
- `status` is one of `live`, `approximate`, `partial` or `missing`.
- **Show these as badges.** Today's India runs are satellite (GK2A) + NWP (GFS) live, with radar and lightning missing.

**`storm_check`** (optional): the storm-location check against GK2A cold cloud tops.
- Label it exactly as its `what` text says. **It's a storm proxy, not lightning verification.**

**`overlays`**
- `hourly{"1": png, ...}`: one map per lead hour.
- `steps[]`: `{minutes, time_ist, p_location, lightning, vil}`, 18 steps × 10 min for the first 3 h. This drives the animation and the 10-min risk curve.

## `scores.json`

| key | meaning |
|---|---|
| `scorecard[]` | `{lead_hour, tier1, tier2, persistence, hrrr_lightning, hrrr_reflectivity}`: the headline table |
| `switch_hour` | same as in the manifest |
| `metric_note` | show under every score chart (what CSI is, which data, which years) |
| `series.<name>` | `label`, `group`, `csi_by_hour`, and for tier-1 runs also `lead_minutes`, `lightning_csi_per_step`, `vil_csi_per_step`, `summary`. Names are the result files. |

Series groups:
- `tier1` (`full`), `tier2` (`ext`), `baseline` (`persistence`)
- `india_mode` (`full_india_mode`), `tier2_india_mode`
- `ablation`: `no_ir`, `no_lght`, `no_nwp`, `no_radar`, `no_radar_no_ir`, `sat_nwp_only`

## Map overlays

- Transparent RGBA PNGs, already north-up. The exporter flips the model's south-up grids; don't flip them again.
- **Lightning probability ramp:** transparent below 0.05; 0.05 → 0.8 goes pale yellow, orange, red, deep red, purple.
- **VIL ramp:** transparent below 16; greens, then orange, then brown, at the SEVIR thresholds 16, 74, 133, 160, 181, 219.

Put the same ramps in the map legend.

## Rules the site must keep

1. Show `honest_label` on every forecast view, and `metric_note` under every score chart.
2. Times are in IST, always with the issue time and the valid-until time.
3. Show the input badges from `inputs.*.status`. A missing source is shown as missing, never hidden.
4. For India maps, use Survey of India boundaries. Never use Natural Earth or default OSM/Mapbox country borders.
5. Label `storm_check` as a satellite storm proxy, not lightning.
