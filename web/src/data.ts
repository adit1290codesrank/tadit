// Site data contract (docs/SITE_DATA.md) and the pure logic around it. No React in here.

export type Risk = "LOW" | "MODERATE" | "HIGH";
export type Status = "live" | "approximate" | "partial" | "missing";
export type Layer = "lightning" | "vil";

export type ManifestEntry = {
  id: string; city: string; lat: number; lon: number; title: string; kind: "case" | "run";
  issue_ist: string; issue_utc: string; peak_risk: Risk | null; has_maps: boolean; has_observed?: boolean; file: string;
};
export type Manifest = {
  generated_utc: string; honest_label: string; switch_hour: number | null;
  model: { tier1: Record<string, unknown>; tier2: Record<string, unknown> };
  boundary: string | null; forecasts: ManifestEntry[];
};
export type Hour = {
  lead_hour: number; window_ist: [string, string]; source: "tier1" | "tier2" | null;
  p_location: number | null; p_tile_max: number | null; risk: Risk | null; advice: string;
};
export type Step = { minutes: number; time_ist: string; p_location: number | null; lightning: string; vil?: string };
export type CheckHour = {
  hour: number; p_city: number | null; coldest_city_c: number | null; deep_cells: number; fc_cells: number;
  hits: number; pod: number | null; far: number | null; csi: number | null;
};
export type LightningCheckHour = {
  hour: number; status: "scored" | "no data"; cells_observed?: number; strikes_within_16km?: number;
  pod?: number | null; far?: number | null; csi?: number | null; csi_20?: number | null; persistence_csi: number | null;
};
export type Forecast = {
  id: string; city: string; lat: number; lon: number; title: string; description: string; kind: "case" | "run";
  issue_utc: string; issue_ist: string; valid_until_ist: string;
  tile: { center: [number, number]; corners: [number, number][]; size_km: number };
  hours: Hour[]; peak_risk: Risk | null;
  inputs: {
    satellite: { status: Status; source: string | null; scans_utc: string[] };
    radar: { status: Status; source: string | null; detail: string | null };
    lightning: { status: Status; source: string | null };
    nwp: { status: Status; runs: { model: string; init: string; fxx: number; valid: string; status: string }[] };
  };
  model_inputs_used: Record<string, boolean> | null;
  honest_label: string;
  overlays: { hourly: Record<string, string>; steps: Step[] };
  storm_check?: { what: string; proxy: string; hours: CheckHour[] };
  lightning_check?: { what: string; source: string; hours: LightningCheckHour[] };
  // Observed lightning (e.g. FY-4A satellite flashes) as [lon, lat], per 10-min step (to 3 h) and per lead hour.
  observed?: { source: string; steps: Record<string, [number, number][]>; hourly: Record<string, [number, number][]> };
};

