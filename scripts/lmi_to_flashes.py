#!/usr/bin/env python
"""FY-4A LMI corrected events (TPDC daily CSVs) -> a flash list the India lightning adapter reads.

The model's lightning channel was trained on GLM *flashes* per 8 km pixel per 5 min. LMI files hold
optical *events* (one pixel lit in one 2 ms frame), several to dozens per flash, so raw events would
inflate the input. Events are grouped into flashes the way GLM does it: an event joins a flash when it
is within 330 ms of that flash's latest event and within 16.5 km of its centroid; otherwise it starts
a new flash. Each flash is written at its first event's time and its events' centroid.

  python scripts/lmi_to_flashes.py data/fy4a_lmi/20210401.csv --bbox 20 30 86 97 \
      --out data/fy4a_lmi/flashes_20210401_ne.csv
"""

import argparse

import numpy as np
import pandas as pd

GAP_S = 0.33
RADIUS_KM = 16.5


def events(paths, bbox):
    frames = []
    for p in paths:
        d = pd.read_csv(p, usecols=["DateTime", "Latitude", "Longitude"], on_bad_lines="skip")
        d["DateTime"] = pd.to_datetime(d.DateTime, errors="coerce")
        d = d.dropna()
        lat0, lat1, lon0, lon1 = bbox
        frames.append(d[d.Latitude.between(lat0, lat1) & d.Longitude.between(lon0, lon1)])
    d = pd.concat(frames).sort_values("DateTime", kind="stable")
    t = (d.DateTime - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    return t, d.Latitude.to_numpy(float), d.Longitude.to_numpy(float)


def cluster(t, lat, lon):
    """-> list of (t_first, lat_centroid, lon_centroid, n_events)."""
    done, active = [], []  # active: [t_first, t_last, sum_lat, sum_lon, n]
    for ti, la, lo in zip(t, lat, lon):
        still = []
        for f in active:
            (still if ti - f[1] <= GAP_S else done).append(f)
        active = still
        best, best_d = None, RADIUS_KM
        for f in active:
            clat, clon = f[2] / f[4], f[3] / f[4]
            dd = np.hypot((la - clat) * 111.0, (lo - clon) * 111.0 * np.cos(np.deg2rad(clat)))
            if dd <= best_d:
                best, best_d = f, dd
        if best is None:
            active.append([ti, ti, la, lo, 1])
        else:
            best[1] = ti
            best[2] += la
            best[3] += lo
            best[4] += 1
    done += active
    return [(f[0], f[2] / f[4], f[3] / f[4], f[4]) for f in done]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+", help="TPDC FY-4A LMI daily event CSVs")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("LAT0", "LAT1", "LON0", "LON1"), default=(6, 37.5, 68, 97.5))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    t, lat, lon = events(args.csv, args.bbox)
    fl = sorted(cluster(t, lat, lon))
    df = pd.DataFrame(fl, columns=["t", "lat", "lon", "n_events"])
    df.insert(0, "time", pd.to_datetime(df.pop("t"), unit="s").dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3] + "Z")
    df.to_csv(args.out, index=False, float_format="%.4f")
    print(f"{len(t):,} events -> {len(df):,} flashes ({len(t) / max(len(df), 1):.1f} events per flash) -> {args.out}")


if __name__ == "__main__":
    main()
