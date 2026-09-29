# Deploying the website

How a forecast gets from the model to a public URL. The data format the site reads is in `docs/SITE_DATA.md`. The site itself is in `web/` (`web/README.md` covers local development).

## Why the site is static

Cloudflare Pages and Vercel have no GPUs, and neither can run our model:
- Cloudflare's Python runs on Pyodide, which has no torch.
- A Vercel function is capped at about 250 MB unzipped, and torch alone is larger than that.
- Both also limit how long a request can run. One forecast spends minutes downloading satellite scans and GFS fields before the model even starts.

We don't need them to run it. A forecast depends on two things: a place and an issue time. `nowcast.india.run` fetches the satellite scans and GFS fields for that place and time, runs both tiers, and writes the result. Once written, the result never changes. So the site serves results that were computed earlier, the way a newspaper prints a forecast made that morning.

That settles what can be computed ahead of time:
- **Past events (the case studies):** run each one once on the GPU machine and publish the files. This is what we deploy for the submission.
- **Future forecasts:** they can't be precomputed, because the satellite scans they need don't exist yet. A live site needs the GPU machine to run the model on a schedule, after each new scan arrives, and upload the new files. The host still only serves files. See [Later: scheduled runs](#later-scheduled-runs).

```
GPU machine (4060 Ti)                                   any machine with Node 22       Cloudflare Pages
nowcast.india.run  ->  results/india*/*.json + .npz  ->  export_site.py  ->  site/public/data/  ->  npm run build  ->  web/dist/  ->  wrangler deploy  ->  CDN
     (torch)             (forecast + map arrays)        (numpy, pyproj)       (JSON + PNG)          (copies data in)                  (static files)
```

The site has no backend, API, database or secret keys. Everything it shows is in `web/dist/`.

## What runs where

| Step | Machine | Needs | Output |
|---|---|---|---|
| Inference (`nowcast.india.run`) | GPU machine | the repo installed, checkpoints, internet for GK2A/GFS, MOSDAC files for INSAT | `results/india/` (GK2A), `results/india_insat/` (INSAT): `.json` + `.npz` |
| Export (`scripts/export_site.py`) | wherever the `.npz` files are, usually the GPU machine | numpy, pyproj | `site/public/data/` |
| Build + deploy | any machine with Node 22 | the exported `site/public/data/` | `web/dist/`, then the live site |

**The map files are never committed.** `results/` and `site/public/data/` are gitignored. Only the forecast JSONs in `results/india*/` are force-added. The `.npz` map arrays stay on the GPU machine and go into the site at export time. An export without them still works, but every forecast then shows "This forecast has no map" and only the hourly chances.

## Deploy the case studies (for the submission)

### One-time setup

On the machine that will deploy:

```bash
npx wrangler login                                  # opens a browser to sign in to Cloudflare
npx wrangler pages project create <name> --production-branch main
```

`<name>` becomes `<name>.pages.dev`.

### 1. Run the cases on the GPU machine

STEPS.md step 12 lists the cases and the checkpoints to use. Run each case twice, once per satellite, so the site can show INSAT with GK2A as the cross-check:

```bash
# GK2A (open data, no login)
python -m nowcast.india.run --city Kolkata --time 2024-05-09T06:00 --gk2a \
  --tier1 <tier1.pt> --tier2 <tier2.pt> --switch-hour <N> --out results/india

# INSAT (MOSDAC L1B files in data/insat/)
python -m nowcast.india.run --city Kolkata --time 2024-05-09T06:00 --insat-dir data/insat \
  --tier1 <tier1.pt> --tier2 <tier2.pt> --switch-hour <N> --out results/india_insat
```

Each run takes about 15 minutes, mostly downloading. Skip any case whose `.json` and `.npz` are already there.

### 2. Export

From the repo root, on the machine with the `.npz` files:

```bash
python scripts/export_site.py --results results --cases site/cases.json \
  --boundary data/boundaries/india_states.geojson --out site/public/data
```

It prints the number of forecasts and the size. Check that the forecasts now have maps:

```bash
grep -c '"has_maps": true' site/public/data/manifest.json   # should equal the number of forecasts
```

Titles, descriptions and hidden cases come from `site/cases.json`. A case with `"hide": true` is left out.

If the build runs on another machine, copy `site/public/data/` into the same path in its checkout, or point the build at it with `SITE_PUBLIC=/path/to/public`, where `public` is the folder that contains `data/`.

### 3. Build and check

```bash
cd web
npm ci
npm test
npm run build        # typecheck, then copies site/public/ into dist/ with the app
npm run preview      # open the printed URL and go through the checklist below
```

The build copies whatever is in `site/public/` at that moment. Always export first, then build.

### 4. Deploy

```bash
npx wrangler pages deploy dist --project-name <name> --branch main
```

Keep `--branch main`. Without it, wrangler uses the current git branch, and any branch other than the production branch becomes a preview deployment on its own URL.

Vercel works the same way, since `dist/` needs no server config: `npx vercel deploy dist --prod`.

### Checklist before publishing

- [ ] Every case in `site/cases.json` without `hide` is in the run picker, and the hidden ones are not.
- [ ] Map overlays appear for each case, and the time bar animates them.
- [ ] The honest label ("Trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations") is at the bottom of every view.
- [ ] "Boundaries: Survey of India" is on the map.
- [ ] Under Inputs, INSAT is the forecast and GK2A the cross-check.
- [ ] The storm check is titled as a satellite proxy, not lightning.
- [ ] The site works at phone width.

## Updating and rolling back

Any change to the data means export, build, then deploy again. Each deploy replaces the whole site at once, so visitors never see a mix of old and new files.

Every deployment stays in the Cloudflare dashboard (Workers & Pages → the project → Deployments), and any of them can be restored with one click.

## Later: scheduled runs

This part isn't needed for the submission. A live site means a cron job on the GPU machine running steps 1 to 4 for recent issue times:

```bash
#!/usr/bin/env bash
# every 3 h from cron; issue time = latest whole hour
set -euo pipefail
T=$(date -u +%Y-%m-%dT%H:00)
for CITY in Kolkata Bhubaneswar; do
  python -m nowcast.india.run --city "$CITY" --time "$T" --gk2a \
    --tier1 <tier1.pt> --tier2 <tier2.pt> --switch-hour <N> --out results/india
done
python scripts/export_site.py --results results --cases site/cases.json \
  --boundary data/boundaries/india_states.geojson --out site/public/data
(cd web && npm run build && npx wrangler pages deploy dist --project-name <name> --branch main)
```

Limits to know first:
- **Throughput.** About 15 minutes per city, so one machine covers two or three cities an hour, not all 20 in `CITIES`.
- **Delay.** GFS is used from the newest cycle at least 4 hours old (`india/gfs.py`). How long GK2A scans take to reach NOAA's bucket hasn't been measured, so the latest whole hour may not have its scans yet. Measure this before choosing the issue time.
- **Size.** Each forecast with maps adds 1 to 2 MB and about 40 files. Delete old runs from `results/india*/` and keep only the latest runs and the cases. Cloudflare Pages allows 20,000 files per deployment and 25 MiB per file.
- **INSAT needs MOSDAC files,** which need a login, so a scheduled job would run on GK2A only unless the INSAT download is automated.

Needed in `export_site.py` before this works:
- A forecast with no entry in `site/cases.json` gets `kind: "case"`, and the site then marks it as archived. Scheduled runs should default to `"run"`.
