"""Compressed event shards.

A shard is a pair of files:
  shard_00000.bin      concatenated zstd frames, one per event (each frame is an .npz)
  shard_00000.idx.npy  structured index: offset, length, event_id, t0

The same format is read from local disk on the primary server and from /dev/shm on the burst
server. Readers mmap the .bin, so the page cache (or tmpfs) is shared by every DataLoader
worker and by both training runs, and data stays compressed in RAM.
"""

from __future__ import annotations

import glob
import io
import json
import os

import numpy as np
import zstandard as zstd

IDX_DTYPE = np.dtype([("offset", "<u8"), ("length", "<u8"), ("event_id", "U24"), ("t0", "<i8")])
STATS_FILE = "nwp_stats.json"


def encode_event(arrays: dict[str, np.ndarray], level: int = 3) -> bytes:
    buf = io.BytesIO()
    np.savez(buf, **arrays)
    return zstd.ZstdCompressor(level=level).compress(buf.getvalue())


def decode_event(blob: bytes) -> dict[str, np.ndarray]:
    raw = zstd.ZstdDecompressor().decompress(blob)
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


class ShardWriter:
    """Streams events into fixed-size shards. Files are renamed into place only when complete."""

    def __init__(self, out_dir: str, prefix: str = "shard", events_per_shard: int = 256, level: int = 3):
        self.out_dir = out_dir
        self.prefix = prefix
        self.events_per_shard = events_per_shard
        self.level = level
        os.makedirs(out_dir, exist_ok=True)
        existing = glob.glob(os.path.join(out_dir, f"{prefix}_*.idx.npy"))
        self._shard_no = len(existing)
        self._fh = None
        self._rows: list[tuple] = []
        self._offset = 0
        self.n_events = 0
        self.n_bytes = 0

    def _paths(self, no: int) -> tuple[str, str]:
        base = os.path.join(self.out_dir, f"{self.prefix}_{no:05d}")
        return base + ".bin", base + ".idx.npy"

    def add(self, event_id: str, t0: int, arrays: dict[str, np.ndarray]) -> None:
        if self._fh is None:
            bin_path, _ = self._paths(self._shard_no)
            self._fh = open(bin_path + ".tmp", "wb")
            self._rows, self._offset = [], 0
        blob = encode_event(arrays, self.level)
        self._fh.write(blob)
        self._rows.append((self._offset, len(blob), event_id, int(t0)))
        self._offset += len(blob)
        self.n_events += 1
        self.n_bytes += len(blob)
        if len(self._rows) >= self.events_per_shard:
            self._flush()

    def _flush(self) -> None:
        if self._fh is None:
            return
        self._fh.close()
        bin_path, idx_path = self._paths(self._shard_no)
        np.save(idx_path + ".tmp.npy", np.array(self._rows, dtype=IDX_DTYPE))
        os.replace(bin_path + ".tmp", bin_path)
        os.replace(idx_path + ".tmp.npy", idx_path)
        self._shard_no += 1
        self._fh = None
        self._rows = []

    def close(self) -> None:
        self._flush()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ShardStore:
    """Random access to all events of a shard directory."""

    def __init__(self, root: str):
        self.root = root
        idx_paths = sorted(glob.glob(os.path.join(root, "*.idx.npy")))
        if not idx_paths:
            raise FileNotFoundError(f"no *.idx.npy shards in {root}")
        self.bin_paths = [p[: -len(".idx.npy")] + ".bin" for p in idx_paths]
        parts = [np.load(p) for p in idx_paths]
        self.index = np.concatenate(parts)
        self.shard_of = np.concatenate([np.full(len(p), i, dtype=np.int32) for i, p in enumerate(parts)])
        self._maps: dict[int, np.memmap] = {}
        self._pid = os.getpid()

    def __len__(self) -> int:
        return len(self.index)

    def _map(self, shard: int) -> np.memmap:
        if os.getpid() != self._pid:  # re-open after fork so each worker owns its handles
            self._maps, self._pid = {}, os.getpid()
        m = self._maps.get(shard)
        if m is None:
            m = np.memmap(self.bin_paths[shard], dtype=np.uint8, mode="r")
            self._maps[shard] = m
        return m

    def get(self, i: int) -> dict[str, np.ndarray]:
        row = self.index[i]
        m = self._map(int(self.shard_of[i]))
        off, n = int(row["offset"]), int(row["length"])
        return decode_event(m[off : off + n].tobytes())

    def stats(self) -> dict | None:
        path = os.path.join(self.root, STATS_FILE)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)


def write_stats(root: str, stats: dict) -> None:
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, STATS_FILE + ".tmp")
    with open(tmp, "w") as f:
        json.dump(stats, f, indent=1)
    os.replace(tmp, os.path.join(root, STATS_FILE))


class RunningStats:
    """Per-variable mean/std over NaN-masked NWP fields (float64 accumulators)."""

    def __init__(self, names: list[str]):
        self.names = list(names)
        v = len(names)
        self.n = np.zeros(v)
        self.s = np.zeros(v)
        self.ss = np.zeros(v)

    def update(self, x: np.ndarray) -> None:
        """x: [..., V, H, W]"""
        x = np.moveaxis(x.astype(np.float64), -3, 0).reshape(len(self.names), -1)
        ok = np.isfinite(x)
        self.n += ok.sum(1)
        self.s += np.where(ok, x, 0).sum(1)
        self.ss += np.where(ok, x * x, 0).sum(1)

    def result(self) -> dict:
        n = np.maximum(self.n, 1)
        mean = self.s / n
        std = np.sqrt(np.maximum(self.ss / n - mean**2, 0)) + 1e-6
        return {"vars": self.names, "mean": mean.tolist(), "std": std.tolist(), "count": self.n.tolist()}
