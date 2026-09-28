"""Sample geometry shared by the data pipeline, model and metrics."""

import numpy as np

# SEVIR events: 49 frames, 5 min apart, offsets -120 .. +120 min around time_utc.
FRAMES = 49
FRAME_SECONDS = 300
DEFAULT_FRAME_OFFSETS_S = np.arange(-120, 125, 5) * 60

# 13 input frames (65 min) -> 12 output frames (60 min), as in the Earthformer SEVIR setup.
T_IN = 13
T_OUT = 12
WINDOW = T_IN + T_OUT

# Stored grids. VIL is 2x average-pooled from 384 (1 km) to 192 (2 km); IR is native 192.
# Lightning and NWP live on the 48 x 48 (8 km) grid.
HR = 192
LR = 48

# Standard SEVIR VIL thresholds (0-255 digital VIL units) used for CSI.
VIL_THRESHOLDS = (16, 74, 133, 160, 181, 219)

# IR quantisation ranges (deg C) for uint8 storage (~0.3-0.5 K per step).
IR_CHANNELS = ("ir069", "ir107")
IR_RANGE_C = {"ir069": (-85.0, 0.0), "ir107": (-90.0, 45.0)}

# NWP hours fed per sample: valid at floor(t0), floor(t0)+1h, floor(t0)+2h.
NWP_HOURS = 3

# Lightning input scaling: log1p(count) / log1p(32).
LGHT_LOG_SCALE = float(np.log1p(32.0))
