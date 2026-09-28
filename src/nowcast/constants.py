"""Sample geometry shared by the data pipeline, model and metrics."""

import numpy as np

# SEVIR events: 49 frames, 5 min apart, offsets -120 .. +120 min around time_utc.
FRAMES = 49
FRAME_SECONDS = 300
DEFAULT_FRAME_OFFSETS_S = np.arange(-120, 125, 5) * 60

# Default horizon: 7 input frames (30 min of history at 5 min) -> 18 outputs every 10 min (0-3 h).
# IMD's operational thunderstorm nowcasts cover the next 3 h; radar extrapolation stops beating
# NWP after ~2 h, so hours 3-6 come from the tier-2 NWP post-processor (nowcast.extended).
# A SEVIR event is 4 h (49 frames): history + horizon must fit, and every spare frame is one more
# training window per event: (49 - 1) - (T_IN - 1) - T_OUT * OUT_STEP = 6 -> 7 windows/event.
# The Earthformer benchmark setup is T_IN=13, T_OUT=12, OUT_STEP=1 (0-1 h); still supported.
T_IN = 7
T_OUT = 18
OUT_STEP = 2  # in 5-min frames


def horizon_frames(t_in: int, t_out: int, out_step: int) -> int:
    """Frames spanned from the first input to the last target, inclusive."""
    return t_in + t_out * out_step


def nwp_hours_for(t_out: int, out_step: int) -> int:
    """Hourly NWP steps covering [floor(t0), t0 + max lead]."""
    lead_min = t_out * out_step * FRAME_SECONDS // 60
    return -(-lead_min // 60) + 1

# Stored grids. VIL is 2x average-pooled from 384 (1 km) to 192 (2 km); IR is native 192.
# Lightning and NWP live on the 48 x 48 (8 km) grid.
HR = 192
LR = 48

# Standard SEVIR VIL thresholds (0-255 digital VIL units) used for CSI.
VIL_THRESHOLDS = (16, 74, 133, 160, 181, 219)

# IR quantisation ranges (deg C) for uint8 storage (~0.3-0.5 K per step).
IR_CHANNELS = ("ir069", "ir107")
IR_RANGE_C = {"ir069": (-85.0, 0.0), "ir107": (-90.0, 45.0)}


# Lightning input scaling: log1p(count) / log1p(32).
LGHT_LOG_SCALE = float(np.log1p(32.0))
