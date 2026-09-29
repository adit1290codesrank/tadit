import { addMin, hm, hourOf, overlayAt, pct, riskShort, utcToIst, type Forecast, type Hour, type Layer, type Status } from "./data";

export const TABS = [
  ["timeline", "Timeline"], ["curve", "Risk curve"], ["inputs", "Inputs"], ["check", "Storm check"],
] as const;
export type Tab = (typeof TABS)[number][0];

type P = {
  f: Forecast; cross: Forecast | null; crossPending: boolean; title: string;
  t: number; layer: Layer; tab: Tab | null; seam: number | null;
  onT(t: number): void; onLayer(l: Layer): void; onTab(t: Tab | null): void; onClose(): void;
};

export default function RegionPanel(p: P) {
  const cur = hourOf(p.t);
  return (
    <aside className="panel" aria-label={`${p.f.city} forecast`}>
      <div className="panel-head">
        <div style={{ display: "grid", gap: "var(--xs)" }}>
          <h2 className="display-sm">{p.f.city}</h2>
          <p className="body-sm body">{p.title}</p>
        </div>
        <div style={{ display: "flex", gap: "var(--sm)", alignItems: "center" }}>
          {p.f.peak_risk && <span className={`chip ${p.f.peak_risk}`} title="Highest risk in the next 6 hours">Peak {riskShort(p.f.peak_risk)}</span>}
          {p.tab
            ? <button className="round" aria-label="Back to hourly forecast" onClick={() => p.onTab(null)}>←</button>
            : <button className="round" aria-label="Close" onClick={p.onClose}>×</button>}
        </div>
      </div>

      {p.tab == null ? (
        <>
          <p className="hint">Chance of lightning at the city, hour by hour. Under 20 % is LOW, over 50 % is HIGH.</p>
          <div className="card hourlist">
            <ol>
              {p.f.hours.map((h, i) => (
                <li key={h.lead_hour}>
                  {h.source === "tier2" && p.f.hours[i - 1]?.source !== "tier2" && (
                    <div className="seamrow caption-mono-sm">outlook: hours 4 to 6, less detail</div>
                  )}
                  <HourCard h={h} on={h.lead_hour === cur} onClick={() => p.onT(h.lead_hour * 60)} />
                </li>
              ))}
            </ol>
          </div>
          <button className="pill" style={{ alignSelf: "flex-start" }} onClick={() => p.onTab("timeline")}>More detail</button>
        </>
      ) : (
        <Detail {...p} cur={cur} />
      )}
    </aside>
  );
}

function HourCard({ h, on, onClick }: { h: Hour; on: boolean; onClick(): void }) {
  return (
    <button className="hourrow" aria-current={on} onClick={onClick}>
      <span className="caption-mono-sm mute">
        {hm(h.window_ist[0])} to {hm(h.window_ist[1])} · {h.source === "tier2" ? "outlook" : "nowcast"}
      </span>
      <span style={{ justifySelf: "end" }}>{h.risk && <span className={`chip ${h.risk}`}>{riskShort(h.risk)}</span>}</span>
      <span className="display-sm" title={h.p_location == null ? undefined : `p = ${h.p_location}`}>{pct(h.p_location)}</span>
      <span className="body-sm mute" style={{ justifySelf: "end" }}>Highest nearby {pct(h.p_tile_max)}</span>
      <span className="body-sm body advice">{h.advice}</span>
    </button>
  );
}

function Detail(p: P & { cur: number }) {
  const hasCheck = !!p.f.storm_check?.hours?.length;
  const tabs = TABS.filter(([k]) => k !== "check" || hasCheck);
  return (
    <>
      <HourStrip f={p.f} cur={p.cur} onT={p.onT} />
      <div className="tabs" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={p.tab === k} className={`pill sm${p.tab === k ? " primary" : ""}`} onClick={() => p.onTab(k)}>
            {label}
          </button>
        ))}
      </div>
      <div className="card tabbody" role="tabpanel">
        {p.tab === "timeline" && <Timeline {...p} />}
        {p.tab === "curve" && <RiskCurve {...p} />}
        {p.tab === "inputs" && <Inputs {...p} />}
        {p.tab === "check" && hasCheck && <StormCheck f={p.f} />}
      </div>
    </>
  );
}

