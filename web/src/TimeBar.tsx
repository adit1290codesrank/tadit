import { useRef } from "react";
import { addMin, hm } from "./data";

// One timeline: dense 10-min ticks for the first hours, sparse hourly ticks after the seam (FRAME §5).
export default function TimeBar(p: {
  positions: number[]; t: number; issueIst: string | null; seam: number | null;
  playing: boolean; onT(t: number): void; onPlay(on: boolean): void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const max = 360;
  const x = (m: number) => `${(m / max) * 100}%`;

  const pick = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    const m = ((clientX - r.left) / r.width) * max;
    const near = p.positions.reduce((a, b) => (Math.abs(b - m) < Math.abs(a - m) ? b : a), p.positions[0]);
    if (near != null) p.onT(near);
  };
  const step = (d: number) => {
    const i = p.positions.indexOf(p.t) + d;
    if (i >= 0 && i < p.positions.length) p.onT(p.positions[i]);
  };

  return (
    <div className="timebar">
      <button className="round" aria-label={p.playing ? "Pause" : "Play"} onClick={() => p.onPlay(!p.playing)} disabled={!p.positions.length}>
        {p.playing ? "❚❚" : "▶"}
      </button>
      <div
        className="track" ref={track} role="slider" tabIndex={0} aria-label="Forecast time"
        aria-valuemin={p.positions[0]} aria-valuemax={p.positions.at(-1)} aria-valuenow={p.t}
        aria-valuetext={p.issueIst ? `${hm(addMin(p.issueIst, p.t))} IST` : undefined}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); p.onPlay(false); pick(e.clientX); }}
        onPointerMove={(e) => { if (e.buttons) pick(e.clientX); }}
        onKeyDown={(e) => { if (e.key === "ArrowRight") step(1); if (e.key === "ArrowLeft") step(-1); }}
      >
        {p.seam != null && <div className="seam" style={{ left: x(p.seam) }}><span className="caption-mono-sm">outlook</span></div>}
        {p.positions.map((m) => (
          <div key={m} className={`tick${m % 60 === 0 ? " hour" : ""}${m === p.t ? " on" : ""}`} style={{ left: x(m) }} />
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((h) => (
          <span key={h} className={`tlabel caption-mono-sm${h % 3 ? " minor" : ""}`} style={{ left: x(h * 60) }}>
            {p.issueIst ? hm(addMin(p.issueIst, h * 60)) : `${h} h`}
          </span>
        ))}
        {p.positions.length > 0 && <div className="cursor" style={{ left: x(p.t) }} />}
      </div>
      <span className="now">
        <span className="caption-mono-sm">{p.issueIst ? `+${p.t} min · ${hm(addMin(p.issueIst, p.t))} IST` : ""}</span>
        <span className="hint" style={{ display: "block" }}>Drag or press play. The first 3 hours step every 10 minutes.</span>
      </span>
    </div>
  );
}
