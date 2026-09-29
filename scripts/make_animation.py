#!/usr/bin/env python
"""Animated forecast vs truth for one US test storm (results/full_examples.npz), for slides and the demo video.

Three panels step through the 18 x 10-min lead times:
  observed radar VIL | model radar VIL forecast | model lightning probability with observed GLM flashes on top.
Writes a GIF, and an MP4 too when imageio-ffmpeg is installed.

  python scripts/make_animation.py --results results --out figures --example 1
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

from make_figures import INK, INK2, LABEL, MUTED, PROB_CMAP, SURFACE, VIL_CMAP, style  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="figures")
    ap.add_argument("--example", type=int, default=1, help="rank by observed lightning, 1 = most lightning")
    ap.add_argument("--fps", type=float, default=3)
    args = ap.parse_args()

    z = np.load(os.path.join(args.results, "full_examples.npz"))
    strikes = z["lght_true"].reshape(len(z["lght_true"]), -1).sum(1, dtype=np.int64)  # uint8: never negate
    i = int(np.argsort(strikes)[::-1][args.example - 1])
    vt, vp = z["vil_true"][i], z["vil_pred"][i]
    lt, lp = z["lght_true"][i], z["lght_prob"][i].astype(np.float32)
    n = vt.shape[0]

    style()
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.83, bottom=0.1, wspace=0.05)
    ims = [axes[0].imshow(vt[0], origin="lower", cmap=VIL_CMAP, vmin=0, vmax=255),
           axes[1].imshow(vp[0], origin="lower", cmap=VIL_CMAP, vmin=0, vmax=255),
           axes[2].imshow(lp[0], origin="lower", cmap=PROB_CMAP, vmin=0, vmax=1)]
    dots, = axes[2].plot([], [], "o", ms=5, mfc="none", mec=INK, mew=1.1)
    for ax, t in zip(axes, ("What happened: radar", "Model forecast: radar", "Model forecast: lightning chance")):
        ax.set_title(t, fontsize=13)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    axes[2].text(0.02, 0.02, "o = real lightning (GLM)", transform=axes[2].transAxes, fontsize=10, color=INK,
                 bbox=dict(facecolor=SURFACE, alpha=0.8, lw=0))
    head = fig.suptitle("", x=0.01, ha="left", fontsize=16, fontweight="bold")
    fig.text(0.01, 0.9, "384 km US test storm the model never saw. North up. Darker = stronger.", fontsize=11, color=INK2)
    fig.text(0.01, 0.03, LABEL, fontsize=9, color=MUTED)

    def frame(k):
        ims[0].set_data(vt[k]); ims[1].set_data(vp[k]); ims[2].set_data(lp[k])
        r, c = np.nonzero(lt[k])
        dots.set_data(c, r)
        head.set_text(f"Nowcast +{(k + 1) * 10} min  ({k + 1}/{n})")
        return ims + [dots, head]

    anim = FuncAnimation(fig, frame, frames=n, interval=1000 / args.fps, blit=False)
    os.makedirs(args.out, exist_ok=True)
    gif = os.path.join(args.out, f"anim_example_{args.example}.gif")
    anim.save(gif, writer=PillowWriter(fps=args.fps), dpi=90, savefig_kwargs={"facecolor": SURFACE})
    print("wrote", gif)
    try:
        import imageio_ffmpeg
        plt.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
        mp4 = gif[:-4] + ".mp4"
        anim.save(mp4, writer="ffmpeg", fps=args.fps, dpi=120, savefig_kwargs={"facecolor": SURFACE})
        print("wrote", mp4)
    except ImportError:
        print("imageio-ffmpeg not installed: GIF only")


if __name__ == "__main__":
    main()
