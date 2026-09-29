// The Canvas slot. The rest of the app talks to it only through CanvasProps (FRAME §6),
// so a globe or another depiction can replace this file without touching anything else.
import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { ImageSource } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { LGHT_STOPS, rampColor, type Layer } from "./data";

export type Region = {
  id: string; city: string; lat: number; lon: number;
  corners: [number, number][];
  intensity: (t: number) => number;
  overlay: (t: number, layer: Layer) => string | null;
};
export type CanvasProps = {
  regions: Region[];
  selected: string | null;
  t: number;
  layer: Layer;
  boundary: GeoJSON.FeatureCollection | null;
  onSelectRegion(id: string): void;
  onHover(id: string | null): void;
};

maplibregl.setWorkerUrl(new URL(workerUrl, location.href).href); // v6 cannot find its worker once bundled

const INDIA: [[number, number], [number, number]] = [[68, 6], [97.5, 37.5]];
const STYLE: maplibregl.StyleSpecification = {
  version: 8, sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#0a0a0a" } }], // no basemap, no borders
};

const cornersBounds = (c: [number, number][]) =>
  c.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(c[0], c[0]));

export default function Canvas(p: CanvasProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef(new Map<string, { m: maplibregl.Marker; el: HTMLDivElement; corners: [number, number][] }>());
  const cb = useRef(p);
  cb.current = p;

  // Map once; keep it sized to its grid cell (the panel opening changes it).
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!, style: STYLE, bounds: INDIA, fitBoundsOptions: { padding: 48 },
      attributionControl: { compact: false }, dragRotate: false, pitchWithRotate: false, renderWorldCopies: false,
    });
    m.touchZoomRotate.disableRotation();
    map.current = m;
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(el.current!);
    m.on("zoom", sizeGlows);
    m.once("load", () => { ready.current = true; for (const fn of queue.current.splice(0)) fn(m); });
    return () => { ro.disconnect(); m.remove(); map.current = null; ready.current = false; markers.current.clear(); };
  }, []);

  // Glow diameter follows the tile's size on screen.
  function sizeGlows() {
    const m = map.current;
    if (!m) return;
    for (const { el, corners } of markers.current.values()) {
      const w = Math.abs(m.project(corners[1]).x - m.project(corners[0]).x);
      el.style.setProperty("--tile", `${Math.max(24, w)}px`);
    }
  }

  // Style calls wait for the first load only; isStyleLoaded() flips false while any source loads.
  const ready = useRef(false);
  const queue = useRef<((m: maplibregl.Map) => void)[]>([]);
  const whenReady = (fn: (m: maplibregl.Map) => void) => {
    if (ready.current && map.current) fn(map.current); else queue.current.push(fn);
  };

  // SoI boundaries: the only borders on the map.
  useEffect(() => whenReady((m) => {
    for (const id of ["soi-line", "soi-fill"]) if (m.getLayer(id)) m.removeLayer(id);
    if (m.getSource("soi")) m.removeSource("soi");
    if (!p.boundary) return;
    m.addSource("soi", { type: "geojson", data: p.boundary, attribution: "Boundaries: Survey of India" });
    m.addLayer({ id: "soi-fill", type: "fill", source: "soi", paint: { "fill-color": "#1a1c20" } }, firstRegionLayer(m));
    m.addLayer({ id: "soi-line", type: "line", source: "soi", paint: { "line-color": "#363a3f", "line-width": 0.6 } }, firstRegionLayer(m));
  }), [p.boundary]);

  // Regions: overlay image, tile outline and glow marker per region.
  const regionKey = p.regions.map((r) => r.id).join("|");
  useEffect(() => {
    const ids = p.regions.map((r) => r.id);
    whenReady((m) => {
      for (const r of p.regions) {
        if (m.getSource(`ov-${r.id}`)) continue;
        m.addSource(`ov-${r.id}`, { type: "image", coordinates: r.corners as never });
        m.addLayer({ id: `ov-${r.id}`, type: "raster", source: `ov-${r.id}`, layout: { visibility: "none" }, paint: { "raster-fade-duration": 0 } });
        const ring = [...r.corners, r.corners[0]];
        m.addSource(`tile-${r.id}`, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: ring } } });
        m.addLayer({ id: `tile-${r.id}`, type: "line", source: `tile-${r.id}`, layout: { visibility: "none" },
          paint: { "line-color": "#7d8187", "line-width": 1, "line-dasharray": [3, 3] } });
      }
    });
    for (const r of p.regions) {
      if (markers.current.has(r.id)) continue;
      const e = document.createElement("div");
      e.className = "region";
      e.innerHTML = `<div class="glow"></div><div class="dot"></div><div class="label caption-mono-sm"></div>`;
      e.querySelector(".label")!.textContent = r.city;
      e.setAttribute("role", "button");
      e.setAttribute("tabindex", "0");
      e.setAttribute("aria-label", `${r.city}: open hourly forecast`);
      e.onclick = () => cb.current.onSelectRegion(r.id);
      e.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") cb.current.onSelectRegion(r.id); };
      e.onmouseenter = () => cb.current.onHover(r.id);
      e.onmouseleave = () => cb.current.onHover(null);
      const mk = new maplibregl.Marker({ element: e }).setLngLat([r.lon, r.lat]).addTo(map.current!);
      markers.current.set(r.id, { m: mk, el: e, corners: r.corners });
    }
    // Drop regions that left (run change).
    for (const [id, { m: mk }] of markers.current) {
      if (ids.includes(id)) continue;
      mk.remove();
      markers.current.delete(id);
      whenReady((m) => {
        for (const k of [`ov-${id}`, `tile-${id}`]) { if (m.getLayer(k)) m.removeLayer(k); if (m.getSource(k)) m.removeSource(k); }
      });
    }
    sizeGlows();
  }, [regionKey]);

  // Every frame of state: intensity, overlay, selection.
  useEffect(() => {
    for (const r of p.regions) {
      const mk = markers.current.get(r.id);
      if (!mk) continue;
      const i = Math.min(1, Math.max(0, r.intensity(p.t)));
      const c = rampColor(LGHT_STOPS, i) ?? [125, 129, 135]; // below the ramp: a faint mute ember
      const on = r.id === p.selected;
      const url = on ? r.overlay(p.t, p.layer) : null;
      mk.el.style.setProperty("--i", i.toFixed(3));
      mk.el.style.setProperty("--c", c.join(" "));
      mk.el.classList.toggle("selected", on);
      (mk.el.querySelector(".glow") as HTMLElement).style.display = url ? "none" : "";
      whenReady((m) => {
        const src = m.getSource(`ov-${r.id}`) as ImageSource | undefined;
        if (!src) return;
        if (url) src.updateImage({ url: `data/${url}` });
        m.setLayoutProperty(`ov-${r.id}`, "visibility", url ? "visible" : "none");
        m.setLayoutProperty(`tile-${r.id}`, "visibility", on ? "visible" : "none");
      });
    }
  }, [p.regions, p.t, p.layer, p.selected]);

  // Framing: India at L0, the tile at L1/L2.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const r = p.regions.find((x) => x.id === p.selected);
    m.fitBounds(r ? cornersBounds(r.corners) : INDIA, { padding: 48, duration: 700 });
    m.once("moveend", sizeGlows);
  }, [p.selected, regionKey]);

  // Preload the selected region's step images so playback doesn't flicker.
  useEffect(() => {
    const r = p.regions.find((x) => x.id === p.selected);
    if (!r) return;
    for (let t = 10; t <= 360; t += 10) {
      const u = r.overlay(t, p.layer);
      if (u) new Image().src = `data/${u}`;
    }
  }, [p.selected, p.layer, regionKey]);

  return <div ref={el} className="map" />;
}

function firstRegionLayer(m: maplibregl.Map) {
  return m.getStyle().layers.find((l: { id: string }) => l.id.startsWith("ov-") || l.id.startsWith("tile-"))?.id;
}
