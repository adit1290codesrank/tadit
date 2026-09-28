import json
import os

import numpy as np
import torch

from conftest import LR
from nowcast import extended
from nowcast.data.hrrr import NWP_VARS, nwp_path, window_end_hours
from nowcast.data.shards import ShardStore

G = LR // 2  # tier-2 grid in the tiny tests (16 -> 8), same ratio as 48 -> 24


def _fake_nwp_cache(shard_root, nwp_root, fxx_list=(2, 3, 4)):
    """Tier-2 cache files for every (hour, fxx) the events need, plus tier-1 f01 on the 'LR' grid
    for the pooling fallback. LTNG (log1p rate) is high where the event later has lightning."""
    rng = np.random.default_rng(0)
    v, i_ltng = len(NWP_VARS), NWP_VARS.index("ltng")
    files = {}
    for split in ("train", "val"):
        st = ShardStore(os.path.join(shard_root, split))
        for i in range(len(st)):
            a, eid = st.get(i), str(st.index[i]["event_id"])
            ends = window_end_hours(a["times"])
            for V in set(ends.tolist()) | set((ends - 3600).tolist()):
                m = (a["times"] > V - 3600) & (a["times"] <= V)
                sig = a["lght"][m].sum(0).reshape(G, 2, G, 2).sum(axis=(1, 3)) if m.any() else np.zeros((G, G))
                for f in fxx_list:
                    x = rng.normal(0, 1, (v, G, G)).astype(np.float32)
                    x[i_ltng] = np.log1p(sig * 0.2)
                    files.setdefault(nwp_path(nwp_root, V, f, G), {})[eid] = x.astype(np.float16)
                files.setdefault(nwp_path(nwp_root, V, 1, 48), {})[eid] = rng.normal(0, 1, (v, LR, LR)).astype(np.float16)
    for p, d in files.items():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        np.savez(p, **d)


def test_window_end_hours():
    t = 1_530_000_000 // 3600 * 3600 + 1800 + np.arange(-120, 125, 5) * 60  # frames at hh:30 +- 2 h
    ends = window_end_hours(t)
    assert all(((t > V - 3600) & (t <= V)).sum() == 12 for V in ends)
    assert len(ends) == 3


def test_build_train_eval(tiny_shards, tmp_path):
    nwp = str(tmp_path / "nwp")
    _fake_nwp_cache(tiny_shards, nwp)
    ext = str(tmp_path / "ext")
    extended.main(["build", "--shards", tiny_shards, "--nwp", nwp, "--out", ext, "--splits", "train,val",
                   "--leads", "1,2,3", "--grid", str(G)])
    x = np.load(os.path.join(ext, "train", "x.npy"), mmap_mode="r")
    lead = np.load(os.path.join(ext, "train", "lead.npy"))
    assert x.shape[1:] == (2, len(NWP_VARS), G, G)
    assert set(lead.tolist()) == {1, 2, 3}  # lead 1 used the pooled tier-1 f01 fallback for V-1h

    r = extended.main(["train", "--data", ext, "--out", str(tmp_path / "run"), "--epochs", "2",
                       "--batch-size", "8", "--workers", "0", "--lr", "3e-3"])
    assert r["epochs"] == 2 and os.path.exists(tmp_path / "run" / "best.pt")

    res = extended.main(["eval", "--ckpt", str(tmp_path / "run" / "best.pt"), "--data", os.path.join(ext, "val"),
                         "--out", str(tmp_path / "ext.json"), "--workers", "0"])
    assert set(res["lead_hour"]) == {"1", "2", "3"}
    for r in res["lead_hour"].values():
        assert {"model", "hrrr_ltng", "hrrr_refc", "base_rate"} <= set(r)
    json.load(open(tmp_path / "ext.json"))


def test_extnet_shapes():
    m = extended.ExtNet(extended.ExtConfig(in_ch=24, max_lead=6, chs=(16, 32), cond_dim=16))
    out = m(torch.randn(3, 24, 24, 24), torch.tensor([1, 4, 6]), torch.randn(3, 2))
    assert out["lght"].shape == (3, 24, 24) and out["vil"].shape == (3, 24, 24)
