import datetime as dt
import json
import os
import types

import numpy as np
import pytest
import torch

from nowcast.data.dataset import GFS_MISSING_VARS, gfs_like, insat_like
from nowcast.data.hrrr import NWP_VARS
from nowcast.india import gfs, insat, lightning, radar
from nowcast.india.tiles import CITIES, city_tile, latlon_to_pixel, tile_grid

BBS = CITIES["Bhubaneswar"]


def write_l1b(path, when: dt.datetime, cold_at=BBS, step4=0.04):
    """Fake INSAT-3DR L1B_STD file in the MOSDAC layout (as read by satpy's insat3d_img_l1b_h5)."""
    import h5py

    def grid(step):
        la = np.arange(BBS[0] - 5, BBS[0] + 5, step)[::-1]  # north-up like the real full disk
        lo = np.arange(BBS[1] - 5, BBS[1] + 5, step)
        return np.meshgrid(la, lo, indexing="ij")

    lut = 180.0 + 0.12 * np.arange(1024)  # K
    with h5py.File(path, "w") as f:
        f.attrs["Acquisition_Start_Time"] = np.bytes_(when.strftime("%d-%b-%YT%H:%M:%S"))
        for var, latn, lonn, step in (("IMG_TIR1", "Latitude", "Longitude", step4),
                                      ("IMG_WV", "Latitude_WV", "Longitude_WV", 2 * step4)):
            lat, lon = grid(step)
            d2 = (lat - cold_at[0]) ** 2 + (lon - cold_at[1]) ** 2
            counts = np.where(d2 < 0.5, 50, 900).astype(np.uint16)  # 186 K core, 288 K elsewhere
            counts[0, 0] = 0  # fill
            ds = f.create_dataset(var, data=counts[None])
            ds.attrs["_FillValue"] = np.uint16(0)
            f.create_dataset(var + "_TEMP", data=lut)
            for name, arr in ((latn, lat), (lonn, lon)):
                q = f.create_dataset(name, data=np.round(arr / 0.01).astype(np.int16))
                q.attrs["scale_factor"] = np.float32(0.01)
                q.attrs["_FillValue"] = np.int16(32767)


def test_tiles_centre_and_orientation():
    t = city_tile("Bhubaneswar")
    r, c = latlon_to_pixel(t, *BBS, 48)
    assert abs(r - 24) < 0.01 and abs(c - 24) < 0.01
    lat, _ = tile_grid(t, 48)
    assert lat[0].mean() < lat[-1].mean()  # row 0 = south, as in the SEVIR training data


def test_insat_reader_and_tile(tmp_path):
    p = tmp_path / "3RIMG_10MAY2024_0900_L1B_STD_V01R00.h5"
    write_l1b(p, dt.datetime(2024, 5, 10, 9, 0))
    bt, lat, lon = insat.read_channel(str(p), "ir107")
    assert np.isnan(bt[0, 0]) and np.nanmin(bt) == pytest.approx(186.0) and abs(np.nanmax(lat) - (BBS[0] + 5)) < 0.1
    tb = insat.to_tile(bt, lat, lon, city_tile("Bhubaneswar"), 48)
    assert tb[24, 24] == pytest.approx(186.0, abs=1) and tb[2, 2] == pytest.approx(288.0, abs=1)


def test_insat_frames_sample_and_hold(tmp_path):
    t0 = dt.datetime(2024, 5, 10, 9, 0)
    for m in (40, 10):
        write_l1b(tmp_path / f"3RIMG_{m}.h5", t0 - dt.timedelta(minutes=m))
    scans = insat.find_scans(str(tmp_path))
    frames, prov = insat.insat_frames(scans, city_tile("Bhubaneswar"), t0, 7, 48)
    assert frames.shape == (7, 2, 48, 48) and len(prov) == 2
    assert frames[-1, 1, 24, 24] < 20  # cold core -> low quantised value
    none, prov = insat.insat_frames(scans, city_tile("Bhubaneswar"), t0 + dt.timedelta(hours=2), 7, 48)
    assert none is None and prov[0]["status"] == "missing"


def test_gfs_mapping():
    s = (4, 5)
    g = {k: np.full(s, v, np.float32) for k, v in dict(
        cape_sfc=1000, cape_mu=1500, cin_sfc=-50, lftx=-4, pwat=50, hlcy03=150, refc=40, tmp700=283.15,
        rh700=100, tmp500=263.15, u500=20, v500=0, u10=5, v10=0).items()}
    from nowcast.data.hrrr import derive

    f = derive(gfs.to_model_fields(g), s)
    v = dict(zip(NWP_VARS, f[:, 0, 0]))
    assert v["shear06"] == pytest.approx(15.0)
    assert v["dd700"] == pytest.approx(0.0, abs=0.05)  # RH 100% -> no dewpoint depression
    assert np.isnan(v["ltng"]) and np.isnan(v["uh25"])
    assert gfs.cycle_for(dt.datetime(2024, 5, 10, 9, 30)) == dt.datetime(2024, 5, 10, 0)


