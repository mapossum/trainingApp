"""Dataset configuration: auto-detection from TIFFs and persistence to dataset_config.json."""

import os
import json
import numpy as np
import rasterio

import config

DATASET_CONFIG_PATH = os.path.join(config.DATA_DIR, 'dataset_config.json')

# Defaults
DEFAULT_STRETCH = "percentile"
DEFAULT_PERCENTILE_MIN = 2
DEFAULT_PERCENTILE_MAX = 98


def _find_first_tiff():
    """Find the first .tif file in the TIFF directory."""
    tiff_dir = config.TIFF_DIR
    if not os.path.isdir(tiff_dir):
        return None
    for fname in sorted(os.listdir(tiff_dir)):
        if fname.lower().endswith('.tif'):
            return os.path.join(tiff_dir, fname)
    return None


def _detect_stretch_range(tiff_path, bands, method="percentile",
                          percentile_min=2, percentile_max=98, sample_limit=5):
    """Compute stretch parameters by sampling TIFFs.

    Returns (band_mins, band_maxs) as lists of per-band values.
    """
    tiff_dir = config.TIFF_DIR
    tiff_files = sorted([
        os.path.join(tiff_dir, f)
        for f in os.listdir(tiff_dir)
        if f.lower().endswith('.tif')
    ])
    # Sample a subset for speed
    if len(tiff_files) > sample_limit:
        step = len(tiff_files) // sample_limit
        tiff_files = tiff_files[::step][:sample_limit]

    all_values = {b: [] for b in bands}

    for tf in tiff_files:
        try:
            with rasterio.open(tf) as ds:
                nodata = ds.nodata
                for b in bands:
                    if b > ds.count:
                        continue
                    data = ds.read(b).astype(np.float64).ravel()
                    if nodata is not None:
                        data = data[data != nodata]
                    # Also exclude exact zeros (common fill value)
                    data = data[data != 0]
                    if len(data) > 0:
                        all_values[b].append(data)
        except Exception:
            continue

    band_mins = []
    band_maxs = []
    for b in bands:
        if all_values[b]:
            combined = np.concatenate(all_values[b])
            if method == "percentile":
                bmin = float(np.percentile(combined, percentile_min))
                bmax = float(np.percentile(combined, percentile_max))
            elif method == "minmax":
                bmin = float(np.min(combined))
                bmax = float(np.max(combined))
            elif method == "stddev":
                mean = np.mean(combined)
                std = np.std(combined)
                bmin = float(max(0, mean - 2 * std))
                bmax = float(mean + 2 * std)
            else:
                bmin, bmax = 0.0, 255.0
        else:
            bmin, bmax = 0.0, 255.0
        band_mins.append(bmin)
        band_maxs.append(bmax)

    return band_mins, band_maxs


def auto_detect(force=False):
    """Auto-detect dataset properties from TIFFs and create/update dataset_config.json.

    If config already exists and force=False, returns existing config.
    """
    if os.path.exists(DATASET_CONFIG_PATH) and not force:
        return load()

    tiff_path = _find_first_tiff()
    if tiff_path is None:
        return _default_config()

    with rasterio.open(tiff_path) as ds:
        band_count = ds.count
        dtype = ds.dtypes[0]
        nodata = ds.nodata

    # Build band names
    band_names = []
    if band_count >= 3:
        band_names = ["Red", "Green", "Blue"]
        if band_count >= 4:
            band_names.append("NIR")
        for i in range(5, band_count + 1):
            band_names.append(f"Band {i}")
    elif band_count == 2:
        band_names = ["Band 1", "Band 2"]
    elif band_count == 1:
        band_names = ["Band 1"]

    # Default display bands: first 3 (or fewer)
    display_bands = list(range(1, min(band_count, 3) + 1))

    # Detect if data looks like 0-255 uint16 (common for ortho exports)
    # vs actual 16-bit or float data needing stretch
    needs_stretch = dtype in ('uint16', 'int16', 'uint32', 'int32',
                              'float32', 'float64')

    if needs_stretch:
        stretch_method = DEFAULT_STRETCH
    else:
        # uint8 data — no stretch needed
        stretch_method = "none"

    # Compute stretch range from sampled TIFFs
    if stretch_method != "none":
        band_mins, band_maxs = _detect_stretch_range(
            tiff_path, display_bands, method=stretch_method
        )
        # Check if data is actually 0-255 range despite uint16 dtype
        if all(mx <= 255 for mx in band_maxs):
            stretch_method = "clip255"
            band_mins = [0.0] * len(display_bands)
            band_maxs = [255.0] * len(display_bands)
    else:
        band_mins = [0.0] * len(display_bands)
        band_maxs = [255.0] * len(display_bands)

    cfg = {
        "band_count": band_count,
        "band_names": band_names,
        "display_bands": display_bands,
        "stretch": {
            "method": stretch_method,
            "band_mins": band_mins,
            "band_maxs": band_maxs,
            "percentile_min": DEFAULT_PERCENTILE_MIN,
            "percentile_max": DEFAULT_PERCENTILE_MAX,
        },
        "nodata": nodata,
        "dtype": dtype,
    }

    save(cfg)
    return cfg


def _default_config():
    """Fallback config when no TIFFs found."""
    return {
        "band_count": 3,
        "band_names": ["Red", "Green", "Blue"],
        "display_bands": [1, 2, 3],
        "stretch": {
            "method": "clip255",
            "band_mins": [0.0, 0.0, 0.0],
            "band_maxs": [255.0, 255.0, 255.0],
            "percentile_min": DEFAULT_PERCENTILE_MIN,
            "percentile_max": DEFAULT_PERCENTILE_MAX,
        },
        "nodata": None,
        "dtype": "uint8",
    }


def load():
    """Load dataset_config.json. Returns dict or None if not found."""
    if not os.path.exists(DATASET_CONFIG_PATH):
        return None
    with open(DATASET_CONFIG_PATH, 'r') as f:
        return json.load(f)


def save(cfg):
    """Save dataset config to disk."""
    with open(DATASET_CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def recalculate_stretch(method=None, percentile_min=None, percentile_max=None,
                        display_bands=None):
    """Recalculate stretch parameters. Used when user changes bands or method."""
    cfg = load()
    if cfg is None:
        cfg = auto_detect()

    if display_bands is not None:
        cfg["display_bands"] = display_bands
    if method is not None:
        cfg["stretch"]["method"] = method
    if percentile_min is not None:
        cfg["stretch"]["percentile_min"] = percentile_min
    if percentile_max is not None:
        cfg["stretch"]["percentile_max"] = percentile_max

    bands = cfg["display_bands"]
    m = cfg["stretch"]["method"]

    if m == "none" or m == "clip255":
        cfg["stretch"]["band_mins"] = [0.0] * len(bands)
        cfg["stretch"]["band_maxs"] = [255.0] * len(bands)
    else:
        tiff_path = _find_first_tiff()
        if tiff_path:
            band_mins, band_maxs = _detect_stretch_range(
                tiff_path, bands, method=m,
                percentile_min=cfg["stretch"]["percentile_min"],
                percentile_max=cfg["stretch"]["percentile_max"],
            )
            cfg["stretch"]["band_mins"] = band_mins
            cfg["stretch"]["band_maxs"] = band_maxs

    save(cfg)
    return cfg
