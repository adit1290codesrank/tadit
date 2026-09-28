"""384 km forecast tiles over India, built with the same geometry code as the SEVIR training patches
(Lambert azimuthal equal-area, row 0 = south), so every adapter lands on the grid the model knows."""

from __future__ import annotations

import numpy as np

from ..data.sevir import event_grid_latlon

TILE_M = 384_000.0

# Lightning hotspots first (Odisha, West Bengal, Jharkhand, Bihar, the North-East), then metros.
CITIES = {
    "Bhubaneswar": (20.296, 85.825), "Kolkata": (22.573, 88.364), "Ranchi": (23.344, 85.310),
    "Patna": (25.594, 85.138), "Guwahati": (26.144, 91.736), "Shillong": (25.578, 91.893),
    "Agartala": (23.831, 91.287), "Raipur": (21.251, 81.630), "Nagpur": (21.146, 79.088),
    "Bhopal": (23.260, 77.413), "Lucknow": (26.847, 80.947), "Delhi": (28.614, 77.209),
    "Jaipur": (26.912, 75.787), "Ahmedabad": (23.023, 72.571), "Mumbai": (19.076, 72.878),
    "Hyderabad": (17.385, 78.487), "Bengaluru": (12.972, 77.595), "Chennai": (13.083, 80.271),
    "Thiruvananthapuram": (8.524, 76.937), "Srinagar": (34.084, 74.797),
}

INDIA_BBOX = (6.0, 37.5, 68.0, 97.5)  # lat_min, lat_max, lon_min, lon_max


def make_tile(lat: float, lon: float, name: str | None = None) -> dict:
    """Tile centred on (lat, lon). The dict has the same keys as a SEVIR catalog row."""
    import pyproj

    proj = f"+proj=laea +lat_0={lat:.4f} +lon_0={lon:.4f} +units=m +a=6370997.0 +ellps=sphere"
    p = pyproj.Proj(proj)
    h = TILE_M / 2
    ll_lon, ll_lat = p(-h, -h, inverse=True)
    ur_lon, ur_lat = p(h, h, inverse=True)
    return {"id": name or f"IN_{lat:.2f}_{lon:.2f}", "proj": proj, "center_lat": lat, "center_lon": lon,
            "llcrnrlat": ll_lat, "llcrnrlon": ll_lon, "urcrnrlat": ur_lat, "urcrnrlon": ur_lon}


def city_tile(name: str) -> dict:
    if name not in CITIES:
        raise KeyError(f"unknown city {name!r}; known: {', '.join(CITIES)}")
    return make_tile(*CITIES[name], name=name)


def india_tiles() -> list[dict]:
    """Non-overlapping tiles covering the India bounding box (ocean-only tiles included)."""
    lat_min, lat_max, lon_min, lon_max = INDIA_BBOX
    dlat = TILE_M / 111_000.0
    tiles = []
    for lat in np.arange(lat_min + dlat / 2, lat_max, dlat):
        dlon = dlat / np.cos(np.deg2rad(lat))
        for lon in np.arange(lon_min + dlon / 2, lon_max, dlon):
            tiles.append(make_tile(float(lat), float(lon)))
    return tiles


def tile_grid(tile: dict, n: int) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lon) of the n x n cell centres, in model orientation."""
    return event_grid_latlon(tile, n)


def latlon_to_pixel(tile: dict, lat, lon, n: int):
    """Fractional (row, col) on the n x n tile grid, consistent with tile_grid()."""
    import pyproj

    from ..data import sevir

    p = pyproj.Proj(tile["proj"])
    x, y = p(np.asarray(lon, float), np.asarray(lat, float))
    col = (x + TILE_M / 2) / TILE_M * n
    row = (y + TILE_M / 2) / TILE_M * n
    if sevir.ROW0_NORTH:
        row = n - row
    return row, col
