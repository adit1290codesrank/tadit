import os

import pytest

from nowcast.data.synthetic import write_synthetic_split

HR, LR = 64, 16


@pytest.fixture(scope="session")
def tiny_shards(tmp_path_factory):
    root = tmp_path_factory.mktemp("shards")
    stats = write_synthetic_split(str(root / "train"), 12, seed=0, hr=HR, lr=LR, events_per_shard=5)
    write_synthetic_split(str(root / "val"), 4, seed=1, hr=HR, lr=LR, stats=stats)
    return str(root)


def tiny_model_cfg(**kw):
    from nowcast.model import ModelConfig

    base = dict(nwp_vars=11, stem_ch=16, chs=(16, 32, 48, 64), enc_blocks=1, dec_blocks=1,
                attn_depth=1, heads=2, cond_dim=32)
    base.update(kw)
    return ModelConfig(**base)


os.environ.setdefault("OMP_NUM_THREADS", "2")
