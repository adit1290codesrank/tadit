"""YAML config -> dataclasses, with `--set section.key=value` overrides. Unknown keys are errors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

import yaml


@dataclass
class DataConfig:
    train_dir: str = "shards/train"
    val_dir: str | None = "shards/val"
    num_workers: int = 8
    prefetch_factor: int = 4
    windows_per_event: int = 3
    rotate: bool = True
    # horizon: t_in frames of 5-min history -> t_out targets every out_step frames
    t_in: int = 7
    t_out: int = 18
    out_step: int = 2
    # India adaptation (training only): make this fraction of samples look like INSAT imagery
    # (4/8 km, 15/30-min scans) and GFS NWP (no LTNG/UH, ~24 km). 0 disables.
    india_aug_p: float = 0.5
    nwp_gfs_p: float = 0.5


@dataclass
class TrainConfig:
    out_dir: str = "runs/dev"
    batch_size: int = 8
    lr: float = 5e-4
    weight_decay: float = 0.05
    betas: tuple = (0.9, 0.95)
    grad_clip: float = 1.0
    warmup_steps: int = 500
    min_lr_ratio: float = 0.02
    max_steps: int | None = None
    deadline_minutes: float | None = None  # wall-clock budget; LR schedule is fitted to it
    reserve_minutes: float = 3.0            # stop this long before the deadline (final save)
    drop_p: float = 0.15                    # modality dropout
    lght_weight: float = 10.0
    vil_band_weights: tuple = (1, 2, 5, 10, 20, 30, 40)
    focal_gamma: float = 2.0
    lght_dilate: int = 1
    lght_pos_weight: float = 1.0
    amp: str = "bf16"                       # bf16 | fp32
    compile: bool = False
    channels_last: bool = True
    ema_decay: float = 0.999
    ckpt_every_min: float = 10.0
    val_every_min: float = 15.0
    val_batches: int = 50
    log_every: int = 50
    min_free_gb: float = 2.0
    seed: int = 0


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    model: dict = field(default_factory=dict)  # passed to ModelConfig (validated there)
    train: TrainConfig = field(default_factory=TrainConfig)

    def to_dict(self) -> dict:
        return asdict(self)


def _build(cls, d: dict):
    names = {f.name for f in fields(cls)}
    unknown = set(d) - names
    if unknown:
        raise KeyError(f"unknown {cls.__name__} keys: {sorted(unknown)}")
    kw = {}
    for f in fields(cls):
        if f.name in d:
            v = d[f.name]
            kw[f.name] = tuple(v) if isinstance(v, list) else v
    return cls(**kw)


def load_config(path: str | None, overrides: list[str] = ()) -> Config:
    raw = {}
    if path:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    for ov in overrides:
        key, _, val = ov.partition("=")
        parts = key.strip().split(".")
        node = raw
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = yaml.safe_load(val)
    unknown = set(raw) - {"data", "model", "train"}
    if unknown:
        raise KeyError(f"unknown config sections: {sorted(unknown)}")
    return Config(
        data=_build(DataConfig, raw.get("data", {})),
        model=dict(raw.get("model", {})),
        train=_build(TrainConfig, raw.get("train", {})),
    )
