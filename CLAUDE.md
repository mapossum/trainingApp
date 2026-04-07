# Training Data Annotation App

## Overview
A single-user web application for annotating ortho images to create deep learning training data. Flask backend, Leaflet frontend, with SAM2 (Segment Anything Model 2) AI-assisted annotation and ESRI deep learning model prediction.

## Python Environment
```
C:\Users\georg\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe
```
Python 3.13.7 with CUDA-capable GPU support (25.8GB VRAM).

## Running the App
```powershell
cd D:\LR2\LR2_arcgis\trainingApp
C:\Users\georg\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe -u app.py
```
Then open `http://127.0.0.1:5000` in a browser.

### CLI Arguments
```
--data <path>   Data directory (default: data/)
--port <int>    Server port (default: 5000)
```

Run multiple datasets simultaneously:
```powershell
python -u app.py --data data_seagrass    --port 5000
python -u app.py --data data             --port 5001
python -u app.py --data data_conch       --port 5003
python -u app.py --data data_phragmites  --port 5007
```

Or use `restart.py` to start all apps + Cloudflare tunnel at once:
```powershell
python restart.py
```

**Important**: Always use `-u` flag for unbuffered output so logs appear in real time.

**Important**: Kill zombie python.exe processes before restarting. Multiple SAM2 instances consume ~1.2GB each:
```powershell
taskkill /F /IM python.exe
```

## Architecture

### Backend (Python/Flask)
- `app.py` — Flask server, all API routes, SAM2 prediction pipeline, model predict, erase
- `config.py` — Path constants and `set_data_dir()` for runtime data directory switching (supports `--data` CLI arg). Includes `MODELS_DIR` for DL models
- `dataset_config.py` — Auto-detects TIFF properties (bands, dtype, stretch), persists to `data/dataset_config.json`. See `DATASET_CONFIG.md` for full reference
- `tiff_manager.py` — Scans trainingTiffs/, parses filenames, renders PNGs with configurable band selection and stretch, handles any CRS via pyproj
- `annotation_store.py` — GeoJSON CRUD for annotations + app state persistence
- `sam2_predictor.py` — SAM2 model loading with auto-config detection from checkpoint filename
- `model_predictor.py` — ESRI deep learning model inference: .emd parsing, tiled UNet prediction, vectorization, dissolve. Loads models via `arcgis.learn.UnetClassifier.from_model()`
- `export.py` — Exports annotations to GeoJSON + Shapefile with CRS reprojection (current, complete, or all)

### Frontend (JavaScript/HTML/CSS)
- `templates/index.html` — Single-page app with Leaflet + Leaflet-Geoman CDN
- `static/js/app.js` — Main orchestrator, keyboard shortcuts, initialization
- `static/js/map.js` — Leaflet map with Esri World Imagery basemap, image overlay
- `static/js/dataset_config.js` — Band assignment dropdowns, stretch controls, applies changes via API
- `static/js/annotations.js` — GeoJSON annotation layer with debounced auto-save (1s), dissolve, erase, 5-level undo stack, polygon notes
- `static/js/drawing.js` — Polygon draw, freehand draw, edit, delete via Leaflet-Geoman. Supports erase mode
- `static/js/sam.js` — SAM2 click-to-segment with preview, accept/clear action bar. Supports erase mode
- `static/js/select.js` — Select mode: click polygons to select, then bulk delete or change class via action bar
- `static/js/notes.js` — Slide-out notes panel: per-image note textarea + annotation list with click-to-open-popup
- `static/js/model_predict.js` — Predict button: runs DL model inference on current area, adds polygons to map
- `static/js/sidebar.js` — Training area list, sorting, navigation, export buttons, share button, image-note dot indicator
- `static/js/classes.js` — Class selector from config.json with Erase pseudo-class

### Data Structure
Each dataset lives in its own directory (default `data/`, selectable via `--data`):
```
data/                       # or data_seagrass/, data_coral/, etc.
  config.json               # Class definitions (required)
  dataset_config.json       # Auto-generated: band mapping, stretch, nodata (see DATASET_CONFIG.md)
  annotations/              # Working GeoJSON per area (EPSG:4326)
  app_state.json            # Completion flags, last viewed, sort preference
  trainingPolygons/         # Export destination (native CRS)
  trainingTiffs/            # GeoTIFFs (any band count, any CRS, any bit depth)
                            # Also auto-detects: trainingAreas/, tiffs/, images/
  models/                   # Optional: ESRI DL models (.pth + .emd pairs)
  auth.json                 # Optional: {"username":"...","password":"..."} for HTTP Basic Auth
sam2_weights/               # SAM2 checkpoint (.pt file) — shared across datasets
```

