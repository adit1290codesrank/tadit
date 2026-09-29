import { useCallback, useEffect, useMemo, useState } from "react";
import Canvas, { type Region } from "./Canvas";
import TopBar from "./TopBar";
import TimeBar from "./TimeBar";
import RegionPanel, { TABS, type Tab } from "./RegionPanel";
import AboutDrawer from "./AboutDrawer";
import {
  getJSON, groupRuns, positions, overlayAt, observedAt, intensityAt, cssGradient, parseHash, toHash,
  LGHT_STOPS, VIL_STOPS, type Forecast, type Manifest, type View, type Layer,
} from "./data";

type Loaded = Forecast | { error: string };
const ok = (x: Loaded | undefined): x is Forecast => !!x && !("error" in x);

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [boundary, setBoundary] = useState<GeoJSON.FeatureCollection | null>(null);
  const [fcs, setFcs] = useState<Record<string, Loaded>>({});
  const [view, setView] = useState<View>(() => parseHash(location.hash));
  const [playing, setPlaying] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadManifest = useCallback(() => {
    setFatal(null);
    getJSON<Manifest>("manifest.json").then(setManifest, (e) => setFatal(`Could not load the forecast list (${e.message}).`));
  }, []);
  useEffect(loadManifest, [loadManifest]);
  useEffect(() => {
    if (manifest?.boundary) getJSON<GeoJSON.FeatureCollection>(manifest.boundary).then(setBoundary, () => setBoundary(null));
  }, [manifest?.boundary]);

  const load = useCallback((id: string, file: string) => {
    setFcs((s) => { const n = { ...s }; delete n[id]; return n; });
    getJSON<Forecast>(file).then(
      (f) => setFcs((s) => ({ ...s, [id]: f })),
      (e) => setFcs((s) => ({ ...s, [id]: { error: e.message } })),
    );
  }, []);

  // ---------------------------------------------------------------- derived view
  const runs = useMemo(() => groupRuns(manifest?.forecasts ?? []), [manifest]);
  const run = runs.find((r) => r.key === view.run) ?? runs[0] ?? null;
  const ref = run?.regions.find((r) => r.city === view.r) ?? null;
  const f = ref ? fcs[ref.primary.id] : undefined;
  const sel = ok(f) ? f : null;
  const cross = ref?.cross ? fcs[ref.cross.id] : undefined;

  // Every region's primary forecast in the run (the canvas needs them all); the cross-check only once selected.
  useEffect(() => {
    for (const r of run?.regions ?? []) if (!(r.primary.id in fcs)) load(r.primary.id, r.primary.file);
  }, [run?.key]);
  useEffect(() => {
    if (ref?.cross && !(ref.cross.id in fcs)) load(ref.cross.id, ref.cross.file);
  }, [ref?.cross?.id]);

  const loaded = (run?.regions ?? []).map((r) => fcs[r.primary.id]).filter(ok);
  const pos = sel ? positions(sel) : [...new Set(loaded.flatMap(positions))].sort((a, b) => a - b);
  const t = view.t != null && pos.includes(view.t) ? view.t : pos[0] ?? 60;
  const layer: Layer = view.layer ?? "lightning";
  const hasCheck = !!sel?.storm_check?.hours?.length || !!sel?.lightning_check?.hours?.length;
  const tab = ref && TABS.some(([k]) => k === view.tab) && (view.tab !== "check" || hasCheck) ? (view.tab as Tab) : null;
  const seam = manifest?.switch_hour != null && pos.some((m) => m > manifest.switch_hour! * 60) ? manifest.switch_hour * 60 : null;

  const regions: Region[] = useMemo(() => (run?.regions ?? []).flatMap((r) => {
    const x = fcs[r.primary.id];
    if (!ok(x)) return [];
    return [{
      id: r.city, city: r.city, lat: x.lat, lon: x.lon, corners: x.tile.corners,
      intensity: (t: number) => intensityAt(x, t), overlay: (t: number, l: Layer) => overlayAt(x, t, l),
      observed: (t: number) => observedAt(x, t),
    }];
  }), [run?.key, fcs]);

  // ---------------------------------------------------------------- actions
  const set = (v: Partial<View>) => setView((o) => ({ ...o, ...v }));
  const setRun = (key: string) => { setPlaying(false); setView({ run: key }); };
  const select = (city: string | null) => set({ r: city ?? undefined, tab: undefined });
  const setT = (x: number) => set({ t: x });

  // URL hash holds the shareable view.
  useEffect(() => {
    if (!run) return;
    history.replaceState(null, "", toHash({ run: run.key, r: ref?.city, tab: tab ?? undefined, t, layer }));
  }, [run?.key, ref?.city, tab, t, layer]);
  useEffect(() => {
    const on = () => setView(parseHash(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // Esc goes back one level.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (drawer) setDrawer(false);
      else if (tab) set({ tab: undefined });
      else if (ref) select(null);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [drawer, tab, ref]);

  // Playback: constant wall-clock rate per position; stops at the end.
  useEffect(() => {
    if (!playing || !pos.length) return;
    const id = setInterval(() => {
      setView((o) => {
        const cur = o.t != null && pos.includes(o.t) ? o.t : pos[0];
        const i = pos.indexOf(cur);
        if (i >= pos.length - 1) { setPlaying(false); return o; }
        return { ...o, t: pos[i + 1] };
      });
    }, 700);
    return () => clearInterval(id);
  }, [playing, pos.join()]);
  const play = (on: boolean) => {
    if (on && t === pos.at(-1)) setT(pos[0]);
    setPlaying(on);
  };

  // Storm intensity exists only where there are 10-min steps (first 3 h).
  useEffect(() => {
    if (layer === "vil" && sel && !overlayAt(sel, t, "vil")) {
      set({ layer: undefined });
      setNotice("Storm intensity only covers the first 3 hours.");
    }
  }, [layer, t, sel?.id]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(id);
  }, [notice]);

  // ---------------------------------------------------------------- render
  const label = manifest?.honest_label ?? "Trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations";
  const crossF = ok(cross) ? cross : null;
  const title = ref && sel
    ? (ref.cross && / IST$/.test(sel.title) && crossF && !/ IST$/.test(crossF.title) ? crossF.title : sel.title)
    : "";
  const description = sel?.description || crossF?.description || "";
  const noMaps = ref && !ref.primary.has_maps;

  return (
    <div className="app">
      <TopBar runs={runs} run={run} validUntil={loaded[0]?.valid_until_ist ?? null} onRun={setRun} onAbout={() => setDrawer(true)} />

      <main className={`stage${ref ? " open" : ""}`}>
        <section className="canvas" aria-label="Map">
          {fatal ? (
            <div className="center"><div className="empty">
              <p className="display-xs">Forecast data didn't load</p>
              <p className="body-sm body">{fatal}</p>
              <button className="pill" onClick={loadManifest}>Try again</button>
            </div></div>
          ) : manifest && !runs.length ? (
            <div className="center"><div className="empty">
              <p className="display-xs">No forecasts yet</p>
              <p className="body-sm body">There are no forecasts to show right now. Check back later.</p>
            </div></div>
          ) : (
            <>
              <Canvas regions={regions} selected={ref?.city ?? null} t={t} layer={layer} boundary={boundary}
                onSelectRegion={select} onHover={() => {}} />
              <div className="legend card">
                <p className="caption-mono-sm">{layer === "vil" ? "Storm intensity" : "Lightning chance"}</p>
                <div className="bar" style={{ background: cssGradient(layer === "vil" ? VIL_STOPS : LGHT_STOPS) }} />
                <div className="ticks caption-mono-sm mute">
                  {layer === "vil"
                    ? <><span>weak</span><span>strong</span></>
                    : <><span>5%</span><span>20%</span><span>40%</span><span>60%</span><span>80%</span></>}
                </div>
                <p className="hint">{layer === "vil" ? "How strong the storm is in each 2 km square" : "Chance of lightning in each 16 km square"}</p>
                {layer === "lightning" && sel?.observed && (
                  <p className="obs-key"><span className="obs-dot" aria-hidden /> Real lightning that happened ({sel.observed.source.replace(/ \(flashes\)$/, "")})</p>
                )}
              </div>
              {!ref && regions.length > 0 && (
                <p className="canvas-hint hint">The glow shows where lightning is likely in the next 6 hours; brighter means more likely. Click a place for its hourly forecast.</p>
              )}
              {(notice || noMaps) && (
                <div className="canvas-note toast">{notice ?? "This forecast has no map. The hourly chances are in the forecast panel."}</div>
              )}
            </>
          )}
        </section>

        {ref && (
          sel ? (
            <RegionPanel
              f={sel} cross={crossF} crossPending={!!ref.cross && !cross} title={title}
              t={t} layer={layer} tab={tab} seam={seam}
              onT={(x) => { setPlaying(false); setT(x); }} onLayer={(l) => set({ layer: l })}
              onTab={(k) => set({ tab: k ?? undefined })} onClose={() => select(null)}
            />
          ) : f && "error" in f ? (
            <aside className="panel">
              <div className="toast">
                <span>Couldn't load the forecast for {ref.city}. {f.error}</span>
                <button className="pill sm" onClick={() => load(ref.primary.id, ref.primary.file)}>Retry</button>
              </div>
            </aside>
          ) : (
            <aside className="panel" aria-busy>
              <div className="skeleton" style={{ height: 36, width: "60%" }} />
              <div className="skeleton" style={{ height: 20, width: "80%" }} />
              <div className="skeleton" style={{ height: 480 }} />
            </aside>
          )
        )}
      </main>

      <TimeBar positions={pos} t={t} issueIst={run?.issue_ist ?? null} seam={seam} playing={playing} onT={setT} onPlay={play} />

      <footer className="status">
        <p>{label}</p>
        <button className="round" aria-label="About this forecast" onClick={() => setDrawer(true)}>i</button>
      </footer>

      {drawer && manifest && <AboutDrawer manifest={manifest} f={sel ?? loaded[0] ?? null} description={sel ? description : loaded[0]?.description ?? ""} onClose={() => setDrawer(false)} />}
    </div>
  );
}