def test_lightning_csv(tmp_path):
    p = tmp_path / "illn.csv"
    p.write_text("Datetime,Latitude,Longitude\n2024-05-10 08:58:00,20.296,85.825\n2024-05-10 08:50:00,40,85\n")
    s = lightning.read_strikes(str(p))
    t0 = int(dt.datetime(2024, 5, 10, 9, 0, tzinfo=dt.timezone.utc).timestamp())
    g = lightning.grid_strikes(s, city_tile("Bhubaneswar"), np.array([t0 - 300, t0]), 48)
    assert g[1, 24, 24] == 1 and g.sum() == 1


def test_radar_vil_scale_roundtrip():
    x = np.arange(20, 250)
    assert np.abs(radar.vil_digital(radar.vil_kgm2_from_digital(x)).astype(int) - x).max() <= 1
    assert radar.vil_digital(radar.vil_kgm2_from_dbz(np.array([10.0])))[0] < radar.vil_digital(
        radar.vil_kgm2_from_dbz(np.array([55.0])))[0]


def test_india_training_augmentation():
    rng = np.random.default_rng(0)
    ir = np.random.default_rng(1).integers(0, 255, (7, 2, 16, 16)).astype(np.uint8)
    out = insat_like(ir, start=3, rng=rng)
    assert out.shape == ir.shape
    assert (out[:, 0].reshape(7, 4, 4, 4, 4).std(axis=(2, 4)) == 0).all()  # WV at 8 km = 4x4 blocks
    assert len({out[j].tobytes() for j in range(7)}) < 7  # scans held over several frames
    nwp = np.random.default_rng(2).normal(size=(3, len(NWP_VARS), 8, 8)).astype(np.float16)
    g = gfs_like(nwp, [NWP_VARS.index(v) for v in GFS_MISSING_VARS])
    assert (g[:, NWP_VARS.index("ltng")] == 0).all() and g.std() < nwp.std()


def test_india_run_end_to_end(tmp_path, tiny_shards):
    from conftest import tiny_model_cfg
    from nowcast.data.shards import ShardStore
    from nowcast.extended import ExtConfig, ExtNet
    from nowcast.india import run as india_run
    from nowcast.model import FusionNowcaster

    stats = ShardStore(f"{tiny_shards}/train").stats()
    cfg = tiny_model_cfg()
    m = FusionNowcaster(cfg)
    from dataclasses import asdict

    torch.save({"ema": m.state_dict(), "model_cfg": asdict(cfg), "nwp_stats": stats,
                "config": {"data": {"t_in": cfg.t_in, "t_out": cfg.t_out, "out_step": 2}}}, tmp_path / "t1.pt")
    ecfg = ExtConfig(in_ch=2 * len(NWP_VARS), max_lead=6, chs=(16, 32), cond_dim=16)
    torch.save({"model": ExtNet(ecfg).state_dict(), "cfg": asdict(ecfg), "stats": stats}, tmp_path / "t2.pt")

    t0 = dt.datetime(2024, 5, 10, 9, 0)
    sat = tmp_path / "insat"
    sat.mkdir()
    write_l1b(sat / "a.h5", t0 - dt.timedelta(minutes=20))
    (tmp_path / "s.csv").write_text("time,lat,lon\n2024-05-10T08:57:00Z,20.3,85.8\n")
    la, lo = np.meshgrid(np.linspace(15, 26, 45), np.linspace(80, 91, 45), indexing="ij")
    np.savez(tmp_path / "r.npz", dbz=np.where((la - BBS[0]) ** 2 + (lo - BBS[1]) ** 2 < 1, 50.0, np.nan), lat=la, lon=lo)

    def fake_gfs(valid, issue):
        glat, glon = np.meshgrid(np.arange(10, 30, 0.25), np.arange(75, 95, 0.25), indexing="ij")
        f = np.random.default_rng(0).normal(0, 1, (len(NWP_VARS), *glat.shape)).astype(np.float32)
        return f, glat, glon, {"model": "gfs(fake)", "valid": valid.isoformat(), "status": "ok"}

    args = types.SimpleNamespace(time=t0.isoformat(), city="Bhubaneswar", lat=None, lon=None,
                                 insat_dir=str(sat), radar_npz=str(tmp_path / "r.npz"),
                                 lightning_csv=str(tmp_path / "s.csv"), tier1=str(tmp_path / "t1.pt"),
                                 tier2=str(tmp_path / "t2.pt"), switch_hour=2, hr=64, out=str(tmp_path / "out"))
    out = india_run.run(args, gfs_fetch=fake_gfs)
    assert out["tier1"]["inputs_present"] == {"ir": True, "vil": True, "lght": True, "nwp": True}
    assert [s["source"] for s in out["summary"]] == ["tier1"] * 2 + ["tier2"] * 4
    rep = json.load(open(os.path.join(args.out, "Bhubaneswar_20240510T0900.json")))
    assert rep["provenance"]["satellite"]["status"] == "live" and rep["provenance"]["radar"]["status"] == "approximate"

    # no INSAT, no radar, no lightning: the model still runs on what India always has (GFS)
    args2 = types.SimpleNamespace(**{**vars(args), "insat_dir": None, "radar_npz": None, "lightning_csv": None})
    out2 = india_run.run(args2, gfs_fetch=fake_gfs)
    assert out2["tier1"]["inputs_present"] == {"ir": False, "vil": False, "lght": False, "nwp": True}
    assert len(out2["summary"]) == 6