// The exporter writes Python's NaN (storm check on a calm day), which is not valid JSON.
export function parseJSON<T>(text: string): T {
  return JSON.parse(text.replace(/\bNaN\b/g, "null")) as T;
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`data/${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return parseJSON<T>(await r.text());
}

// --------------------------------------------------------------------------- runs and regions

// One region = one city in a run. The INSAT export (`<id>_insat`) is primary; the GK2A one is its cross-check.
export type RegionRef = { city: string; primary: ManifestEntry; cross: ManifestEntry | null };
export type Run = { key: string; issue_ist: string; regions: RegionRef[]; archived: boolean; peak: Risk | null };

export const isInsat = (id: string) => id.endsWith("_insat");
const RISKS: Risk[] = ["LOW", "MODERATE", "HIGH"];
export const maxRisk = (rs: (Risk | null)[]) =>
  rs.reduce<Risk | null>((a, r) => (r && (!a || RISKS.indexOf(r) > RISKS.indexOf(a)) ? r : a), null);

export function groupRuns(entries: ManifestEntry[]): Run[] {
  const byRun = new Map<string, ManifestEntry[]>();
  for (const e of entries) byRun.set(e.issue_utc, [...(byRun.get(e.issue_utc) ?? []), e]);
  const runs: Run[] = [];
  for (const [key, es] of byRun) {
    const cities = [...new Set(es.map((e) => e.city))];
    const regions = cities.map((city) => {
      const mine = es.filter((e) => e.city === city);
      const primary = mine.find((e) => isInsat(e.id)) ?? mine[0];
      const cross = isInsat(primary.id) ? mine.find((e) => !isInsat(e.id)) ?? null : null;
      return { city, primary, cross };
    });
    runs.push({
      key, issue_ist: es[0].issue_ist, regions,
      archived: es.every((e) => e.kind === "case"),
      peak: maxRisk(regions.map((r) => r.primary.peak_risk)),
    });
  }
  return runs.sort((a, b) => (a.key < b.key ? 1 : -1));
}

// --------------------------------------------------------------------------- time

export const hourOf = (t: number) => Math.max(1, Math.ceil(t / 60));

// Cursor positions, straight from the data: the 10-min steps, then whole hours after the last step.
export function positions(f: Forecast): number[] {
  const steps = f.overlays.steps.map((s) => s.minutes).sort((a, b) => a - b);
  const last = steps.at(-1) ?? 0;
  return [...steps, ...f.hours.map((h) => h.lead_hour * 60).filter((m) => m > last)];
}

export const hourAt = (f: Forecast, t: number) => f.hours.find((h) => h.lead_hour === hourOf(t));

export function overlayAt(f: Forecast, t: number, layer: Layer): string | null {
  const step = t <= 180 ? f.overlays.steps.find((s) => s.minutes === t) : undefined;
  if (step) return step[layer] ?? null;
  return layer === "lightning" ? f.overlays.hourly[String(hourOf(t))] ?? null : null;
}

// Observed lightning to draw at cursor t: the 10-min window ending at t (first 3 h), then the whole lead hour.
export function observedAt(f: Forecast, t: number): [number, number][] | null {
  if (!f.observed) return null;
  const step = t <= 180 ? f.observed.steps[String(t)] : undefined;
  return step ?? f.observed.hourly[String(hourOf(t))] ?? null;
}

// How strongly a region is drawn: the strongest chance anywhere in its tile, that hour (same in both tiers).
export const intensityAt = (f: Forecast, t: number) => hourAt(f, t)?.p_tile_max ?? 0;

// --------------------------------------------------------------------------- colour ramps (copied from export_site.py)

type Stops = [number, [number, number, number]][];
export const LGHT_STOPS: Stops = [[0.05, [255, 237, 160]], [0.2, [254, 178, 76]], [0.4, [240, 59, 32]],
  [0.6, [189, 0, 38]], [0.8, [84, 39, 143]]];
export const VIL_STOPS: Stops = [[16, [199, 233, 192]], [74, [65, 171, 93]], [133, [35, 139, 69]],
  [160, [254, 196, 79]], [181, [236, 112, 20]], [219, [153, 52, 4]]];

// Same piecewise-linear colour as the PNGs; null below the first stop (transparent there).
export function rampColor(stops: Stops, x: number): [number, number, number] | null {
  if (!(x >= stops[0][0])) return null;
  for (let k = 1; k < stops.length; k++) {
    const [v0, c0] = stops[k - 1], [v1, c1] = stops[k];
    if (x <= v1) {
      const f = (x - v0) / (v1 - v0);
      return c0.map((c, i) => Math.round(c + (c1[i] - c) * f)) as [number, number, number];
    }
  }
  return stops.at(-1)![1];
}

export const cssGradient = (stops: Stops) => {
  const lo = stops[0][0], hi = stops.at(-1)![0];
  return `linear-gradient(90deg, ${stops.map(([v, c]) => `rgb(${c.join(",")}) ${((v - lo) / (hi - lo)) * 100}%`).join(", ")})`;
};

// --------------------------------------------------------------------------- formatting (exported times are already IST)

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const asDate = (iso: string) => new Date(iso.slice(0, 16) + ":00Z");
const two = (n: number) => String(n).padStart(2, "0");

export const hm = (iso: string) => iso.slice(11, 16);
export const day = (iso: string) => { const d = asDate(iso); return `${two(d.getUTCDate())} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const dayHm = (iso: string) => `${day(iso)}, ${hm(iso)}`;
export function addMin(iso: string, m: number) {
  const d = new Date(asDate(iso).getTime() + m * 60_000);
  return d.toISOString().slice(0, 16);
}
export const utcToIst = (iso: string) => addMin(iso, 330);
export const pct = (p: number | null) => (p == null ? "n/a" : `${Math.round(p * 100)} %`);
export const riskShort = (r: Risk | null) => (r === "MODERATE" ? "MOD" : r ?? "n/a");

// --------------------------------------------------------------------------- URL hash (shareable view)

export type View = { run?: string; r?: string; tab?: string; t?: number; layer?: Layer };

export function parseHash(h: string): View {
  const q = new URLSearchParams(h.replace(/^#/, ""));
  const t = Number(q.get("t"));
  return {
    run: q.get("run") ?? undefined, r: q.get("r") ?? undefined, tab: q.get("tab") ?? undefined,
    t: Number.isFinite(t) && t > 0 ? t : undefined,
    layer: q.get("layer") === "vil" ? "vil" : undefined,
  };
}

export function toHash(v: View): string {
  const q = new URLSearchParams();
  for (const [k, x] of Object.entries(v)) if (x != null && x !== "" && !(k === "layer" && x === "lightning")) q.set(k, String(x));
  return "#" + q.toString();
}
