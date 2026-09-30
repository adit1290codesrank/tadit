import { useEffect, useRef, useState } from "react";
import { dayHm, hm, riskShort, type Run } from "./data";

export const BRAND = "Tadit"; // तड़ित, lightning

export default function TopBar(p: {
  runs: Run[]; run: Run | null; validUntil: string | null; onRun(key: string): void; onAbout(): void; onUs?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc, true);
    return () => { document.removeEventListener("mousedown", close); window.removeEventListener("keydown", esc, true); };
  }, [open]);

  return (
    <header className="topbar">
      <div className="brand">
        <span className="display-xs">{BRAND}</span>
        <span className="eyebrow mute">SIH26072</span>
      </div>
      <div className="runpicker" ref={box}>
        {p.run ? (
          <button className="pill" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
            Issued {dayHm(p.run.issue_ist)} IST <span aria-hidden>▾</span>
          </button>
        ) : <span className="skeleton" style={{ width: 240, height: 38 }} />}
        {p.validUntil && <span className="valid">Valid until {hm(p.validUntil)} IST</span>}
        {p.run?.archived && <span className="chip" title="A past forecast, shown as it was issued">archived</span>}
        {open && (
          <ul className="runlist card" role="listbox" aria-label="Forecast runs">
            {p.runs.map((r) => (
              <li key={r.key}>
                <button aria-current={r.key === p.run?.key} onClick={() => { setOpen(false); p.onRun(r.key); }}>
                  <span>{dayHm(r.issue_ist)} IST</span>
                  {r.peak && <span className={`chip ${r.peak}`}>{riskShort(r.peak)}</span>}
                  <span className="body-sm mute">{r.regions.map((x) => x.city).join(", ")}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <span className="spacer" />
      <span className="lang-slot" aria-hidden />
      {p.onUs && <button className="pill" onClick={p.onUs}>Tested on US storms</button>}
      <button className="round" aria-label="About this forecast" onClick={p.onAbout}>i</button>
    </header>
  );
}
