import json
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_site  # noqa: E402


def read_png(path):
    """Decode the exporter's own PNGs (filter type 0 rows) -> [H, W, 4]."""
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos : pos + 4])[0]
        tag, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + n]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[i * (w * 4 + 1) + 1 : (i + 1) * (w * 4 + 1)] for i in range(h)]
    return np.frombuffer(b"".join(rows), np.uint8).reshape(h, w, 4)


def test_export_real_results_with_maps(tmp_path):
    res = tmp_path / "results"
    shutil.copytree(ROOT / "results", res)
    fid = "Bhubaneswar_20230902T0800"
    n = 24
    hot = np.zeros((n, n), np.float32)
    hot[n - 1, 3] = 0.9  # model grids are south-up: last row = northern edge
    lp = np.zeros((18, 48, 48), np.float16)
    lp[0, 24, 24] = 0.8  # the city sits at the tile centre
    np.savez(res / "india" / f"{fid}.npz", tier1_hour1_16km=hot, tier1_hour2_16km=hot, tier1_hour3_16km=hot,
             tier1_lght_prob=lp, tier1_vil=np.zeros((18, 192, 192), np.uint8))

    out = tmp_path / "site"
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"Kolkata_20240509T0800": {"hide": True}, fid: {"title": "Odisha lightning outbreak"}}))
    m = export_site.main(["--results", str(res), "--figures", str(ROOT / "figures"), "--out", str(out),
                          "--cases", str(cases)])

    ids = [f["id"] for f in m["forecasts"]]
    assert "Kolkata_20240509T0800" not in ids and fid in ids
    assert m["switch_hour"] == 3 and m["honest_label"].startswith("Trained on US GLM")
    scores = json.load(open(out / "scores.json"))
    assert scores["scorecard"][0]["tier1"] == 0.6131 and scores["scorecard"][0]["persistence"] == 0.3414

    doc = json.load(open(out / "forecasts" / f"{fid}.json"))
    assert doc["title"] == "Odisha lightning outbreak" and doc["hours"][0]["risk"] == "HIGH"
    assert doc["storm_check"]["what"].startswith("Storm-location check")
    tl, tr, br, bl = doc["tile"]["corners"]
    assert tl[1] > bl[1] and tr[0] > tl[0]  # top is north, right is east
    assert len(doc["overlays"]["steps"]) == 18 and doc["overlays"]["steps"][0]["minutes"] == 10
    assert doc["overlays"]["steps"][0]["p_location"] == 0.8

    img = read_png(out / doc["overlays"]["hourly"]["1"])
    assert img.shape == (n, n, 4)
    assert img[0, 3, 3] > 0 and img[n - 1, 3, 3] == 0  # the northern cell is drawn at the TOP of the image
    assert (img[..., 3] > 0).sum() == 1


def test_forecasts_without_maps_and_colour_ramp(tmp_path):
    res = tmp_path / "results"  # a copy without the .npz maps, which exist wherever the pipeline has run
    shutil.copytree(ROOT / "results", res, ignore=shutil.ignore_patterns("*.npz"))
    m = export_site.main(["--results", str(res), "--out", str(tmp_path / "site")])
    assert len(m["forecasts"]) == 10 and not any(f["has_maps"] for f in m["forecasts"])  # 5 GK2A + 5 INSAT
    ids = {f["id"] for f in m["forecasts"]}
    assert "Kolkata_20240509T0600_insat" in ids and "Kolkata_20240509T0600" in ids
    rgba = export_site.colorize(np.array([0.0, 0.04, 0.1, 0.5, 1.0]), export_site.LGHT_STOPS)
    assert rgba[0, 3] == 0 and rgba[1, 3] == 0 and rgba[2, 3] > 0  # transparent below 5 %, visible above
    assert rgba[2, 3] < rgba[3, 3] <= rgba[4, 3]  # opacity fades in with probability: no hard-edged holes


def test_switch_hour_rule():
    rows = [{"lead_hour": 1, "tier1": 0.6, "tier2": 0.4}, {"lead_hour": 2, "tier1": 0.3, "tier2": 0.35}]
    assert export_site.switch_hour(rows) == 1
    assert export_site.switch_hour(rows[:1]) == 1
    assert export_site.switch_hour([{"lead_hour": 1, "tier1": 0.5}]) == 1
