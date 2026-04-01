# Training Data Annotation App

A web-based tool for annotating geospatial imagery to create deep learning training data. Built with Flask and Leaflet, featuring AI-assisted annotation powered by [SAM2 (Segment Anything Model 2)](https://github.com/facebookresearch/sam2).

Designed for remote sensing workflows: load GeoTIFFs in any projection, any band count, any bit depth, and annotate features as polygons with class labels. Annotations are saved as GeoJSON and can be exported as Shapefiles in the native CRS.

## Features

- **Multi-band TIFF support** -- works with RGB, RGBNIR, 8-band (Planet SuperDove), or any band count. Configurable band-to-RGB mapping and dynamic stretch (percentile, min/max, standard deviation)
- **Any projection** -- TIFFs in any CRS are automatically reprojected for display. Annotations stored in EPSG:4326, exported in native CRS
- **SAM2 click-to-segment** -- click foreground/background points and SAM2 generates a smooth polygon. Uses the same bands you see on screen
- **Multiple drawing tools** -- vertex-by-vertex polygon, freehand drawing, and SAM2 AI-assisted modes
- **Dissolve overlapping polygons** -- merge overlapping polygons of the same class into unified polygons with one click
- **Multi-dataset support** -- run multiple instances on different ports with `--data` and `--port` CLI args
- **Auto-save** -- annotations are saved automatically with 1-second debounce
- **Class management** -- define annotation classes with colors in a simple JSON config
- **Keyboard-driven workflow** -- navigate between areas, switch tools, and manage annotations without touching the mouse
- **Export** -- export individual or all areas as GeoJSON + Shapefile with CRS reprojection

## Screenshots

<!-- Add screenshots here -->

## Requirements

- **Python 3.10+** with the following packages:
  - flask, rasterio, numpy, Pillow, pyproj, shapely, fiona, geopandas
  - torch (with CUDA recommended), sam2, opencv-python
- **CUDA-capable GPU** -- recommended for SAM2 inference. CPU fallback is supported but slow
- **SAM2 checkpoint** -- download a SAM2 model checkpoint (e.g., `sam2.1_hiera_small.pt`) from [Meta's SAM2 repository](https://github.com/facebookresearch/sam2)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/trainingApp.git
   cd trainingApp
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   Or use a conda environment with the required packages.

3. **Download a SAM2 checkpoint** and place it in the `sam2_weights/` directory:
   ```
   sam2_weights/
     sam2.1_hiera_small.pt    # or any supported SAM2 checkpoint
   ```
   Supported checkpoints: `sam2_hiera_tiny`, `sam2_hiera_small`, `sam2_hiera_base_plus`, `sam2_hiera_large` (and their SAM2.1 variants). The config YAML is auto-detected from the checkpoint filename.

4. **Prepare your data** (see [Data Setup](#data-setup) below).

5. **Run the app:**
   ```bash
   python -u app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.

   **Run with a specific data directory and port:**
   ```bash
   python -u app.py --data my_dataset --port 5000
   ```

   **Run multiple datasets simultaneously:**
   ```bash
   python -u app.py --data data_seagrass --port 5000
   python -u app.py --data data_coral --port 5001
   ```
   Each instance loads its own SAM2 model (~1.2GB VRAM each).

## Data Setup

Place your data in a directory (default `data/`, or any path via `--data`):

```
data/                       # or data_seagrass/, my_project/, etc.
  config.json               # Class definitions (required)
  trainingTiffs/            # Your GeoTIFF files (required)
  dataset_config.json       # Band/stretch config (auto-generated on first run)
  annotations/              # Annotation GeoJSON files (auto-created)
  app_state.json            # UI state (auto-created)
  trainingPolygons/         # Export output (auto-created)
```

The TIFF subdirectory is auto-detected: `trainingTiffs/`, `trainingAreas/`, `tiffs/`, `images/`, or any subdirectory containing `.tif` files.

### Class Definitions (`config.json`)

Define your annotation classes as a JSON array:

```json
[
  {"name": "building", "value": 1, "color": "red"},
  {"name": "road", "value": 2, "color": "blue"},
  {"name": "vegetation", "value": 3, "color": "green"}
]
```

Each class has:
- `name` -- display label
- `value` -- numeric class ID (used in exports)
- `color` -- CSS color name or hex code for the annotation overlay

### GeoTIFF Files (`trainingTiffs/`)

Place your GeoTIFF files in `data/trainingTiffs/`. The app accepts:

- **Any band count** -- 1-band grayscale through 8+ band multispectral
- **Any bit depth** -- uint8, uint16, int16, float32, float64
- **Any projection** -- UTM, state plane, geographic, compound CRS
- **Any filename** -- the filename stem is used as the unique area ID

On first startup, the app scans the TIFFs and auto-generates `dataset_config.json` with appropriate band mapping and stretch parameters. See [DATASET_CONFIG.md](DATASET_CONFIG.md) for the full configuration reference.

### Dataset Configuration

The auto-generated `data/dataset_config.json` controls how bands are mapped to RGB and how pixel values are stretched for display. Key settings:

| Field | Description |
|-------|-------------|
| `display_bands` | Which bands to map to R, G, B (e.g., `[1, 2, 3]` for true color, `[4, 3, 2]` for false color NIR) |
| `stretch.method` | How to map values to 0-255: `"percentile"`, `"minmax"`, `"stddev"`, `"clip255"`, or `"none"` |
| `stretch.band_mins/maxs` | Per-band stretch range (auto-computed or manual override) |
| `nodata` | Nodata value (auto-detected from TIFF metadata) |

You can edit this file directly or update it via the API:

```bash
# Switch to false-color NIR composite
curl -X PUT http://127.0.0.1:5000/api/dataset-config \
  -H "Content-Type: application/json" \
  -d '{"display_bands": [4, 3, 2]}'

# Force re-detect from TIFFs
curl -X POST http://127.0.0.1:5000/api/dataset-config/redetect
```

See [DATASET_CONFIG.md](DATASET_CONFIG.md) for full details and example configurations.

## Usage

### Navigation

| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next training area |
| 1-9 | Select annotation class |

### Drawing Tools

| Key | Tool | Description |
|-----|------|-------------|
| D | Draw polygon | Click to place vertices, double-click to finish |
| F | Freehand draw | Click, drag to draw, click to finish |
| S | SAM2 segment | Click foreground (left) and background (right) points |
| E | Edit | Drag vertices to reshape existing polygons |
| X | Delete | Click a polygon to remove it |
| -- | Dissolve | Merge overlapping polygons of the same class (toolbar button) |

### SAM2 Workflow

1. Press **S** to enter SAM2 mode
2. **Left-click** to add foreground points (things to include)
3. **Right-click** to add background points (things to exclude)
4. A preview polygon appears after each click
5. Press **Enter** to accept the polygon, or **Escape** to cancel
6. Press **Z** to undo the last point

### Completion Tracking

Mark areas as complete using the checkbox in the sidebar. The app remembers your progress and the last area you were viewing.

### Exporting

Export annotations from the sidebar:
- **Export** button on individual areas
- **Export All** button for batch export

Exports produce both GeoJSON and Shapefile formats in `data/trainingPolygons/`, reprojected to the native CRS of the source TIFF.

## Architecture

```
trainingApp/
  app.py                 # Flask server + API routes + SAM2 prediction pipeline (--data/--port CLI args)
  config.py              # Path constants + set_data_dir() for runtime switching
  dataset_config.py      # TIFF auto-detection and dataset configuration
  tiff_manager.py        # TIFF scanning, rendering, coordinate transforms
  annotation_store.py    # GeoJSON annotation persistence
  sam2_predictor.py      # SAM2 model wrapper
  export.py              # GeoJSON/Shapefile export with CRS reprojection
  templates/
    index.html           # Single-page app
  static/js/
    app.js               # Main orchestrator, keyboard shortcuts
    map.js               # Leaflet map with Esri basemap
    dataset_config.js    # Band assignment and stretch controls UI
    annotations.js       # GeoJSON annotation layer, auto-save, dissolve
    drawing.js           # Polygon/freehand drawing via Leaflet-Geoman
    sam.js               # SAM2 click-to-segment UI
    sidebar.js           # Training area list, navigation, export
    classes.js           # Class selector
```

### How It Works

1. **Startup**: Auto-detect dataset config from TIFFs, load all TIFF metadata (bounds, CRS, transform), initialize SAM2
2. **Display**: TIFFs are warped to EPSG:4326, stretched to uint8 RGB based on `dataset_config.json`, and served as PNG tiles via Leaflet `ImageOverlay`
3. **Annotation**: Polygons drawn or generated by SAM2 are stored as GeoJSON in EPSG:4326 with auto-save
4. **SAM2**: Click coordinates are reprojected to the TIFF's native CRS, converted to pixel coordinates, passed to SAM2. The resulting mask is upsampled 4x, smoothed with Gaussian blur, vectorized with rasterio, simplified, and reprojected back to EPSG:4326
5. **Export**: Annotations are reprojected from EPSG:4326 to the source TIFF's native CRS and written as GeoJSON + Shapefile

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/config` | Class definitions |
| GET | `/api/dataset-config` | Dataset configuration (bands, stretch, nodata) |
| PUT | `/api/dataset-config` | Update dataset configuration |
| POST | `/api/dataset-config/redetect` | Force re-detect config from TIFFs |
| GET | `/api/training-areas` | List all areas with metadata and annotation counts |
| GET | `/api/state` | App state (completion, last viewed) |
| POST | `/api/state` | Update app state |
| GET | `/api/tiff/<id>/image.png` | Rendered TIFF as RGBA PNG |
| GET | `/api/tiff/<id>/bounds` | TIFF bounds in EPSG:4326 |
| GET | `/api/annotations/<id>` | Load annotations for an area |
| PUT | `/api/annotations/<id>` | Save annotations for an area |
| POST | `/api/annotations/<id>/dissolve` | Dissolve overlapping polygons of same class |
| GET | `/api/sam2/status` | Check if SAM2 is available |
| POST | `/api/sam2/predict` | Run SAM2 prediction from click points |
| POST | `/api/export/<id>` | Export one area |
| POST | `/api/export/all` | Export all annotated areas |

## Troubleshooting

**Port already in use**: A previous Flask process may still be running. Kill it:
```bash
# Windows
taskkill /F /IM python.exe

# Linux/Mac
pkill -f "python.*app.py"
```

**SAM2 not loading**: Ensure the checkpoint file is in `sam2_weights/` and the filename matches a known SAM2 variant (e.g., contains `hiera_small`, `hiera_tiny`, etc.).

**Images look wrong**: Check `data/dataset_config.json`. Delete it and restart to trigger re-detection, or adjust `display_bands` and `stretch` settings. See [DATASET_CONFIG.md](DATASET_CONFIG.md).

**Out of GPU memory**: SAM2 uses ~1.2GB VRAM. Use a smaller checkpoint (e.g., `hiera_tiny`) or ensure no zombie Python processes are holding GPU memory.

## License

<!-- Add your license here -->
