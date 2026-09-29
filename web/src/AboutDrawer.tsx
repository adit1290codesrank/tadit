import { useEffect, useRef } from "react";
import { dayHm, utcToIst, type Forecast, type Manifest } from "./data";

const REPO = "https://github.com/adit1290codesrank/sih2026";
const INPUT_NAMES: Record<string, string> = { ir: "Satellite", vil: "Radar", lght: "Lightning", nwp: "Weather model" };

export default function AboutDrawer(p: { manifest: Manifest; f: Forecast | null; description: string; onClose(): void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const m = p.manifest.model;
  return (
    <>
      <div className="scrim" onClick={p.onClose} />
      <div className="drawer" role="dialog" aria-modal="true" aria-label="About this forecast" tabIndex={-1} ref={ref}>
        <div className="panel-head">
          <h2 className="display-xs">About</h2>
          <button className="round" aria-label="Close" onClick={p.onClose}>×</button>
        </div>

        <details open>
          <summary className="eyebrow">This forecast</summary>
          <div className="sect">
            {p.f ? (
              <>
                <p className="ink">{p.f.title}</p>
                {p.description && <p>{p.description}</p>}
                <dl className="kv">
                  <dt className="caption-mono-sm mute">Issued</dt>
                  <dd>{dayHm(p.f.issue_ist)} IST ({p.f.issue_utc.replace("T", " ")} UTC)</dd>
                  <dt className="caption-mono-sm mute">Valid until</dt>
                  <dd>{dayHm(p.f.valid_until_ist)} IST</dd>
                  {p.f.model_inputs_used && (
                    <>
                      <dt className="caption-mono-sm mute">Inputs used</dt>
                      <dd>{Object.entries(p.f.model_inputs_used).map(([k, on]) => `${INPUT_NAMES[k] ?? k}: ${on ? "yes" : "no"}`).join(" · ")}</dd>
                    </>
                  )}
                  <dt className="caption-mono-sm mute">Trained on</dt>
                  <dd>{p.f.honest_label}</dd>
                  <dt className="caption-mono-sm mute">Models</dt>
                  <dd>
                    Nowcast model, first 3 hours: {fmt(m.tier1)}.<br />
                    Outlook model, hours 4 to 6: {fmt(m.tier2)}.
                  </dd>
                </dl>
              </>
            ) : <p>Click a place on the map to see details for its forecast.</p>}
          </div>
        </details>

        <details>
          <summary className="eyebrow">Data sources</summary>
          <div className="sect">
            <ul>
              <li><span className="ink">INSAT-3DR/3DS (MOSDAC)</span> is the main satellite input. On real files it tracks GK2A closely (correlation 0.87 for infrared, 0.84 for water vapour) and reads about 2.7 K warmer.</li>
              <li><span className="ink">GK2A (NOAA open data)</span> is used to cross-check each forecast and as the reference for the storm check.</li>
              <li><span className="ink">GFS 0.25°</span> supplies the weather model fields. We have checked it over India.</li>
              <li><span className="ink">IMD radar</span> images are public and the data is available on request. The code to read it is ready but not connected.</li>
              <li>We have requested data from the <span className="ink">Indian lightning network (ILDN)</span>. The code to read it is ready.</li>
              <li><span className="ink">ISS-LIS</span>, a lightning sensor on the space station, is only for checking forecasts. We have not run it on real files yet.</li>
            </ul>
            <p>There is no open archive of Indian lightning, so the model learned from US lightning data (GOES-16 GLM).</p>
          </div>
        </details>

        <details>
          <summary className="eyebrow">Limits</summary>
          <div className="sect">
            <ul>
              <li>We have not yet checked the forecasts against Indian lightning. That needs ILDN or ISS-LIS data.</li>
              <li>The model finds where storms are, but its percentages are calibrated on US storms and need Indian data before they can be trusted.</li>
              <li>Indian radar and lightning feeds are not connected yet.</li>
            </ul>
            <p>Next we plan to add IMD radar, get an extract of ILDN data and recalibrate.</p>
          </div>
        </details>

        <details>
          <summary className="eyebrow">About the storm check</summary>
          <div className="sect">
            <p>We have no Indian lightning data to score against yet. As a stand-in, the storm check compares where we forecast lightning with where the satellite saw very cold cloud tops, a sign of deep thunderstorms.</p>
            <p>So it tells you whether we put storms in the right place. It does not confirm lightning.</p>
            {p.f?.storm_check?.proxy && <p className="mute">{p.f.storm_check.proxy}</p>}
          </div>
        </details>

        <details>
          <summary className="eyebrow">Map boundaries</summary>
          <div className="sect">
            <p>{p.manifest.boundary
              ? "State and national boundaries are from the Survey of India, the official depiction."
              : "Boundaries are not shown because this export did not include the Survey of India file."}</p>
          </div>
        </details>

        <details>
          <summary className="eyebrow">Credits</summary>
          <div className="sect">
            <p>Built for Smart India Hackathon 2026, problem SIH26072 (Ministry of Earth Sciences / India Meteorological Department).</p>
            <p><a href={REPO} target="_blank" rel="noreferrer">Source code</a></p>
            <p className="mute">Data exported {utcToIst(p.manifest.generated_utc).replace("T", " ")} IST.</p>
          </div>
        </details>
      </div>
    </>
  );
}

function fmt(r: Record<string, unknown>) {
  const parts = [];
  if (r.step != null) parts.push(`${Number(r.step).toLocaleString("en-IN")} training steps`);
  if (r.samples != null) parts.push(`${Number(r.samples).toLocaleString("en-IN")} samples`);
  if (r.epoch != null) parts.push(`epoch ${r.epoch}`);
  return parts.join(", ") || "no details available";
}
