# Training Data Annotation App

## Overview
A single-user web application for annotating ortho images to create deep learning training data. Flask backend, Leaflet frontend, with SAM2 (Segment Anything Model 2) AI-assisted annotation.

## Python Environment
```
C:\Users\georg\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe
```
Python 3.13.7 with CUDA-capable GPU support.

## Running the App
```powershell
cd D:\LR2\LR2_arcgis\trainingApp
C:\Users\georg\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe -u app.py
```
Then open `http://127.0.0.1:5000` in a browser.

**Important**: Always use `-u` flag for unbuffered output so logs appear in real time.

**Important**: Kill zombie python.exe processes before restarting. Multiple SAM2 instances consume ~1.2GB each:
```powershell
taskkill /F /IM python.exe
```

## Architecture

### Backend (Python/Flask)
- `app.py` — Flask server, all API routes, SAM2 prediction pipeline
- `config.py` — Path constants (DATA_DIR, TIFF_DIR, ANNOTATIONS_DIR, etc.)
- `dataset_config.py` — Auto-detects TIFF properties (bands, dtype, stretch), persists to `data/dataset_config.json`. See `DATASET_CONFIG.md` for full reference
- `tiff_manager.py` — Scans trainingTiffs/, parses filenames, renders PNGs with configurable band selection and stretch, handles any CRS via pyproj
- `annotation_store.py` — GeoJSON CRUD for annotations + app state persistence
- `sam2_predictor.py` — SAM2 model loading with auto-config detection from checkpoint filename
- `export.py` — Exports annotations to GeoJSON + Shapefile with CRS reprojection

### Frontend (JavaScript/HTML/CSS)
- `templates/index.html` — Single-page app with Leaflet + Leaflet-Geoman CDN
- `static/js/app.js` — Main orchestrator, keyboard shortcuts, initialization
- `static/js/map.js` — Leaflet map with Esri World Imagery basemap, image overlay
- `static/js/annotations.js` — GeoJSON annotation layer with debounced auto-save (1s)
- `static/js/drawing.js` — Polygon draw, freehand draw, edit, delete via Leaflet-Geoman
- `static/js/sam.js` — SAM2 click-to-segment with preview, accept/clear action bar
- `static/js/sidebar.js` — Training area list, sorting, navigation, export buttons
- `static/js/classes.js` — Class selector from config.json

### Data Structure
```
data/
  config.json               # Class definitions (e.g., 5 coral classes)
  dataset_config.json       # Auto-generated: band mapping, stretch, nodata (see DATASET_CONFIG.md)
  annotations/              # Working GeoJSON per area (EPSG:4326)
  app_state.json            # Completion flags, last viewed, sort preference
  trainingPolygons/         # Export destination (native CRS)
  trainingTiffs/            # GeoTIFFs (any band count, any CRS, any bit depth)
sam2_weights/               # SAM2 checkpoint (.pt file)
```

### TIFF Format
- **Naming**: Any `.tif` file is accepted. `{OrthoName}_OID{number}.tif` pattern is parsed for ortho_name/oid metadata when present; otherwise the filename stem is the unique key
- **CRS**: Any CRS supported by rasterio/pyproj. Compound CRS (projected + vertical) handled via `_get_horizontal_crs()`
- **Bands**: Any band count supported. Display bands are configurable via `dataset_config.json` — 3 bands are selected for RGB display and SAM2 input
- **Bit depth**: uint8, uint16, int16, float32, float64. Stretch method in `dataset_config.json` maps values to 0-255 for display
- **Nodata**: Auto-detected from TIFF metadata or set in `dataset_config.json`. Nodata pixels rendered as transparent
- **Rendering**: Configurable band selection + stretch -> uint8 RGB -> warp to EPSG:4326 -> RGBA PNG

