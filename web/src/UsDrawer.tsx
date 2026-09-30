import { useEffect, useRef } from "react";
import type { UsExample } from "./data";

// Proof on data we can score: a US test storm the model never saw, with real radar and real GLM lightning.
export default function UsDrawer(p: { us: UsExample; onClose(): void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const model = p.us.csi_by_hour.full ?? {};
  const pers = p.us.csi_by_hour.persistence ?? {};
  const hours = Object.keys(model).sort();
  return (
    <>
      <div className="scrim" onClick={p.onClose} />
      <div className="drawer wide" role="dialog" aria-modal="true" aria-label="Tested on US storms" tabIndex={-1} ref={ref}>
        <div className="panel-head">
          <h2 className="display-xs">Tested on US storms</h2>
          <button className="round" aria-label="Close" onClick={p.onClose}>×</button>
        </div>
        <p className="body-sm">
          India has no open lightning archive to score against, so we prove the model where the truth is known: US storms
          from 2019 that it never saw in training, with real radar and real lightning from the GOES-16 GLM satellite.
        </p>
        <img className="us-video" src={`data/${p.us.animation}`} alt="Animated US test storm: observed radar, forecast radar and forecast lightning chance with real lightning, 10 minutes to 3 hours ahead" />
        <p className="hint">
          Left: what the radar saw. Middle: the model's radar forecast. Right: the model's lightning chance, with real
          lightning as circles. It steps from 10 minutes to 3 hours ahead.
        </p>
        {hours.length > 0 && (
          <div className="sect">
            <p className="eyebrow">Lightning skill on all US test storms (CSI, 16 km squares, higher is better)</p>
            <table className="table">
              <thead><tr><th>Hour ahead</th><th>Model</th><th>Persistence</th></tr></thead>
              <tbody>
                {hours.map((h) => (
                  <tr key={h}>
                    <td>{h}</td>
                    <td className="ink">{model[h].toFixed(2)}</td>
                    <td>{pers[h] != null ? pers[h].toFixed(2) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint">Persistence assumes the lightning stays where it is now, the usual baseline.</p>
          </div>
        )}
      </div>
    </>
  );
}
