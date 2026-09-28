import numpy as np
import torch
from torch.utils.data import DataLoader

from conftest import HR, LR
from nowcast.constants import DEFAULT_FRAME_OFFSETS_S, T_IN, T_OUT
from nowcast.data.dataset import NowcastDataset, prepare_batch
from nowcast.data.sevir import dequantize_ir, ir_to_celsius, lightning_to_grid, quantize_ir
from nowcast.data.shards import ShardStore, ShardWriter, decode_event, encode_event


def test_encode_roundtrip():
    a = {"x": np.arange(10, dtype=np.uint8), "y": np.ones((2, 3), np.float16), "t": np.int64(5)}
    b = decode_event(encode_event(a))
    assert set(a) == set(b)
    for k in a:
        np.testing.assert_array_equal(a[k], b[k])


def test_shard_writer_store(tmp_path):
    with ShardWriter(str(tmp_path), events_per_shard=3) as w:
        for i in range(7):
            w.add(f"E{i}", 1000 + i, {"v": np.full((4,), i, np.uint8)})
    store = ShardStore(str(tmp_path))
    assert len(store) == 7
    assert len(store.bin_paths) == 3
    for i in range(7):
        assert store.index[i]["event_id"] == f"E{i}"
        assert int(store.get(i)["v"][0]) == i


def test_lightning_binning_has_no_future_leak():
    offs = DEFAULT_FRAME_OFFSETS_S  # -7200 .. 7200 s
    # frame 24 is t=0. A flash at t=+1 s belongs to frame 25, one at t=0 to frame 24,
    # one at t=-299 s to frame 24, one at t=-300 s to frame 23.
    fl = np.array([
        [1.0, 0, 0, 3, 4],
        [0.0, 0, 0, 3, 4],
        [-299.0, 0, 0, 3, 4],
        [-300.0, 0, 0, 3, 4],
        [-7500.0, 0, 0, 3, 4],   # before the first frame window: dropped
        [0.0, 0, 0, 60, 4],      # outside the grid: dropped
    ])
    g = lightning_to_grid(fl, offs, size=48, xy_units=48)
    assert g.shape == (49, 48, 48)
    assert g[25, 4, 3] == 1 and g[24, 4, 3] == 2 and g[23, 4, 3] == 1
    assert g.sum() == 4


def test_frame_offsets_repair_real_catalog_quirks():
    from nowcast.data.sevir import frame_offsets

    std = list(range(-120, 125, 5))
    shifted = list(range(-118, 127, 5))
    dup = std.copy()
    dup[17] = -40          # "...:-45:-40:-40:-30:..." as in the real catalog
    typo = std.copy()
    typo[30] = 27          # "...:25:27:35:..."
    fmt = lambda m: ":".join(map(str, m))  # noqa: E731
    assert (frame_offsets({"minute_offsets": fmt(shifted)}) == np.array(shifted) * 60).all()
    assert (frame_offsets({"minute_offsets": fmt(dup)}) == np.array(std) * 60).all()
    assert (frame_offsets({"minute_offsets": fmt(typo)}) == np.array(std) * 60).all()
    assert (frame_offsets({"minute_offsets": float("nan")}) == np.array(std) * 60).all()


def test_lightning_xy_units_384():
    fl = np.array([[0.0, 0, 0, 100.0, 200.0]])
    g = lightning_to_grid(fl, DEFAULT_FRAME_OFFSETS_S, size=48, xy_units=384)
    assert g[24, 25, 12] == 1


def test_ir_unit_detection_and_quantization():
    c = np.linspace(-80, 30, 1000).astype(np.float32)
    np.testing.assert_allclose(ir_to_celsius((c * 100).astype(np.int16)), c, atol=0.02)
    np.testing.assert_allclose(ir_to_celsius(c + 273.15), c, atol=1e-3)
    q = quantize_ir(c, "ir107")
    assert np.abs(dequantize_ir(q, "ir107") - c).max() < 0.3


