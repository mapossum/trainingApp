# Training Data Annotation App

A web-based tool for annotating geospatial imagery to create deep learning training data. Built with Flask and Leaflet, featuring AI-assisted annotation powered by [SAM2 (Segment Anything Model 2)](https://github.com/facebookresearch/sam2) and ESRI deep learning model prediction.

Designed for remote sensing workflows: load GeoTIFFs in any projection, any band count, any bit depth, and annotate features as polygons with class labels. Annotations are saved as GeoJSON and can be exported as Shapefiles in the native CRS.

## Features

- **Multi-band TIFF support** -- works with RGB, RGBNIR, 8-band (Planet SuperDove), or any band count. Configurable band-to-RGB mapping and dynamic stretch (percentile, min/max, standard deviation)
- **Any projection** -- TIFFs in any CRS are automatically reprojected for display. Annotations stored in EPSG:4326, exported in native CRS
- **SAM2 click-to-segment** -- click foreground/background points and SAM2 generates a smooth polygon
- **Model prediction** -- run ESRI-trained UNet models to pre-generate annotation polygons. Supports multiple models per dataset with automatic normalization from `.emd` metadata. Drop `.pth` + `.emd` pairs in `models/` and restart
- **Multiple drawing tools** -- vertex-by-vertex polygon, freehand, SAM2, edit, and delete modes. All tools allow drawing inside existing polygons (clicks pass through to the map)
- **Select mode** -- click polygons to select, then bulk delete or reassign class
- **Erase mode** -- draw/freehand/SAM2 polygons clip existing annotations instead of adding new ones. Works inside existing polygons
- **Undo** -- 5-level snapshot history (Ctrl+Z)
- **Dissolve overlapping polygons** -- merge overlapping polygons of the same class into unified polygons
- **Smart navigation** -- switching areas preserves the current map view; only re-centers when the new image is off-screen. Fit-to-image button (W) for manual zoom-to-extent
- **Multi-dataset support** -- run multiple instances on different ports with `--data` and `--port` CLI args
- **Auto-save** -- annotations are saved automatically with 1-second debounce
- **Export** -- export current, complete, or all areas as GeoJSON + Shapefile with CRS reprojection
- **Basic authentication** -- optional per-dataset HTTP Basic Auth via `auth.json`
- **Remote access** -- expose datasets to collaborators via Cloudflare Tunnel

## Screenshots

<!-- Add screenshots here -->

## Requirements

- **Python 3.10+** with the following packages:
  - flask, rasterio, numpy, Pillow, pyproj, shapely, fiona, geopandas
  - torch (with CUDA recommended), sam2, opencv-python
  - arcgis.learn (for ESRI model prediction)
- **CUDA-capable GPU** -- recommended for SAM2 and model inference. CPU fallback supported but slow
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
   python -u app.py --data data_conch --port 5003
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
  models/                   # Optional: ESRI DL models (.pth + .emd pairs)
  auth.json                 # Optional: HTTP Basic Auth credentials
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

### Model Prediction (`models/`)

Place ESRI-trained `.pth` + `.emd` file pairs in `data/models/`. On startup the app detects all models and enables the Predict button. Multiple models are supported — a dropdown selector appears when more than one is present.

The `.emd` file is parsed for normalization statistics, band count, and class definitions. Both standard 3-band (ImageNet normalization) and multispectral models (per-band stats from the `.emd`) are supported automatically.

### Authentication (`auth.json`)

To require a password for a dataset (e.g., when exposing via Cloudflare Tunnel):

```json
{
  "username": "annotator",
  "password": "your-password-here"
}
```

If `auth.json` is absent, the app runs without authentication. `auth.json` is in `.gitignore` and should never be committed.

### Dataset Configuration

The auto-generated `data/dataset_config.json` controls how bands are mapped to RGB and how pixel values are stretched for display. Key settings:

| Field | Description |
|-------|-------------|
| `display_bands` | Which bands to map to R, G, B (e.g., `[1, 2, 3]` for true color, `[4, 3, 2]` for false color NIR) |
| `stretch.method` | How to map values to 0-255: `"percentile"`, `"minmax"`, `"stddev"`, `"clip255"`, or `"none"` |
| `stretch.band_mins/maxs` | Per-band stretch range (auto-computed or manual override) |
| `nodata` | Nodata value (auto-detected from TIFF metadata) |

## Usage

### Navigation

| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next training area |
| W | Fit image to window (zoom to extent) |
| 1-9 | Select annotation class |
| 0 | Activate Erase mode |

### Drawing Tools

| Key | Tool | Description |
|-----|------|-------------|
| D | Draw polygon | Click to place vertices, double-click to finish |
| F | Freehand draw | Click, drag to draw, click to finish |
| S | SAM2 segment | Click foreground (left) and background (right) points |
| Q | Select | Click polygons to select; bulk delete or change class |
| E | Edit | Drag vertices to reshape existing polygons |
| X | Delete | Click a polygon to remove it |
| M | Predict | Run DL model inference on current area |
| Ctrl+Z | Undo | Revert last change (up to 5 levels) |
| -- | Dissolve | Merge overlapping polygons of the same class (toolbar button) |

All drawing tools (Draw, Freehand, SAM2) disable polygon click interception while active, so you can start drawing or erasing inside existing polygons.

### Erase Mode

Press **0** or click the Erase button in the class selector. While active, any polygon drawn with Draw, Freehand, or SAM2 will clip existing annotations rather than create a new one. Fully contained polygons are deleted; partially overlapping polygons are clipped. The erase polygon itself is discarded.

### SAM2 Workflow

1. Press **S** to enter SAM2 mode
2. **Left-click** to add foreground points (things to include)
3. **Right-click** to add background points (things to exclude)
4. A preview polygon appears after each click
5. Press **Enter** to accept, **Escape** to cancel, **Z** to undo last point

### Select Mode

1. Press **Q** to enter Select mode
2. Click polygons to toggle selection (highlighted with white dashed border)
3. Use the action bar to change class or delete all selected
4. Press **Escape** or **Q** to exit

### Completion Tracking

Mark areas as complete using the checkbox in the sidebar. Export by completion status using the **Export Complete** button.

### Exporting

Export annotations from the sidebar:
- **Export Current** -- current area only
- **Export Complete** -- all areas marked complete
- **Export All** -- all annotated areas

Exports produce GeoJSON and Shapefile in `data/trainingPolygons/`, reprojected to the native CRS.

## Remote Access (Cloudflare Tunnel)

To share a dataset with offsite collaborators:

1. Add `auth.json` to the dataset directory
2. Install cloudflared: `winget install cloudflare.cloudflared`
3. Start the app: `python -u app.py --data my_dataset --port 5000`
4. Start a tunnel: `cloudflared tunnel --url http://localhost:5000`

For a stable URL, create a named tunnel with a Cloudflare account and configure a custom domain.

## Architecture

```
trainingApp/
  app.py                 # Flask server, API routes, SAM2 pipeline, erase, auth
  config.py              # Path constants, set_data_dir(), AUTH_PATH
  dataset_config.py      # TIFF auto-detection and dataset configuration
  tiff_manager.py        # TIFF scanning, rendering, coordinate transforms
  annotation_store.py    # GeoJSON annotation persistence
  sam2_predictor.py      # SAM2 model wrapper
  model_predictor.py     # ESRI DL model inference (UNet, tiled, multi-band norm)
  export.py              # GeoJSON/Shapefile export with CRS reprojection
  templates/
    index.html           # Single-page app
  static/js/
    app.js               # Main orchestrator, keyboard shortcuts
    map.js               # Leaflet map, fit-to-image control
    dataset_config.js    # Band assignment and stretch controls UI
    annotations.js       # GeoJSON layer, auto-save, undo, erase, setInteractive
    drawing.js           # Polygon/freehand drawing via Leaflet-Geoman
    sam.js               # SAM2 click-to-segment UI
    select.js            # Select mode: click to select, bulk edit/delete
    model_predict.js     # DL model prediction UI, model selector dropdown
    sidebar.js           # Training area list, navigation, export buttons
    classes.js           # Class selector with Erase pseudo-class
```

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/config` | Class definitions |
| GET | `/api/dataset-config` | Dataset configuration (bands, stretch, nodata) |
| PUT | `/api/dataset-config` | Update dataset configuration |
| POST | `/api/dataset-config/redetect` | Force re-detect config from TIFFs |
| GET | `/api/training-areas` | List all areas with metadata and annotation counts |
| GET | `/api/state` | App state (completion, last viewed, sort) |
| POST | `/api/state` | Update app state |
| GET | `/api/tiff/<id>/image.png` | Rendered TIFF as RGBA PNG |
| GET | `/api/tiff/<id>/bounds` | TIFF bounds in EPSG:4326 |
| GET | `/api/annotations/<id>` | Load annotations for an area |
| PUT | `/api/annotations/<id>` | Save annotations for an area |
| POST | `/api/annotations/<id>/dissolve` | Dissolve overlapping polygons of same class |
| POST | `/api/annotations/<id>/erase` | Clip annotations with an erase polygon |
| GET | `/api/sam2/status` | Check if SAM2 is available |
| POST | `/api/sam2/predict` | Run SAM2 prediction from click points |
| GET | `/api/models` | List available DL prediction models |
| POST | `/api/model-predict` | Run DL model inference on a training area |
| POST | `/api/export/<id>` | Export one area |
| POST | `/api/export/complete` | Export all areas marked complete |
| POST | `/api/export/all` | Export all annotated areas |

## Troubleshooting

**Port already in use**: A previous Flask process may still be running:
```powershell
taskkill /F /IM python.exe
# or find the specific PID:
netstat -ano | findstr :5000
taskkill /F /PID <pid>
```

**App loads but no data (blank sidebar)**: The `app_state.json` may be empty or corrupted (e.g., after swapping datasets). Delete it and restart — the app will create a fresh one.

**SAM2 not loading**: Ensure the checkpoint file is in `sam2_weights/` and the filename matches a known SAM2 variant (e.g., contains `hiera_small`, `hiera_tiny`, etc.).

**Images look wrong**: Delete `data/dataset_config.json` and restart to trigger re-detection, or adjust `display_bands` and `stretch` in the sidebar controls.

**Model prediction fails**: Ensure the `.emd` file is present alongside the `.pth`. The `.emd` must be a valid ESRI Model Definition with `NormalizationStats` for multispectral models.

**Out of GPU memory**: SAM2 uses ~1.2GB VRAM. Use a smaller checkpoint (e.g., `hiera_tiny`) or ensure no zombie Python processes are holding GPU memory.

## License

<!-- Add your license here -->