### TIFF Format
- **Naming**: Any `.tif` file is accepted. `{OrthoName}_OID{number}.tif` pattern is parsed for ortho_name/oid metadata when present; otherwise the filename stem is the unique key
- **CRS**: Any CRS supported by rasterio/pyproj. Compound CRS (projected + vertical) handled via `_get_horizontal_crs()`
- **Bands**: Any band count supported. Display bands are configurable via `dataset_config.json` — 3 bands are selected for RGB display and SAM2 input
- **Bit depth**: uint8, uint16, int16, float32, float64. Stretch method in `dataset_config.json` maps values to 0-255 for display
- **Nodata**: Auto-detected from TIFF metadata or set in `dataset_config.json`. Nodata pixels rendered as transparent
- **Rendering**: Configurable band selection + stretch -> uint8 RGB -> warp to EPSG:4326 -> RGBA PNG

### Model Prediction
- **Models directory**: Place ESRI-trained `.pth` + `.emd` pairs in `<data_dir>/models/`
- **Supported architectures**: UNet (via `arcgis.learn.UnetClassifier.from_model()`)
- **Pipeline**: Parse .emd metadata -> load model -> tile image (256x256, 64px overlap) -> ImageNet normalize -> batch GPU inference -> average overlapping logits -> argmax -> vectorize per class (same smoothing as SAM2) -> dissolve -> return GeoJSON
- **GPU memory**: Model loaded on demand, unloaded after inference. SAM2 stays resident (~1.2GB)
- If no `models/` directory exists, Predict button is greyed out

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
| POST | `/api/annotations/<id>/dissolve` | Dissolve overlapping polygons of same class |
| POST | `/api/annotations/<id>/erase` | Erase (clip) annotations with a polygon |
| GET | `/api/models` | List available DL prediction models |
| POST | `/api/model-predict` | Run DL model inference on a training area |
| POST | `/api/export/<id>` | Export one area (GeoJSON + Shapefile) |
| POST | `/api/export/complete` | Export all areas marked complete |
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
- **Erase mode**: Pseudo-class in class selector. When active, drawn/freehand/SAM2 polygons clip existing annotations via Shapely `difference()` on the backend
- **Undo**: 5-level snapshot stack in annotations.js. Captures FeatureCollection before each mutation
- **Select mode**: Click to toggle selection on individual polygons. Action bar for bulk class change or delete
- **Smart navigation**: Switching areas only re-centers the map if the new image is off-screen; otherwise the current view is preserved. Fit-to-image button (Leaflet control) for manual zoom-to-extent
- **Draw-through existing polygons**: Draw, Freehand, and SAM2 modes call `Annotations.setInteractive(false)` on activate (pointer-events:none on all annotation layers) so clicks pass through to the map. Restored on deactivate
- **Multispectral model normalization**: `model_predictor.py` checks `IsMultispectral` + `NormalizationStats` in .emd. Uses per-band min/max/mean/std from the .emd instead of hardcoded ImageNet 3-band values
- **Dissolve robustness**: `buffer(0)` applied unconditionally to every input polygon before `unary_union` to repair self-intersections that cause `TopologyException` even on geometries that pass `is_valid`. Falls back to keeping originals if union still fails
- **Predict preview**: model inference results shown as a dashed preview layer (class colors, low opacity). Accept (Enter) or Discard action bar before committing to annotations
- **Fill opacity toggle**: `_fillOpacity` state in annotations.js, `setFillOpacity()`/`getFillOpacity()` API. T key and Fill button toggle between 0.3 and 0. Select module uses `getFillOpacity()` on unselect to stay consistent
- **Export field names**: `class_name`→`classname`, `class_value`→`classvalue` at export time in export.py (rename columns on GeoDataFrame). Internal app continues to use underscored names
- **Toolbar ribbon**: toolbar moved from floating absolute overlay to fixed bottom ribbon (`flex-shrink:0` in flex column). Map flexes to fill remaining space — no occlusion. `flex-wrap:wrap` handles overflow. Responsive breakpoints at 1300px and 1050px shrink padding/font-size
- **Polygon notes**: each annotation has an optional text note stored in `feature.properties.note`. Shown as a Leaflet tooltip on hover (`.note-tooltip` CSS class) and editable via textarea in the click popup. Note saved on blur; tooltip updated live
- **Notes panel**: `notes.js` creates a 280px slide-out panel anchored to right edge of map container. 28px tab ("Notes") always visible; clicking it toggles the panel open/closed. Panel contains: image note textarea (saved to `app_state.json` image_notes on blur) + scrollable annotation list (color swatch, class name, note excerpt; click row opens polygon popup). Panel refreshes on every annotation change
- **Image note dot**: sidebar area list shows a small yellow dot (`.note-dot`) next to the green complete checkmark when an area has a saved image note. Updated live via `Sidebar.updateImageNote()` called from notes.js on blur
- **Deep link**: `?area=<id>` URL parameter loads a specific area on startup (takes priority over last_viewed). Share button (SVG network-share icon) in sidebar nav-controls copies the current area's deep link URL to clipboard via `navigator.clipboard`
- **app_state.json image_notes**: `annotation_store.update_state()` deep-merges `image_notes` the same as `complete` — updating one area's note never overwrites other areas