function HourStrip({ f, cur, onT }: { f: Forecast; cur: number; onT(t: number): void }) {
  return (
    <div className="hourstrip" aria-label="Chance of lightning per hour">
      {f.hours.map((h, i) => (
        <span key={h.lead_hour} style={{ display: "contents" }}>
          {h.source === "tier2" && f.hours[i - 1]?.source !== "tier2" && <span className="gap" />}
          <button aria-current={h.lead_hour === cur} title={`Hour ${h.lead_hour}: ${pct(h.p_location)}`} onClick={() => onT(h.lead_hour * 60)}>
            <span className="b" style={{ height: `${Math.max(2, (h.p_location ?? 0) * 40)}px` }} />
            <span className="caption-mono-sm mute" style={{ textAlign: "center" }}>{h.lead_hour}</span>
          </button>
        </span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ tabs

function Timeline(p: P) {
  const f = p.f;
  const noMaps = !f.overlays.steps.length && !Object.keys(f.overlays.hourly).length;
  const vilHere = !!overlayAt(f, p.t, "vil");
  const step = f.overlays.steps.find((s) => s.minutes === p.t);
  return (
    <>
      <p className="hint">Press play under the map to watch the storm move. Lightning shows where strikes are likely; storm intensity shows how strong the storm is.</p>
      <div className="tabs">
        <button className={`pill sm${p.layer === "lightning" ? " primary" : ""}`} onClick={() => p.onLayer("lightning")}>Lightning</button>
        <button className={`pill sm${p.layer === "vil" ? " primary" : ""}`} disabled={!vilHere} onClick={() => p.onLayer("vil")}>Storm intensity</button>
      </div>
      {noMaps
        ? <p className="body-sm body">This forecast came without a map, so there is nothing to animate.</p>
        : !vilHere && <p className="body-sm mute">Storm intensity only covers the first 3 hours.</p>}
      <dl className="kv body-sm">
        <dt className="caption-mono-sm mute">Showing</dt>
        <dd>{hm(step?.time_ist ?? addMin(f.issue_ist, p.t))} IST · +{p.t} min</dd>
        <dt className="caption-mono-sm mute">At the city</dt>
        <dd>{pct(step?.p_location ?? f.hours.find((h) => h.lead_hour === hourOf(p.t))?.p_location ?? null)}</dd>
        <dt className="caption-mono-sm mute">Time step</dt>
        <dd>{step ? "10 minutes" : "1 hour"}</dd>
      </dl>
    </>
  );
}

function RiskCurve(p: P) {
  const f = p.f;
  const W = 320, H = 160, L = 28, B = 20;
  const x = (m: number) => L + (m / 360) * (W - L);
  const y = (v: number) => (H - B) * (1 - v);
  const last = f.overlays.steps.at(-1)?.minutes ?? 0;
  const pts: [number, number][] = [
    ...f.overlays.steps.filter((s) => s.p_location != null).map((s) => [s.minutes, s.p_location!] as [number, number]),
    ...f.hours.filter((h) => h.lead_hour * 60 > last && h.p_location != null).map((h) => [h.lead_hour * 60, h.p_location!] as [number, number]),
  ];
  const line = pts.map(([m, v]) => `${x(m)},${y(v)}`).join(" ");
  return (
    <>
      <p className="hint">How the chance of lightning at the city changes: every 10 minutes for the first 3 hours, then every hour.</p>
      <svg className="curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Chance of lightning at the city over 6 hours">
        {[0.2, 0.5].map((v) => (
          <g key={v}>
            <line x1={L} x2={W} y1={y(v)} y2={y(v)} stroke="#363a3f" strokeDasharray="3 3" />
            <text x={0} y={y(v) + 3}>{v * 100}%</text>
          </g>
        ))}
        <text x={W} y={y(0.5) - 4} textAnchor="end">HIGH</text>
        <text x={W} y={y(0.2) - 4} textAnchor="end">MOD</text>
        <text x={W} y={y(0) - 4} textAnchor="end">LOW</text>
        <line x1={L} x2={W} y1={y(0)} y2={y(0)} stroke="#212327" />
        {p.seam != null && <line x1={x(p.seam)} x2={x(p.seam)} y1={0} y2={H - B} stroke="#363a3f" strokeDasharray="2 4" />}
        {[0, 1, 2, 3, 4, 5, 6].map((h) => <text key={h} x={x(h * 60)} y={H - 4} textAnchor="middle">{h}h</text>)}
        <polyline points={line} fill="none" stroke="#ffffff" strokeWidth={1} />
        {pts.filter(([m]) => m % 60 === 0).map(([m, v]) => <circle key={m} cx={x(m)} cy={y(v)} r={2} fill="#ffffff" />)}
        <line x1={x(p.t)} x2={x(p.t)} y1={0} y2={H - B} stroke="#ffffff" strokeOpacity={0.5} />
      </svg>
      {!f.overlays.steps.length && <p className="body-sm mute">Only hourly points: this forecast has no 10-minute data.</p>}
    </>
  );
}

const SAT_NAME = (s: string | null) => (s ?? "").split(" ")[0] || "Satellite";

function Inputs(p: P) {
  const i = p.f.inputs;
  const rows: [string, Status, string][] = [
    ["Satellite", i.satellite.status, i.satellite.source ?? ""],
    ["Radar", i.radar.status, i.radar.source ?? i.radar.detail ?? "Not connected yet for India"],
    ["Lightning", i.lightning.status, i.lightning.source ?? "Not connected yet for India"],
    ["Weather model", i.nwp.status, nwpLine(p.f)],
  ];
  return (
    <>
      <p className="hint">The data this forecast used. Indian radar and lightning feeds are not connected yet.</p>
      <dl className="kv body-sm">
        {rows.map(([k, s, d]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt><span className={`chip ${s}`}>{s}</span></dt>
            <dd><span className="caption-mono-sm">{k}</span><br /><span className="body">{d}</span></dd>
          </div>
        ))}
      </dl>
      {i.satellite.scans_utc.length > 0 && (
        <p className="body-sm mute">Satellite scans: {i.satellite.scans_utc.map((s) => hm(utcToIst(s))).join(", ")} IST</p>
      )}
      {p.cross ? (
        <>
          <p className="eyebrow">Cross-check</p>
          <p className="body-sm body">As a check, we ran the same forecast on {SAT_NAME(p.cross.inputs.satellite.source)} data. Chance of lightning at the city from each:</p>
          <table className="table">
            <thead><tr><th>Hour</th><th>{SAT_NAME(i.satellite.source)}</th><th>{SAT_NAME(p.cross.inputs.satellite.source)}</th></tr></thead>
            <tbody>
              {p.f.hours.map((h) => (
                <tr key={h.lead_hour}>
                  <td>{h.lead_hour}</td><td>{pct(h.p_location)}</td>
                  <td>{pct(p.cross!.hours.find((c) => c.lead_hour === h.lead_hour)?.p_location ?? null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : p.crossPending ? <div className="skeleton" style={{ height: 120 }} /> : null}
    </>
  );
}

function nwpLine(f: Forecast) {
  const runs = f.inputs.nwp.runs;
  if (!runs.length) return "Not available";
  const models = [...new Set(runs.map((r) => r.model.toUpperCase()))].join(", ");
  const ok = runs.filter((r) => r.status === "ok").length;
  return `${models} run from ${hm(utcToIst(runs[0].init))} IST, ${ok} of ${runs.length} hours received`;
}

function StormCheck({ f }: { f: Forecast }) {
  const c = f.storm_check!;
  const n = (v: number | null) => (v == null ? "n/a" : v.toFixed(2));
  return (
    <>
      <p className="eyebrow">{c.what}</p>
      <p className="hint">Did the satellite see storms where we forecast lightning? This checks where storms were. It cannot confirm lightning.</p>
      <table className="table">
        <thead><tr><th>Hour</th><th>Storm cells</th><th>Hits</th><th>POD</th><th>FAR</th><th>CSI</th></tr></thead>
        <tbody>
          {c.hours.map((h) =>
            h.deep_cells === 0 || h.csi == null ? (
              <tr key={h.hour}><td>{h.hour}</td><td colSpan={5} className="mute">No storm clouds seen on satellite</td></tr>
            ) : (
              <tr key={h.hour}>
                <td>{h.hour}</td><td>{h.deep_cells}</td><td>{h.hits}</td><td>{n(h.pod)}</td><td>{n(h.far)}</td><td>{n(h.csi)}</td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      <p className="body-sm mute">POD is the share of observed storm cells we forecast. FAR is the share of forecast cells that had no storm. CSI combines the two, and 1 is perfect.</p>
    </>
  );
}
