#!/usr/bin/env python
"""Synthetic shards in the real format: develop and smoke-test training before real data exists.

  python scripts/make_synthetic.py --out shards/synth --n-train 256 --n-val 32 --n-test 32
  python scripts/make_synthetic.py --out shards/tiny --hr 64 --lr 16 --n-train 32   # CPU-sized
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nowcast.data.synthetic import write_synthetic_split  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="shards/synth")
    ap.add_argument("--n-train", type=int, default=256)
    ap.add_argument("--n-val", type=int, default=32)
    ap.add_argument("--n-test", type=int, default=32)
    ap.add_argument("--hr", type=int, default=192)
    ap.add_argument("--lr", type=int, default=48)
    args = ap.parse_args()
    stats = None
    for i, (split, n) in enumerate([("train", args.n_train), ("val", args.n_val), ("test", args.n_test)]):
        stats = write_synthetic_split(os.path.join(args.out, split), n, seed=i, hr=args.hr, lr=args.lr, stats=stats)
        print(f"{split}: {n} events -> {os.path.join(args.out, split)}")


if __name__ == "__main__":
    main()