def test_iss_lis_to_csv(tmp_path):
    import h5py

    p = tmp_path / "ISS_LIS_SC_V2.2_20240510_085500_NQC.nc"
    t_unix = dt.datetime(2024, 5, 10, 8, 58, tzinfo=dt.timezone.utc).timestamp()
    with h5py.File(p, "w") as f:
        f["lightning_flash_lat"] = np.array([20.3, 51.0], np.float32)   # India, Europe
        f["lightning_flash_lon"] = np.array([85.8, 0.1], np.float32)
        f["lightning_flash_TAI93_time"] = np.array([t_unix - lightning.TAI93_TO_UNIX] * 2)
    n = lightning.iss_lis_to_csv([str(p)], str(tmp_path / "lis.csv"))
    s = lightning.read_strikes(str(tmp_path / "lis.csv"))
    assert n == 1 and abs(int(s.t.iloc[0]) - int(t_unix)) <= 1


def write_gk2a(folder, when: dt.datetime, n=550):
    """Small fake GK2A full disk (real file attributes, 10x coarser grid) with a cold spot over Bhubaneswar."""
    import h5py
    import pyproj

    attrs = dict(earth_equatorial_radius=6378137.0, earth_polar_radius=6356752.3, nominal_satellite_height=42164000.0,
                 sub_longitude=np.deg2rad(128.2), cfac=20425338.90333935 / 10, lfac=-20425338.90333935 / 10,
                 coff=n / 2 + 0.5, loff=n / 2 + 0.5, DN_to_Radiance_Gain=-0.0198197, DN_to_Radiance_Offset=161.58013916,
                 Teff_to_Tbb_c0=-0.14286645, Teff_to_Tbb_c1=1.0006407, Teff_to_Tbb_c2=-5.50443295e-07,
                 light_speed=2.99792458e08, Boltzmann_constant_k=1.3806488e-23, Plank_constant_h=6.62606957e-34)
    h = attrs["nominal_satellite_height"] - attrs["earth_equatorial_radius"]
    p = pyproj.Proj(f"+proj=geos +h={h} +lon_0=128.2 +a=6378137.0 +b=6356752.3 +sweep=y")
    x, y = p(BBS[1], BBS[0])
    col = int(np.rad2deg(x / h) * attrs["cfac"] / 2**16 + attrs["coff"] - 1)
    row = int(np.rad2deg(y / h) * attrs["lfac"] / 2**16 + attrs["loff"] - 1)
    for band in ("ir105", "wv069"):
        dn = np.full((n, n), 5000, np.uint16)
        dn[row - 2 : row + 3, col - 2 : col + 3] = 7500  # lower radiance (negative gain) -> colder
        with h5py.File(os.path.join(folder, f"gk2a_ami_le1b_{band}_fd020ge_{when:%Y%m%d%H%M}.nc"), "w") as f:
            f.attrs.update({k: np.array([v]) for k, v in attrs.items()})
            d = f.create_dataset("image_pixel_values", data=dn)
            d.attrs["number_of_valid_bits_per_pixel"] = np.array([13], np.uint8)


def test_gk2a_reader_and_frames(tmp_path):
    from nowcast.india import gk2a

    t0 = dt.datetime(2024, 5, 10, 9, 0)
    for m in (20, 10, 0):
        write_gk2a(str(tmp_path), t0 - dt.timedelta(minutes=m))
    scans = gk2a.find_scans(str(tmp_path))
    assert len(scans) == 3
    tile = city_tile("Bhubaneswar")
    bt = gk2a.read_tile(scans[-1][1]["ir105"], 10.35, tile, 48)
    assert np.isfinite(bt).all() and 180 < np.nanmin(bt) < bt[2, 2] < 330
    assert bt[24, 24] < bt[2, 2] - 5  # the cold spot lands at the tile centre
    frames, prov = gk2a.gk2a_frames(scans, tile, t0, 7, 48)
    assert frames.shape == (7, 2, 48, 48) and len(prov) == 3