## Keyboard Shortcuts
- **Left/Right arrows**: Previous/next training area
- **D**: Draw polygon (click vertices)
- **F**: Freehand polygon (click-drag-click)
- **S**: SAM2 click-to-segment mode
- **Q**: Select mode (click polygons to select, then bulk edit)
- **E**: Edit vertices
- **X**: Delete mode
- **W**: Fit image to window (zoom to extent)
- **T**: Toggle polygon fill on/off (outlines only when off)
- **M**: Run model prediction on current area
- **Enter**: Accept SAM2 prediction / Exit edit mode (saves edits)
- **Escape**: Cancel current tool / SAM2 / Select mode
- **Ctrl+Z**: Undo (up to 5 levels)
- **Z**: Undo last SAM2 point (when SAM2 is active)
- **0**: Activate Erase mode
- **1-9**: Select class by number

## Dependencies
All available in the arcgispro-py3-dl conda env:
- flask, rasterio, numpy, Pillow, pyproj, shapely, fiona, geopandas
- torch (2.5.1 + CUDA), sam2, opencv-python
- arcgis.learn (for ESRI model loading)

## Common Issues
- **Zombie processes**: Previous Flask processes may hold port 5000. Kill with `taskkill /F /IM python.exe`
- **Compound CRS**: TIFFs have compound CRS (projected + vertical). `_get_horizontal_crs()` handles this via pyproj sub_crs_list
- **SAM2 config lookup**: Config YAML path must include `configs/` prefix (e.g., `configs/sam2.1/sam2.1_hiera_s.yaml`)
- **SAM2 mask dtype**: SAM2 returns numpy bool arrays; must cast to uint8 for rasterio/cv2
- **Module globals**: Flask's `app.run()` can fork processes. Module-level `initialize()` ensures globals are set in the serving process
- **Image overlay alignment**: TIFF pixels are in UTM grid but Leaflet displays as a lat/lng rectangle. A UTM rectangle becomes a trapezoid in 4326, causing ~9px misalignment. Fixed by warping the image to EPSG:4326 with `rasterio.warp.reproject` before serving, and computing bounds from the warped transform via `calculate_default_transform`. Both the PNG and bounds now use the same 4326 pixel grid
- **Stale processes**: When restarting, ensure ALL old python.exe processes are killed. Old processes on the same port serve stale code. Use `netstat -ano | grep :5000` to find PIDs if `taskkill /F /IM python.exe` doesn't catch them all
- **Corrupt app_state.json**: If `app_state.json` is empty (e.g., after swapping dataset contents), `/api/training-areas` will 500 with a JSONDecodeError. Fix: delete the file and restart — the app creates a fresh one
- **Dissolve TopologyException**: Caused by self-intersecting polygons from aggressive vectorization simplification. Fixed by `buffer(0)` on all inputs before `unary_union`

## Authentication
Optional HTTP Basic Auth, configurable per dataset. Place an `auth.json` in the dataset's data directory:
```json
{
  "username": "annotator",
  "password": "your-password-here"
}
```
- If `auth.json` exists and has valid username/password, all routes require HTTP Basic Auth
- If `auth.json` is missing, the app runs without authentication (local-only use)
- `auth.json` is in `.gitignore` — never commit credentials
- The browser will prompt for credentials on first access and cache them for the session

## Remote Access (Cloudflare Tunnel)
To expose the app to offsite collaborators without VPN or firewall changes:

### Setup
1. Install cloudflared: `winget install cloudflare.cloudflared`
2. Add `auth.json` to the dataset's data directory (see Authentication above)
3. Start the app: `python -u app.py --data data_conch --port 5003`
4. Start the tunnel: `cloudflared tunnel --url http://localhost:5003`
5. Share the generated `*.trycloudflare.com` URL with collaborators

### Active named tunnel
Single tunnel (`0c93bc83`) routes all four hostnames via `~/.cloudflared/config.yml`:
- conch.mapossum.org → localhost:5003
- palmata.mapossum.org → localhost:5001
- phragmites.mapossum.org → localhost:5007

### Notes
- Named tunnel started with: `cloudflared tunnel run` (reads config.yml automatically)
- cloudflared installed at: `C:\Program Files (x86)\cloudflared\cloudflared.exe`
- `restart.py` starts all apps + tunnel together
- Tunnels handle HTTPS automatically — collaborators access via `https://`
- Basic auth credentials are sent over HTTPS so they're encrypted in transit
