import { test } from "node:test";
import assert from "node:assert/strict";
import {
  groupRuns, positions, overlayAt, intensityAt, rampColor, parseJSON, parseHash, toHash, LGHT_STOPS,
  type Forecast, type ManifestEntry,
} from "./data.ts";

const entry = (id: string, city: string, issue_utc: string, peak: "LOW" | "HIGH", kind: "case" | "run" = "case") =>
  ({ id, city, issue_utc, issue_ist: issue_utc, peak_risk: peak, kind, lat: 0, lon: 0, title: id, has_maps: false, file: "" }) as ManifestEntry;

test("runs: grouped by issue time, newest first, INSAT primary, GK2A cross-check", () => {
  const runs = groupRuns([
    entry("Delhi_A", "Delhi", "2024-05-28T08:00", "LOW"),
    entry("Kolkata_B", "Kolkata", "2024-05-09T06:00", "HIGH"),
    entry("Kolkata_B_insat", "Kolkata", "2024-05-09T06:00", "HIGH"),
    entry("Patna_B", "Patna", "2024-05-09T06:00", "LOW", "run"),
  ]);
  assert.deepEqual(runs.map((r) => r.key), ["2024-05-28T08:00", "2024-05-09T06:00"]);
  const k = runs[1];
  assert.equal(k.regions.length, 2);
  assert.equal(k.regions[0].primary.id, "Kolkata_B_insat");
  assert.equal(k.regions[0].cross?.id, "Kolkata_B");
  assert.equal(k.regions[1].cross, null);
  assert.equal(k.peak, "HIGH");
  assert.equal(k.archived, false); // one live forecast drops the badge
  assert.equal(runs[0].archived, true);
});

const hours = [1, 2, 3, 4, 5, 6].map((h) => ({ lead_hour: h, p_tile_max: h / 10 }));
const fc = (steps: number[]) => ({
  hours, overlays: {
    hourly: { "1": "h1.png", "4": "h4.png" },
    steps: steps.map((m) => ({ minutes: m, lightning: `l${m}.png`, vil: `v${m}.png` })),
  },
}) as unknown as Forecast;

test("positions: 10-min steps then hourly; hourly only without steps", () => {
  const tens = Array.from({ length: 18 }, (_, i) => (i + 1) * 10);
  assert.deepEqual(positions(fc(tens)), [...tens, 240, 300, 360]);
  assert.deepEqual(positions(fc([])), [60, 120, 180, 240, 300, 360]);
});

test("t -> overlay and intensity", () => {
  const f = fc([10, 20]);
  assert.equal(overlayAt(f, 20, "vil"), "v20.png");
  assert.equal(overlayAt(f, 60, "lightning"), "h1.png"); // no step at 60 -> hourly
  assert.equal(overlayAt(f, 240, "lightning"), "h4.png");
  assert.equal(overlayAt(f, 240, "vil"), null);
  assert.equal(overlayAt(f, 300, "lightning"), null);
  assert.equal(intensityAt(f, 10), 0.1);
  assert.equal(intensityAt(f, 61), 0.2);
  assert.equal(intensityAt(f, 360), 0.6);
});

test("ramp matches the exporter stops", () => {
  assert.equal(rampColor(LGHT_STOPS, 0.04), null);
  assert.deepEqual(rampColor(LGHT_STOPS, 0.05), [255, 237, 160]);
  assert.deepEqual(rampColor(LGHT_STOPS, 0.4), [240, 59, 32]);
  assert.deepEqual(rampColor(LGHT_STOPS, 0.95), [84, 39, 143]);
});

test("NaN from the exporter parses; hash round-trips", () => {
  assert.deepEqual(parseJSON('{"csi": NaN, "x": "NaNa"}'), { csi: null, x: "NaNa" });
  const v = { run: "2024-05-09T06:00", r: "Kolkata", tab: "inputs", t: 120, layer: "vil" as const };
  assert.deepEqual(parseHash(toHash(v)), v);
  assert.deepEqual(parseHash(""), { run: undefined, r: undefined, tab: undefined, t: undefined, layer: undefined });
});
