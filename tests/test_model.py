import torch

from conftest import HR, LR, tiny_model_cfg
from nowcast.constants import OUT_STEP, T_IN, T_OUT, nwp_hours_for
from nowcast.losses import lightning_loss, total_loss, vil_weights
from nowcast.metrics import LightningMetrics, VILMetrics
from nowcast.model import FusionNowcaster


def fake_inputs(B=2, V=12, nwp_ok=True):
    return {
        "vil": torch.rand(B, T_IN, HR, HR),
        "ir": torch.rand(B, T_IN * 2, HR, HR),
        "lght": torch.rand(B, T_IN, LR, LR),
        "nwp": torch.randn(B, nwp_hours_for(T_OUT, OUT_STEP) * V, LR, LR),
        "tod": torch.randn(B, 2),
        "present": {"nwp": torch.full((B,), nwp_ok)},
    }


def test_forward_shapes_full_and_radar_only():
    for mods in [("vil", "ir", "lght", "nwp"), ("vil",), ("ir", "lght")]:
        m = FusionNowcaster(tiny_model_cfg(modalities=mods))
        out = m(fake_inputs())
        assert out["vil"].shape == (2, T_OUT, HR, HR)
        assert out["lght"].shape == (2, T_OUT, LR, LR)
    radar = FusionNowcaster(tiny_model_cfg(modalities=("vil",)))
    assert not hasattr(radar, "nwp_enc") and set(radar.stems) == {"vil"}


def test_two_level_unet():
    m = FusionNowcaster(tiny_model_cfg(chs=(16, 32)))
    out = m(fake_inputs())
    assert out["lght"].shape == (2, T_OUT, LR, LR)


def test_missing_modalities_change_output_and_backprop():
    torch.manual_seed(0)
    m = FusionNowcaster(tiny_model_cfg()).eval()
    x = fake_inputs()
    with torch.no_grad():
        a = m(x)["vil"]
        b = m(x, force_missing=("ir",))["vil"]
        c = m(fake_inputs(nwp_ok=False) | {k: x[k] for k in ("vil", "ir", "lght", "tod")})["vil"]
    assert not torch.allclose(a, b) and torch.isfinite(c).all()

    m.train()
    out = m(x, drop_p=0.9)
    loss, _ = total_loss(out, {"vil": torch.rand(2, T_OUT, HR, HR),
                               "lght": (torch.rand(2, T_OUT, LR, LR) > 0.9).float()})
    loss.backward()
    assert all(p.grad is not None for n, p in m.named_parameters() if "stems" in n)


def test_modality_dropout_keeps_one_observation():
    m = FusionNowcaster(tiny_model_cfg())
    B = 256
    present = {k: torch.ones(B, dtype=torch.bool) for k in m.modalities}
    out = m._modality_dropout(present, p=0.95)
    any_obs = torch.stack([out[k] for k in m.obs], 1).any(1)
    assert any_obs.all()
    assert (~out["nwp"]).any()


def test_losses():
    t = torch.tensor([0.0, 20, 80, 140, 170, 190, 230]) / 255
    w = vil_weights(t)
    assert w.tolist() == [1, 2, 5, 10, 20, 30, 40]
    logits = torch.full((1, 2, 8, 8), -3.0)
    tgt = torch.zeros(1, 2, 8, 8)
    tgt[0, 0, 4, 4] = 1
    assert lightning_loss(logits, tgt, dilate=1) > lightning_loss(logits, tgt, dilate=0)


def test_metrics_perfect_and_empty():
    vm = VILMetrics(T_OUT, pools=(1, 4))
    y = torch.zeros(2, T_OUT, 16, 16)
    y[:, :, 4:8, 4:8] = 200 / 255
    vm.update(y, y)
    r = vm.compute()
    assert r["pool1"]["csi_per_threshold"]["181"] == 1.0
    assert r["mse"] == 0.0

    lm = LightningMetrics(T_OUT)
    tg = (torch.rand(2, T_OUT, 8, 8) > 0.8).float()
    lm.update(tg, tg)
    r = lm.compute()
    assert r["tol0"]["csi"] == 1.0 and r["brier"] == 0.0


def test_lead_hour_lightning_bins():
    from nowcast.metrics import LeadHourLightning

    leads = [10 * (k + 1) for k in range(18)]
    m = LeadHourLightning(leads, pool=2)
    assert {h: len(v) for h, v in m.bins.items()} == {1: 6, 2: 6, 3: 6}
    t = torch.zeros(2, 18, 8, 8)
    t[:, 7, 2, 3] = 1  # lightning at 80 min -> hour 2
    m.update(t.clone(), t)
    r = m.compute()
    assert r["2"]["csi"] == 1.0 and r["2"]["base_rate"] > 0 and r["1"]["base_rate"] == 0
