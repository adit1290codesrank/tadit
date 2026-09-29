# Forecast viewer

The public site for the India nowcasts. It's a static Vite + React + TypeScript app with MapLibre. It reads the JSON and PNG files that `scripts/export_site.py` writes (see `docs/SITE_DATA.md`). No forecast data is committed here.

`BRIEF.md` says what the site is for, `FRAME.md` fixes its structure and `DESIGN.md` fixes its look.

## Run it locally

You need Node 22 or newer.

1. Export the data from the repo root. This writes `site/public/data/`, which the site serves at `data/`:

   ```sh
   python scripts/export_site.py --cases site/cases.json \
     --boundary data/boundaries/india_states.geojson
   ```

2. Install and start the dev server:

   ```sh
   cd web
   npm ci
   npm run dev
   ```

   Vite prints the local URL. To point the site at an export somewhere else, set `SITE_PUBLIC` to the folder that contains `data/`:

   ```sh
   SITE_PUBLIC=/path/to/public npm run dev
   ```

Without an export the page loads and shows "Forecast data didn't load".

## Test and build

```sh
npm test          # unit tests for the data logic in src/data.ts
npm run build     # typecheck, then build into dist/
npm run preview   # serve dist/ locally
```

## Deploy

`dist/` is a static folder with relative paths, so any static host works. For Cloudflare Pages:

```sh
cd web && npm ci && npm run build && npx wrangler pages deploy dist
```

Re-run the export before each build. The build copies whatever is in `site/public/` at that moment.

## INSAT forecasts

Name forecasts run on INSAT `<City>_<YYYYmmddTHHMM>_insat.json` and export them next to the GK2A ones. The site pairs the two by city and issue time. It shows INSAT as the forecast and GK2A as the cross-check under Inputs. `FRAME.md` §7 has the details.
