# Dataset Configuration Reference

The file `data/dataset_config.json` controls how TIFFs are read, rendered, and passed to SAM2. It is **auto-generated** on first startup by scanning the TIFFs in `data/trainingTiffs/`. You can edit it manually or update it via the API.

## Auto-Detection

On startup, if `data/dataset_config.json` does not exist, the app:

1. Opens the first TIFF to read band count, dtype, and nodata
2. Samples up to 5 TIFFs to compute stretch statistics
3. Detects whether data is already 0-255 (common for ortho exports) or needs stretching
4. Writes the config to `data/dataset_config.json`

To force re-detection: `POST /api/dataset-config/redetect`

## Fields

### `band_count` (integer, read-only)

Total number of bands in the TIFFs. Detected from the first TIFF. Not used directly for rendering — `display_bands` controls which bands are shown.

### `band_names` (array of strings)

Human-readable names for each band, in order. Used for UI labels.

Auto-detected defaults:
- 3 bands: `["Red", "Green", "Blue"]`
- 4 bands: `["Red", "Green", "Blue", "NIR"]`
- 5+ bands: `["Red", "Green", "Blue", "NIR", "Band 5", ...]`
- 1-2 bands: `["Band 1"]` or `["Band 1", "Band 2"]`

You should customize these for your data. For example, Planet SuperDove 8-band:
```json
"band_names": ["Coastal Blue", "Blue", "Green I", "Green II", "Yellow", "Red", "Red Edge", "NIR"]
```

### `display_bands` (array of 1-3 integers)

Which bands (1-based) to map to the Red, Green, Blue display channels. The order matters: `[R, G, B]`.

Examples:
| Setting | Effect |
|---------|--------|
| `[1, 2, 3]` | True color RGB (default) |
| `[4, 1, 2]` | False color NIR composite (NIR as red) |
| `[4, 3, 2]` | Standard false color (common for vegetation) |
| `[1, 1, 1]` | Single band displayed as grayscale |

SAM2 receives the same 3 bands shown on screen — what you see is what SAM2 segments.

If a band index exceeds the TIFF's band count, the last valid band is repeated to fill 3 channels.

### `stretch` (object)

Controls how raw pixel values are mapped to the 0-255 display range.

#### `stretch.method` (string)

| Method | Description |
|--------|-------------|
| `"none"` | No transformation. Assumes data is already uint8 0-255. |
| `"clip255"` | Clip values to 0-255 range. For uint16 data that stores 0-255 values (e.g., ortho exports with nodata=256). |
| `"percentile"` | Linear stretch using percentile-based min/max. Best general-purpose option for satellite imagery. |
| `"minmax"` | Linear stretch using absolute min/max. Can be washed out if outliers exist. |
| `"stddev"` | Linear stretch using mean +/- 2 standard deviations. Good for normally-distributed data. |

For `percentile`, `minmax`, and `stddev`: pixel values are linearly mapped from `[band_min, band_max]` to `[0, 255]`, then clipped.

#### `stretch.band_mins` (array of floats)

Per-band minimum values for the stretch. One value per display band. Values below this become 0 (black).

Auto-computed from sampled TIFFs based on the chosen method. Can be overridden manually for fine-tuning.

#### `stretch.band_maxs` (array of floats)

Per-band maximum values for the stretch. One value per display band. Values above this become 255 (white).

#### `stretch.percentile_min` (integer, default: 2)

Lower percentile for the `"percentile"` stretch method. Typical range: 1-5. Lower values preserve more shadow detail but may look washed out.

#### `stretch.percentile_max` (integer, default: 98)

Upper percentile for the `"percentile"` stretch method. Typical range: 95-99. Higher values preserve more highlight detail.

### `nodata` (number or null)

The nodata value for the TIFFs. Pixels matching this value in any band are rendered as transparent. Auto-detected from TIFF metadata.

Common values:
- `256` — ortho exports with uint16 bands storing 0-255
- `0` — some satellite products
- `-9999` — float data products
- `null` — no nodata value set

### `dtype` (string, read-only)

The numpy dtype of the TIFF bands as reported by rasterio. Informational only — the stretch method determines how values are mapped.

Common values: `"uint8"`, `"uint16"`, `"int16"`, `"float32"`, `"float64"`

## API Endpoints

### `GET /api/dataset-config`

Returns the current dataset configuration.

### `PUT /api/dataset-config`

Update configuration fields. Only include fields you want to change. Stretch statistics are automatically recalculated when `display_bands` or `stretch.method` changes (unless you also provide explicit `band_mins`/`band_maxs`).

Example — switch to false-color NIR composite:
```json
{
  "display_bands": [4, 3, 2]
}
```

Example — change stretch method:
```json
{
  "stretch": {
    "method": "percentile",
    "percentile_min": 1,
    "percentile_max": 99
  }
}
```

Example — manual stretch override:
```json
{
  "stretch": {
    "band_mins": [100.0, 200.0, 150.0],
    "band_maxs": [2500.0, 3000.0, 2800.0]
  }
}
```

### `POST /api/dataset-config/redetect`

Force re-detection of all dataset properties from TIFFs. Overwrites the existing config.

## Example Configurations

### 3-band ortho (uint16 0-255, nodata=256)
```json
{
  "band_count": 3,
  "band_names": ["Red", "Green", "Blue"],
  "display_bands": [1, 2, 3],
  "stretch": {
    "method": "clip255",
    "band_mins": [0.0, 0.0, 0.0],
    "band_maxs": [255.0, 255.0, 255.0],
    "percentile_min": 2,
    "percentile_max": 98
  },
  "nodata": 256.0,
  "dtype": "uint16"
}
```

### 4-band drone imagery (RGBNIR, uint16, 12-bit range)
```json
{
  "band_count": 4,
  "band_names": ["Red", "Green", "Blue", "NIR"],
  "display_bands": [1, 2, 3],
  "stretch": {
    "method": "percentile",
    "band_mins": [120.0, 95.0, 80.0],
    "band_maxs": [3200.0, 3100.0, 2900.0],
    "percentile_min": 2,
    "percentile_max": 98
  },
  "nodata": 0,
  "dtype": "uint16"
}
```

### Planet SuperDove (8-band, uint16, surface reflectance)
```json
{
  "band_count": 8,
  "band_names": ["Coastal Blue", "Blue", "Green I", "Green II", "Yellow", "Red", "Red Edge", "NIR"],
  "display_bands": [6, 3, 2],
  "stretch": {
    "method": "percentile",
    "band_mins": [400.0, 500.0, 300.0],
    "band_maxs": [2800.0, 2600.0, 2200.0],
    "percentile_min": 2,
    "percentile_max": 98
  },
  "nodata": 0,
  "dtype": "uint16"
}
```