def test_dataset_shapes_and_batch(tiny_shards):
    ds = NowcastDataset(f"{tiny_shards}/train", train=True, windows_per_event=2)
    assert len(ds) == 24 and ds.hr == HR and ds.lr == LR
    s = ds[0]
    assert s["vil_in"].shape == (T_IN, HR, HR) and s["vil_out"].shape == (T_OUT, HR, HR)
    assert s["ir_in"].shape == (T_IN, 2, HR, HR)
    assert s["lght_in"].shape == (T_IN, LR, LR) and s["lght_out"].shape == (T_OUT, LR, LR)
    assert s["nwp"].shape == (ds.nwp_hours, len(ds.nwp_vars), LR, LR) and s["nwp_ok"].all()
    assert s["vil_in"].dtype == np.uint8

    b = next(iter(DataLoader(ds, batch_size=3)))
    x, y = prepare_batch(b, torch.device("cpu"))
    assert x["ir"].shape == (3, T_IN * 2, HR, HR)
    assert x["nwp"].shape == (3, ds.nwp_hours * len(ds.nwp_vars), LR, LR)
    assert 0 <= float(x["vil"].min()) and float(x["vil"].max()) <= 1
    assert set(torch.unique(y["lght"]).tolist()) <= {0.0, 1.0}


def test_eval_windows_are_deterministic_and_cover_event(tiny_shards):
    ds = NowcastDataset(f"{tiny_shards}/val", train=False, windows_per_event=3, rotate=True)
    assert [ds._start(k) for k in range(3)] == [0, 3, 6]  # 49 - 7 - 18*2 = 6 spare frames
    np.testing.assert_array_equal(ds[1]["vil_in"], ds[1]["vil_in"])


def test_nwp_hour_selection(tiny_shards):
    ds = NowcastDataset(f"{tiny_shards}/train", train=False, windows_per_event=1)
    a = ds.store.get(0)
    t0 = int(a["times"][T_IN - 1])
    out, ok = ds._nwp(a, t0)
    h0 = (t0 // 3600 * 3600 - int(a["nwp_t0"])) // 3600
    expect = (a["nwp"][h0].astype(np.float32) - ds.nwp_mean) / ds.nwp_std
    np.testing.assert_allclose(out[0].astype(np.float32), expect, atol=2e-2, rtol=1e-2)
    assert ok.all()


def test_horizon_target_alignment(tiny_shards):
    """VIL targets are frames t0+2, t0+4, ...; lightning targets sum the 2 frames of each interval."""
    ds = NowcastDataset(f"{tiny_shards}/val", train=False, windows_per_event=1, t_in=7, t_out=18, out_step=2)
    a = ds.store.get(0)
    s = ds._start(0)
    i0 = s + 6
    x = ds[0]
    np.testing.assert_array_equal(x["vil_in"], a["vil"][s : i0 + 1])
    np.testing.assert_array_equal(x["vil_out"][0], a["vil"][i0 + 2])
    np.testing.assert_array_equal(x["vil_out"][-1], a["vil"][i0 + 36])
    expect = a["lght"][i0 + 1].astype(int) + a["lght"][i0 + 2]
    np.testing.assert_array_equal(x["lght_out"][0], np.minimum(expect, 255))
    assert ds.lead_minutes[0] == 10 and ds.lead_minutes[-1] == 180
    assert ds.nwp_hours == 4 and x["nwp"].shape[0] == 4


def test_legacy_one_hour_horizon(tiny_shards):
    ds = NowcastDataset(f"{tiny_shards}/val", train=False, windows_per_event=3, t_in=13, t_out=12, out_step=1)
    x = ds[0]
    assert x["vil_in"].shape[0] == 13 and x["vil_out"].shape[0] == 12
    assert [ds._start(k) for k in range(3)] == [0, 12, 24] and ds.nwp_hours == 2


def test_horizon_too_long_is_rejected(tiny_shards):
    import pytest

    with pytest.raises(ValueError):
        NowcastDataset(f"{tiny_shards}/val", train=False, t_in=13, t_out=20, out_step=2)
