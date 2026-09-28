"""Mid-fusion U-Net with NWP cross-attention.

  VIL  [B, T, H, W]     -> stem (stride 2) ─┐
  IR   [B, T*C, H, W]   -> stem (stride 2) ─┼─ ModalityFusion (gates + learned "missing" embeddings)
  LGHT [B, T, H/4, W/4] -> stem (up x2)   ─┘            │
                                         U-Net encoder H/2 -> H/4 -> H/8 -> H/16
  NWP  [B, h*V, H/4, W/4] -> CNN -> tokens at H/16 ──> bottleneck: self-attn + cross-attn(obs -> NWP)
                                         U-Net decoder with FiLM(time of day, pooled NWP, presence mask)
  heads: VIL [B, T_out, H, W] (PixelShuffle from H/2); lightning logits [B, T_out, H/4, W/4]

All lead times are predicted at once (no autoregression). Modalities not listed in
`ModelConfig.modalities` are not instantiated (e.g. the radar-only control).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..constants import OUT_STEP, T_IN, T_OUT, nwp_hours_for

OBS = ("vil", "ir", "lght")


@dataclass
class ModelConfig:
    t_in: int = T_IN
    t_out: int = T_OUT
    ir_channels: int = 2
    nwp_vars: int = 12
    nwp_hours: int = nwp_hours_for(T_OUT, OUT_STEP)
    modalities: tuple = ("vil", "ir", "lght", "nwp")
    stem_ch: int = 64
    chs: tuple = (128, 256, 384, 512)
    enc_blocks: int = 2
    dec_blocks: int = 2
    attn_depth: int = 4
    heads: int = 8
    cond_dim: int = 256
    lght_bias_init: float = -4.0

    def __post_init__(self):
        self.modalities = tuple(self.modalities)
        self.chs = tuple(self.chs)
        unknown = set(self.modalities) - set(OBS) - {"nwp"}
        assert not unknown, f"unknown modalities {unknown}"
        assert any(m in self.modalities for m in OBS), "need at least one observation modality"
        assert len(self.chs) >= 2


def _groups(c: int) -> int:
    return math.gcd(32, c)


class ResBlock(nn.Module):
    def __init__(self, cin: int, cout: int, cond_dim: int = 0):
        super().__init__()
        self.n1 = nn.GroupNorm(_groups(cin), cin)
        self.c1 = nn.Conv2d(cin, cout, 3, padding=1)
        self.n2 = nn.GroupNorm(_groups(cout), cout)
        self.c2 = nn.Conv2d(cout, cout, 3, padding=1)
        self.skip = nn.Conv2d(cin, cout, 1) if cin != cout else nn.Identity()
        self.film = None
        if cond_dim:
            self.film = nn.Linear(cond_dim, 2 * cout)
            nn.init.zeros_(self.film.weight)
            nn.init.zeros_(self.film.bias)

    def forward(self, x, cond=None):
        h = self.c1(F.silu(self.n1(x)))
        h = self.n2(h)
        if self.film is not None and cond is not None:
            s, b = self.film(cond)[:, :, None, None].chunk(2, dim=1)
            h = h * (1 + s) + b
        h = self.c2(F.silu(h))
        return self.skip(x) + h


class Stem(nn.Module):
    """Time folded into channels -> features at the fusion resolution (H/2)."""

    def __init__(self, cin: int, cout: int, resample: str):
        super().__init__()
        self.inp = nn.Conv2d(cin, cout, 3, padding=1)
        self.block = ResBlock(cout, cout)
        if resample == "down":
            self.resample = nn.Conv2d(cout, cout, 3, stride=2, padding=1)
        elif resample == "up":
            self.resample = nn.Sequential(nn.Upsample(scale_factor=2, mode="nearest"),
                                          nn.Conv2d(cout, cout, 3, padding=1))
        else:
            self.resample = nn.Identity()

    def forward(self, x):
        return self.resample(self.block(self.inp(x)))


class ModalityFusion(nn.Module):
    """Concat of per-modality features, each gated by a squeeze-excitation over all of them.
    A missing modality is replaced by a learned embedding, never by zeros the net must interpret."""

    def __init__(self, names: tuple, c: int, cout: int):
        super().__init__()
        self.names = names
        n = len(names)
        self.missing = nn.ParameterDict({m: nn.Parameter(torch.zeros(1, c, 1, 1)) for m in names})
        self.gate = nn.Sequential(nn.Linear(n * c + n, c), nn.SiLU(), nn.Linear(c, n * c))
        self.proj = nn.Conv2d(n * c, cout, 1)

    def forward(self, feats: dict, present: dict):
        es, ms = [], []
        for m in self.names:
            p = present[m].to(feats[m].dtype).view(-1, 1, 1, 1)
            es.append(feats[m] * p + self.missing[m].to(feats[m].dtype) * (1 - p))
            ms.append(present[m].to(feats[m].dtype))
        z = torch.cat(es, 1)
        pooled = torch.cat([z.mean((2, 3)), torch.stack(ms, 1)], 1)
        g = torch.sigmoid(self.gate(pooled))[:, :, None, None]
        return self.proj(z * g)


class AttnBlock(nn.Module):
    def __init__(self, d: int, heads: int, cross: bool, mlp: int = 4):
        super().__init__()
        self.n1 = nn.LayerNorm(d)
        self.sa = nn.MultiheadAttention(d, heads, batch_first=True)
        self.cross = cross
        if cross:
            self.n2 = nn.LayerNorm(d)
            self.nkv = nn.LayerNorm(d)
            self.ca = nn.MultiheadAttention(d, heads, batch_first=True)
        self.n3 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(nn.Linear(d, mlp * d), nn.GELU(), nn.Linear(mlp * d, d))

    def forward(self, x, ctx=None):
        h = self.n1(x)
        x = x + self.sa(h, h, h, need_weights=False)[0]
        if self.cross and ctx is not None:
            h, c = self.n2(x), self.nkv(ctx)
            x = x + self.ca(h, c, c, need_weights=False)[0]
        return x + self.mlp(self.n3(x))


class NWPEncoder(nn.Module):
    """[B, hours*V, H/4, W/4] -> tokens [B, N, d] at H/16, plus a pooled vector."""

    def __init__(self, cin: int, d: int):
        super().__init__()
        c1, c2 = max(d // 4, 32), max(d // 2, 32)
        self.net = nn.Sequential(
            nn.Conv2d(cin, c1, 3, padding=1), ResBlock(c1, c1),
            nn.Conv2d(c1, c2, 3, stride=2, padding=1), ResBlock(c2, c2),
            nn.Conv2d(c2, d, 3, stride=2, padding=1), ResBlock(d, d),
        )
        self.pos = nn.Conv2d(d, d, 3, padding=1, groups=d)

    def forward(self, x):
        h = self.net(x)
        h = h + self.pos(h)
        t = h.flatten(2).transpose(1, 2)
        return t, t.mean(1)


class FusionNowcaster(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.modalities = cfg.modalities
        self.obs = tuple(m for m in OBS if m in cfg.modalities)
        self.use_nwp = "nwp" in cfg.modalities and cfg.nwp_vars > 0
        chs, sc = cfg.chs, cfg.stem_ch

        stem_in = {"vil": cfg.t_in, "ir": cfg.t_in * cfg.ir_channels, "lght": cfg.t_in}
        stem_rs = {"vil": "down", "ir": "down", "lght": "up"}
        self.stems = nn.ModuleDict({m: Stem(stem_in[m], sc, stem_rs[m]) for m in self.obs})
        self.fuse = ModalityFusion(self.obs, sc, chs[0])

        self.enc = nn.ModuleList()
        self.down = nn.ModuleList()
        for i, c in enumerate(chs):
            if i > 0:
                self.down.append(nn.Conv2d(chs[i - 1], c, 3, stride=2, padding=1))
            self.enc.append(nn.ModuleList([ResBlock(c, c) for _ in range(cfg.enc_blocks)]))

        d = chs[-1]
        self.bott_pos = nn.Conv2d(d, d, 3, padding=1, groups=d)
        self.attn = nn.ModuleList([AttnBlock(d, cfg.heads, cross=self.use_nwp) for _ in range(cfg.attn_depth)])
        if self.use_nwp:
            self.nwp_enc = NWPEncoder(cfg.nwp_hours * cfg.nwp_vars, d)
            self.nwp_null = nn.Parameter(torch.zeros(1, 1, d))

        cond_in = 2 + len(self.modalities) + (d if self.use_nwp else 0)
        self.cond = nn.Sequential(nn.Linear(cond_in, cfg.cond_dim), nn.SiLU(),
                                  nn.Linear(cfg.cond_dim, cfg.cond_dim))

        self.up = nn.ModuleList()
        self.dec = nn.ModuleList()
        for i in range(len(chs) - 1):
            self.up.append(nn.Sequential(nn.Upsample(scale_factor=2, mode="nearest"),
                                         nn.Conv2d(chs[i + 1], chs[i], 3, padding=1)))
            blocks = [ResBlock(2 * chs[i], chs[i], cfg.cond_dim)]
            blocks += [ResBlock(chs[i], chs[i], cfg.cond_dim) for _ in range(cfg.dec_blocks - 1)]
            self.dec.append(nn.ModuleList(blocks))

        self.vil_head = nn.Sequential(nn.GroupNorm(_groups(chs[0]), chs[0]), nn.SiLU(),
                                      nn.Conv2d(chs[0], cfg.t_out * 4, 3, padding=1), nn.PixelShuffle(2))
        self.lght_head = nn.Sequential(nn.GroupNorm(_groups(chs[1]), chs[1]), nn.SiLU(),
                                       nn.Conv2d(chs[1], cfg.t_out, 3, padding=1))
        nn.init.constant_(self.lght_head[-1].bias, cfg.lght_bias_init)

    # ------------------------------------------------------------------ presence handling
    def _presence(self, x, B, device, force_missing):
        present = {m: torch.ones(B, dtype=torch.bool, device=device) for m in self.modalities}
        given = x.get("present", {})
        for m, v in given.items():
            if m in present:
                present[m] = v.to(device=device, dtype=torch.bool)
        for m in force_missing:
            if m in present:
                present[m] = torch.zeros_like(present[m])
        return present

    def _modality_dropout(self, present, p):
        out = {}
        for m, v in present.items():
            drop = torch.rand(v.shape, device=v.device) < p
            out[m] = v & ~drop
        # never drop every observation modality of a sample: restore the first one that existed
        any_obs = torch.stack([out[m] for m in self.obs], 1).any(1)
        for m in self.obs:
            restore = ~any_obs & present[m]
            out[m] = out[m] | restore
            any_obs = any_obs | restore
        return out

    # ------------------------------------------------------------------ forward
    def forward(self, x: dict, drop_p: float = 0.0, force_missing: tuple = ()):
        ref = x[self.obs[0]]
        B, device = ref.shape[0], ref.device
        present = self._presence(x, B, device, force_missing)
        if self.training and drop_p > 0:
            present = self._modality_dropout(present, drop_p)

        feats = {m: self.stems[m](x[m]) for m in self.obs}
        h = self.fuse(feats, present)

        skips = []
        for i, blocks in enumerate(self.enc):
            if i > 0:
                h = self.down[i - 1](h)
            for blk in blocks:
                h = blk(h)
            skips.append(h)

        ctx = None
        cond_parts = [x["tod"].to(h.dtype), torch.stack([present[m] for m in self.modalities], 1).to(h.dtype)]
        if self.use_nwp:
            ctx, nwp_vec = self.nwp_enc(x["nwp"])
            ok = present["nwp"]
            ctx = torch.where(ok[:, None, None], ctx, self.nwp_null.to(ctx.dtype).expand_as(ctx))
            cond_parts.append(torch.where(ok[:, None], nwp_vec, torch.zeros_like(nwp_vec)))
        cond = self.cond(torch.cat([c.to(h.dtype) for c in cond_parts], 1))

        h = h + self.bott_pos(h)
        _, C, hh, ww = h.shape
        t = h.flatten(2).transpose(1, 2)
        for blk in self.attn:
            t = blk(t, ctx)
        h = t.transpose(1, 2).reshape(B, C, hh, ww)

        lght_feat = h  # with only 2 levels the bottleneck is already at H/4
        for i in reversed(range(len(self.dec))):
            h = torch.cat([self.up[i](h), skips[i]], 1)
            for blk in self.dec[i]:
                h = blk(h, cond)
            if i == 1:
                lght_feat = h
        return {"vil": self.vil_head(h), "lght": self.lght_head(lght_feat)}


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
