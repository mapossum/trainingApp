import io
import json
import numpy as np
from flask import Flask, render_template, jsonify, request, send_file

import config
import annotation_store
import dataset_config as dscfg
import export
import sam2_predictor
from tiff_manager import TiffManager

app = Flask(__name__)
tiff_mgr = None
_sam2_service = None
_sam2_ready = False


import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger('training_app')


def initialize():
    """Initialize TIFF manager and SAM2. Called once before serving."""
    global tiff_mgr, _sam2_service, _sam2_ready

    logger.info("Auto-detecting dataset configuration...")
    sys.stdout.flush()
    ds_cfg = dscfg.auto_detect()
    logger.info(f"Dataset config: {ds_cfg['band_count']} bands, "
                f"display={ds_cfg['display_bands']}, "
                f"stretch={ds_cfg['stretch']['method']}")

    logger.info("Initializing TIFF manager...")
    sys.stdout.flush()
    tiff_mgr = TiffManager()
    logger.info(f"Loaded {len(tiff_mgr.get_area_ids())} training areas")

    logger.info("Initializing SAM2...")
    sam2_predictor.init_sam2()
    _sam2_service = sam2_predictor.get_service()
    _sam2_ready = _sam2_service is not None
    logger.info(f"SAM2 available: {_sam2_ready}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config')
def get_config():
    with open(config.CONFIG_PATH, 'r') as f:
        classes = json.load(f)
    return jsonify(classes)


@app.route('/api/dataset-config')
def get_dataset_config():
    cfg = dscfg.load()
    if cfg is None:
        cfg = dscfg.auto_detect()
    return jsonify(cfg)


@app.route('/api/dataset-config', methods=['PUT'])
def update_dataset_config():
    updates = request.get_json()
    cfg = dscfg.load()
    if cfg is None:
        cfg = dscfg.auto_detect()

    changed_bands = False
    changed_stretch = False

    if 'display_bands' in updates:
        cfg['display_bands'] = updates['display_bands']
        changed_bands = True

    if 'stretch' in updates:
        for key in ('method', 'percentile_min', 'percentile_max'):
            if key in updates['stretch']:
                cfg['stretch'][key] = updates['stretch'][key]
                changed_stretch = True
        # Allow direct min/max override
        if 'band_mins' in updates['stretch']:
            cfg['stretch']['band_mins'] = updates['stretch']['band_mins']
            changed_stretch = True
        if 'band_maxs' in updates['stretch']:
            cfg['stretch']['band_maxs'] = updates['stretch']['band_maxs']
            changed_stretch = True

    # Recalculate stretch if bands changed but mins/maxs weren't explicitly set
    if changed_bands and 'band_mins' not in updates.get('stretch', {}):
        cfg = dscfg.recalculate_stretch(
            display_bands=cfg['display_bands'],
            method=cfg['stretch']['method'],
            percentile_min=cfg['stretch']['percentile_min'],
            percentile_max=cfg['stretch']['percentile_max'],
        )
    elif changed_stretch and 'band_mins' not in updates.get('stretch', {}):
        cfg = dscfg.recalculate_stretch(
            method=cfg['stretch']['method'],
            percentile_min=cfg['stretch']['percentile_min'],
            percentile_max=cfg['stretch']['percentile_max'],
        )
    else:
        dscfg.save(cfg)

    # Clear render caches so new settings take effect
    tiff_mgr.clear_render_cache()

    return jsonify(cfg)


@app.route('/api/dataset-config/redetect', methods=['POST'])
def redetect_dataset_config():
    """Force re-detection of dataset properties from TIFFs."""
    cfg = dscfg.auto_detect(force=True)
    tiff_mgr.clear_render_cache()
    return jsonify(cfg)


@app.route('/api/training-areas')
def get_training_areas():
    areas = tiff_mgr.get_all_areas_summary()
    state = annotation_store.load_state()
    complete_map = state.get("complete", {})
    for a in areas:
        a['annotation_count'] = annotation_store.get_annotation_count(a['id'])
        a['complete'] = complete_map.get(a['id'], False)
    return jsonify(areas)


@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(annotation_store.load_state())


@app.route('/api/state', methods=['POST'])
def update_state():
    updates = request.get_json()
    state = annotation_store.update_state(updates)
    return jsonify(state)


@app.route('/api/tiff/<area_id>/image.png')
def get_tiff_image(area_id):
    png_bytes = tiff_mgr.render_png(area_id)
    if png_bytes is None:
        return jsonify({"error": "Area not found"}), 404
    return send_file(io.BytesIO(png_bytes), mimetype='image/png')


@app.route('/api/tiff/<area_id>/bounds')
def get_tiff_bounds(area_id):
    area = tiff_mgr.get_area(area_id)
    if area is None:
        return jsonify({"error": "Area not found"}), 404
    return jsonify({"bounds": area['bounds_4326']})


@app.route('/api/annotations/<area_id>', methods=['GET'])
def get_annotations(area_id):
    return jsonify(annotation_store.load_annotations(area_id))


@app.route('/api/annotations/<area_id>', methods=['PUT'])
def save_annotations(area_id):
    fc = request.get_json()
    annotation_store.save_annotations(area_id, fc)
    return jsonify({"status": "ok", "count": len(fc.get("features", []))})


@app.route('/api/annotations/<area_id>/dissolve', methods=['POST'])
def dissolve_annotations(area_id):
    """Dissolve overlapping polygons of the same class into unified polygons."""
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    from collections import defaultdict

    fc = annotation_store.load_annotations(area_id)
    features = fc.get("features", [])
    if len(features) < 2:
        return jsonify(fc)

    # Group by class_value
    groups = defaultdict(list)
    for f in features:
        cv = f.get("properties", {}).get("class_value")
        groups[cv].append(f)

    new_features = []
    for cv, group_features in groups.items():
        if len(group_features) < 2:
            new_features.extend(group_features)
            continue

        # Build shapely geometries
        polys = []
        for f in group_features:
            try:
                polys.append(shape(f["geometry"]))
            except Exception:
                continue

        # Union all polygons in this class
        merged = unary_union(polys)
        if not merged.is_valid:
            merged = merged.buffer(0)

        # Get properties template from first feature
        props = dict(group_features[0].get("properties", {}))

        # Split MultiPolygon into individual features
        if merged.geom_type == 'MultiPolygon':
            for geom in merged.geoms:
                new_features.append({
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": dict(props),
                })
        elif merged.geom_type == 'Polygon':
            new_features.append({
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": dict(props),
            })

    result = {
        "type": "FeatureCollection",
        "properties": {"area_id": area_id},
        "features": new_features,
    }

    annotation_store.save_annotations(area_id, result)
    before = len(features)
    after = len(new_features)
    logger.info(f"Dissolve {area_id}: {before} -> {after} features")

    return jsonify(result)


@app.route('/api/sam2/status')
def sam2_status():
    return jsonify({"available": _sam2_ready})


@app.route('/api/sam2/predict', methods=['POST'])
def sam2_predict():
    import traceback
    import cv2
    import rasterio.features
    from rasterio.transform import Affine as RioAffine
    from shapely.geometry import shape, mapping
    from shapely.ops import transform as shapely_transform
    from pyproj import Transformer

    if not _sam2_ready:
        return jsonify({"error": "SAM2 not available"}), 503

    try:
        data = request.get_json()
        area_id = data.get('area_id')
        points = data.get('points', [])

        if not area_id or not points:
            return jsonify({"error": "area_id and points required"}), 400

        area = tiff_mgr.get_area(area_id)
        if not area:
            return jsonify({"error": "Area not found"}), 404

        # Load image for SAM2
        image_array = tiff_mgr.get_image_array(area_id)
        if image_array is None:
            return jsonify({"error": "Could not load image"}), 500

        service = _sam2_service
        service.set_image(area_id, image_array)

        # Convert geo points to pixel coordinates
        pixel_points = []
        labels = []
        for pt in points:
            col, row = tiff_mgr.geo_to_pixel(area_id, pt['lng'], pt['lat'])
            pixel_points.append([col, row])
            labels.append(pt.get('label', 1))

        point_coords = np.array(pixel_points, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)

        logger.info(f"SAM2 predict: area={area_id}, points={point_coords.tolist()}, labels={point_labels.tolist()}")

        # Run prediction
        mask, score = service.predict(point_coords, point_labels)

        # Ensure mask is a proper numpy array
        if hasattr(mask, 'cpu'):
            mask = mask.cpu().numpy()
        mask = np.asarray(mask, dtype=np.uint8)

        logger.info(f"SAM2 result: score={score:.3f}, mask_sum={mask.sum()}, shape={mask.shape}")

        if mask.sum() == 0:
            return jsonify({"error": "No polygon detected"}), 200

        # --- Smooth vectorization ---
        # 1. Upsample mask 4x for sub-pixel resolution
        scale = 4
        mask_255 = (mask * 255).astype(np.uint8)
        mask_up = cv2.resize(mask_255,
                             (mask.shape[1] * scale, mask.shape[0] * scale),
                             interpolation=cv2.INTER_NEAREST)

        # 2. Gaussian blur to smooth staircase edges, then re-threshold
        mask_up = cv2.GaussianBlur(mask_up, (7, 7), sigmaX=2.0)
        _, mask_up = cv2.threshold(mask_up, 127, 255, cv2.THRESH_BINARY)

        # 3. Use rasterio to vectorize the smoothed upscaled mask
        #    Scale the affine transform to match the upscaled pixel grid.
        #    This ensures coordinates are computed identically to the image overlay.
        upscaled_transform = area['transform'] * RioAffine.scale(1.0 / scale)
        mask_binary = (mask_up > 0).astype(np.uint8)
        shapes_gen = list(rasterio.features.shapes(
            mask_binary,
            mask=mask_binary,
            transform=upscaled_transform
        ))

        # 4. Find the largest foreground polygon
        best_poly = None
        best_area_val = 0
        for geom, value in shapes_gen:
            if value == 1:
                poly = shape(geom)
                if poly.area > best_area_val:
                    best_area_val = poly.area
                    best_poly = poly

        if best_poly is None:
            return jsonify({"error": "No polygon detected"}), 200

        # 5. Simplify to reduce vertices while keeping smooth curves
        #    Tolerance ~0.25 of a pixel in native CRS units
        pixel_size = abs(area['transform'].a)
        best_poly = best_poly.simplify(pixel_size * 0.25)

        if not best_poly.is_valid:
            best_poly = best_poly.buffer(0)

        # 6. Reproject to EPSG:4326
        transformer = Transformer.from_crs(
            area['horizontal_crs'], "EPSG:4326", always_xy=True
        )
        poly_4326 = shapely_transform(transformer.transform, best_poly)

        feature = {
            "type": "Feature",
            "geometry": mapping(poly_4326),
            "properties": {"score": score, "source": "sam2"}
        }

        return jsonify({"polygon": feature})

    except Exception as e:
        logger.error(f"SAM2 prediction error: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/export/<area_id>', methods=['POST'])
def export_area(area_id):
    result = export.export_area(area_id, tiff_mgr)
    if result is None:
        return jsonify({"error": "No annotations to export"}), 400
    geojson_path, shp_path = result
    return jsonify({
        "status": "ok",
        "geojson": geojson_path,
        "shapefile": shp_path
    })


@app.route('/api/export/all', methods=['POST'])
def export_all():
    exported = export.export_all(tiff_mgr)
    return jsonify({"status": "ok", "exported": exported, "count": len(exported)})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Training Data Annotation App')
    parser.add_argument('--data', type=str, default=None,
                        help='Path to data directory (default: data/)')
    parser.add_argument('--port', type=int, default=5000,
                        help='Server port (default: 5000)')
    args = parser.parse_args()

    if args.data:
        config.set_data_dir(args.data)
        logger.info(f"Using data directory: {config.DATA_DIR}")
        logger.info(f"TIFF directory: {config.TIFF_DIR}")

    initialize()
    print(f"Starting server on port {args.port}...")
    app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False, threaded=True)
else:
    # When imported (not run directly), initialize with defaults
    initialize()