### API Routes

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | Serve index.html |
| GET | `/api/config` | Class definitions from config.json |
| GET | `/api/dataset-config` | Dataset config (bands, stretch, nodata) |
| PUT | `/api/dataset-config` | Update dataset config (partial merge, auto-recalculates stretch) |
| POST | `/api/dataset-config/redetect` | Force re-detect config from TIFFs |
| GET | `/api/training-areas` | All areas with metadata, bounds, annotation counts |
| GET | `/api/state` | App state (completion, last viewed, sort) |
| POST | `/api/state` | Update app state (partial merge) |
| GET | `/api/tiff/<id>/image.png` | TIFF rendered as RGBA PNG (uses dataset config) |
| GET | `/api/tiff/<id>/bounds` | Bounds in EPSG:4326 for Leaflet |
| GET | `/api/annotations/<id>` | Load area annotations (GeoJSON) |
| PUT | `/api/annotations/<id>` | Save full FeatureCollection (auto-save) |
| GET | `/api/sam2/status` | Check if SAM2 is loaded |
| POST | `/api/sam2/predict` | Click points -> smooth polygon prediction |
| POST | `/api/export/<id>` | Export one area (GeoJSON + Shapefile) |
| POST | `/api/export/all` | Export all annotated areas |

### SAM2 Pipeline
1. Receive click points (lng/lat + label: 1=foreground, 0=background)
2. Reproject EPSG:4326 -> native CRS via pyproj
3. Inverse affine transform -> pixel coordinates
4. SAM2ImagePredictor.predict() -> binary mask + score
5. **Smooth vectorization**: Upsample mask 4x with INTER_NEAREST, Gaussian blur (7x7, sigma=2.0), re-threshold at 127
6. **Vectorize with rasterio**: `rasterio.features.shapes` with scaled transform (`area['transform'] * RioAffine.scale(1/scale)`) — ensures coordinates align exactly with image overlay
7. Find largest polygon, simplify (0.25 * pixel_size tolerance)
8. Reproject native -> EPSG:4326
9. Return GeoJSON Feature

### Key Technical Decisions
- **Image serving**: TIFF warped to EPSG:4326 via rasterio, then served as RGBA PNG via `L.imageOverlay` (images are small ~1045x1046)
- **Working annotations**: GeoJSON in EPSG:4326 (Leaflet-native) in `data/annotations/`
- **Export**: Reproject to native CRS -> GeoJSON + Shapefile in `trainingPolygons/`
- **Max zoom**: 30 (allows pixel-level viewing)
- **SAM2 smoothing**: 4x upsampled mask + Gaussian blur + rasterio vectorization with scaled transform for precise alignment
- **Freehand tool**: Mouse-tracking with Douglas-Peucker simplification (0.4px tolerance)

## Keyboard Shortcuts
- **Left/Right arrows**: Previous/next training area
- **D**: Draw polygon (click vertices)
- **F**: Freehand polygon (click-drag-click)
- **S**: SAM2 click-to-segment mode
- **E**: Edit vertices
- **X**: Delete mode
- **Enter**: Accept SAM2 prediction / Exit edit mode (saves edits)
- **Escape**: Cancel current tool / SAM2 mode
- **Z**: Undo last SAM2 point
- **1-9**: Select class by number

## Dependencies
All available in the arcgispro-py3-dl conda env:
- flask, rasterio, numpy, Pillow, pyproj, shapely, fiona, geopandas
- torch (2.5.1 + CUDA), sam2, opencv-python

## Common Issues
- **Zombie processes**: Previous Flask processes may hold port 5000. Kill with `taskkill /F /IM python.exe`
- **Compound CRS**: TIFFs have compound CRS (projected + vertical). `_get_horizontal_crs()` handles this via pyproj sub_crs_list
- **SAM2 config lookup**: Config YAML path must include `configs/` prefix (e.g., `configs/sam2.1/sam2.1_hiera_s.yaml`)
- **SAM2 mask dtype**: SAM2 returns numpy bool arrays; must cast to uint8 for rasterio/cv2
- **Module globals**: Flask's `app.run()` can fork processes. Module-level `initialize()` ensures globals are set in the serving process
- **Image overlay alignment**: TIFF pixels are in UTM grid but Leaflet displays as a lat/lng rectangle. A UTM rectangle becomes a trapezoid in 4326, causing ~9px misalignment. Fixed by warping the image to EPSG:4326 with `rasterio.warp.reproject` before serving, and computing bounds from the warped transform via `calculate_default_transform`. Both the PNG and bounds now use the same 4326 pixel grid
