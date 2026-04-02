"""Deep learning model inference for pre-generating annotation polygons.

Loads ESRI-trained models (.pth + .emd) and runs tiled inference on training
area TIFFs, producing vectorized polygons per class.
"""

import os
import json
import logging

import numpy as np
import torch
import cv2
import rasterio
import rasterio.features
from rasterio.transform import Affine as RioAffine
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as shapely_transform
from pyproj import Transformer

logger = logging.getLogger('training_app')

# Module state
_models = []  # list of parsed emd configs


def _parse_emd(emd_path):
    """Parse an ESRI Model Definition file into a config dict."""
    with open(emd_path, 'r') as f:
        emd = json.load(f)

    emd_dir = os.path.dirname(os.path.abspath(emd_path))
    model_file = emd.get('ModelFile', '')
    pth_path = os.path.join(emd_dir, model_file)

    classes = []
    for cls in emd.get('Classes', []):
        classes.append({
            'value': cls['Value'],
            'name': cls['Name'],
            'color': cls.get('Color', [0, 255, 0]),
        })

    # Total output channels = max class value + 1 (background is 0)
    num_classes = max((c['value'] for c in classes), default=0) + 1

    return {
        'name': os.path.splitext(os.path.basename(emd_path))[0],
        'emd_path': os.path.abspath(emd_path),
        'pth_path': pth_path,
        'model_name': emd.get('ModelName', 'unknown'),
        'architecture': emd.get('ModelConfiguration', '').lstrip('_'),
        'backbone': emd.get('ModelParameters', {}).get('backbone', 'unknown'),
        'tile_size': emd.get('ImageHeight', 256),
        'extract_bands': emd.get('ExtractBands', [0, 1, 2]),
        'format': emd.get('ModelFormat', 'NCHW'),
        'is_imagenet_norm': emd.get('IsImageNetNormalization', False),
        'is_multispectral': emd.get('IsMultispectral', False),
        'normalization_stats': emd.get('NormalizationStats', None),
        'classes': classes,
        'num_classes': num_classes,
    }


def scan_models(models_dir):
    """Find .emd/.pth model pairs in a directory."""
    models = []
    if not os.path.isdir(models_dir):
        return models

    for fname in os.listdir(models_dir):
        if fname.lower().endswith('.emd'):
            emd_path = os.path.join(models_dir, fname)
            try:
                cfg = _parse_emd(emd_path)
                if os.path.isfile(cfg['pth_path']):
                    models.append(cfg)
                    logger.info(f"Found model: {cfg['name']} "
                                f"({cfg['architecture']}/{cfg['backbone']}, "
                                f"{len(cfg['classes'])} classes)")
                else:
                    logger.warning(f"Model {fname}: .pth file not found at {cfg['pth_path']}")
            except Exception as e:
                logger.warning(f"Failed to parse {fname}: {e}")

    return models


def init(models_dir):
    """Scan for models at startup."""
    global _models
    _models = scan_models(models_dir)
    logger.info(f"Found {len(_models)} prediction model(s)")


def get_available_models():
    """Return model info for the API (lightweight, no model objects)."""
    return [{
        'name': m['name'],
        'architecture': m['architecture'],
        'backbone': m['backbone'],
        'tile_size': m['tile_size'],
        'classes': m['classes'],
    } for m in _models]


def _load_pytorch_model(emd_config):
    """Load the PyTorch model from an ESRI .emd/.pth pair."""
    from arcgis.learn import UnetClassifier
    model_obj = UnetClassifier.from_model(emd_config['emd_path'], data=None)
    pytorch_model = model_obj.learn.model
    pytorch_model.eval()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    pytorch_model = pytorch_model.to(device)
    return pytorch_model, device


def _read_raw_bands(tiff_path, extract_bands):
    """Read raw bands from TIFF. extract_bands is 0-indexed."""
    with rasterio.open(tiff_path) as ds:
        rio_bands = [b + 1 for b in extract_bands]
        data = ds.read(rio_bands)  # (C, H, W)
        return data.transpose(1, 2, 0)  # (H, W, C)


def _generate_tiles(H, W, tile_size, overlap):
    """Generate (y1, x1, y2, x2) tile coordinates with overlap."""
    stride = tile_size - overlap
    tiles = []
    for y in range(0, H, stride):
        for x in range(0, W, stride):
            y2 = min(y + tile_size, H)
            x2 = min(x + tile_size, W)
            y1 = max(0, y2 - tile_size)
            x1 = max(0, x2 - tile_size)
            tiles.append((y1, x1, y2, x2))
    return tiles


def _vectorize_mask(mask, transform, horizontal_crs, pixel_size, scale=4, simplify_factor=0.25):
    """Convert a binary mask to a list of Shapely polygons in EPSG:4326.

    Uses the same smoothing pipeline as SAM2: upsample, Gaussian blur,
    rasterio vectorize, simplify, reproject.
    """
    mask_255 = (mask * 255).astype(np.uint8)
    mask_up = cv2.resize(mask_255,
                         (mask.shape[1] * scale, mask.shape[0] * scale),
                         interpolation=cv2.INTER_NEAREST)

    mask_up = cv2.GaussianBlur(mask_up, (7, 7), sigmaX=2.0)
    _, mask_up = cv2.threshold(mask_up, 127, 255, cv2.THRESH_BINARY)

    upscaled_transform = transform * RioAffine.scale(1.0 / scale)
    mask_binary = (mask_up > 0).astype(np.uint8)

    shapes_gen = list(rasterio.features.shapes(
        mask_binary,
        mask=mask_binary,
        transform=upscaled_transform,
    ))

    transformer = Transformer.from_crs(horizontal_crs, "EPSG:4326", always_xy=True)
    polygons = []
    for geom, value in shapes_gen:
        if value == 1:
            poly = shape(geom)
            poly = poly.simplify(pixel_size * simplify_factor)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            poly_4326 = shapely_transform(transformer.transform, poly)
            polygons.append(poly_4326)

    return polygons


def _dissolve_polygons(polygons):
    """Dissolve a list of polygons into non-overlapping polygons."""
    if len(polygons) <= 1:
        return polygons

    merged = unary_union(polygons)
    if not merged.is_valid:
        merged = merged.buffer(0)

    result = []
    if merged.geom_type == 'MultiPolygon':
        result.extend(list(merged.geoms))
    elif merged.geom_type == 'Polygon':
        result.append(merged)

    return result


def predict(model_name, tiff_path, transform, native_crs, horizontal_crs, pixel_size, overlap=64):
    """Run tiled model inference on a TIFF and return GeoJSON features.

    Loads the model, runs inference, unloads. Returns a list of GeoJSON
    Feature dicts in EPSG:4326 with class_name, class_value, source properties.
    """
    # Find model config
    model_cfg = None
    for m in _models:
        if m['name'] == model_name:
            model_cfg = m
            break
    if model_cfg is None:
        raise ValueError(f"Model '{model_name}' not found")

    tile_size = model_cfg['tile_size']
    extract_bands = model_cfg['extract_bands']
    is_imagenet = model_cfg['is_imagenet_norm']
    is_multispectral = model_cfg['is_multispectral']
    norm_stats = model_cfg['normalization_stats']
    num_classes = model_cfg['num_classes']
    classes = model_cfg['classes']

    # Load model
    logger.info(f"Loading model '{model_name}'...")
    pytorch_model, device = _load_pytorch_model(model_cfg)
    logger.info("Model loaded")

    try:
        # Read raw image bands
        image = _read_raw_bands(tiff_path, extract_bands)  # (H, W, C)
        H, W, C = image.shape
        logger.info(f"Image shape: {H}x{W}x{C}")

        # Generate tiles
        tiles = _generate_tiles(H, W, tile_size, overlap)
        logger.info(f"Generated {len(tiles)} tiles ({tile_size}x{tile_size}, overlap={overlap})")

        # Normalization setup
        if is_multispectral and norm_stats:
            # Use per-band stats from .emd (scaled to 0-1 range)
            band_min = np.array(norm_stats['band_min_values'], dtype=np.float32)
            band_max = np.array(norm_stats['band_max_values'], dtype=np.float32)
            band_range = np.maximum(band_max - band_min, 1.0)
            scaled_mean = np.array(norm_stats['scaled_mean_values'], dtype=np.float32)
            scaled_std = np.array(norm_stats['scaled_std_values'], dtype=np.float32)
            use_custom_norm = True
        elif is_imagenet:
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            use_custom_norm = False
        else:
            use_custom_norm = False

        # Run inference on all tiles, accumulate logits
        prediction_sum = np.zeros((num_classes, H, W), dtype=np.float32)
        count = np.zeros((H, W), dtype=np.float32)

        with torch.no_grad():
            for i, (y1, x1, y2, x2) in enumerate(tiles):
                tile = image[y1:y2, x1:x2].copy()  # (th, tw, C)
                th, tw = tile.shape[:2]

                # Pad if tile is smaller than tile_size (edge tiles)
                if th < tile_size or tw < tile_size:
                    padded = np.zeros((tile_size, tile_size, C), dtype=tile.dtype)
                    padded[:th, :tw] = tile
                    # Reflect-pad for better edge predictions
                    if th < tile_size:
                        for row in range(th, tile_size):
                            padded[row, :tw] = tile[th - 1, :]
                    if tw < tile_size:
                        for col in range(tw, tile_size):
                            padded[:, col] = padded[:, tw - 1]
                    tile = padded

                # Normalize to float32
                tile_f = tile.astype(np.float32)
                if use_custom_norm:
                    # Scale to 0-1 using band min/max, then normalize with scaled stats
                    tile_f = (tile_f - band_min) / band_range
                    tile_f = (tile_f - scaled_mean) / scaled_std
                elif is_imagenet:
                    tile_f = tile_f / 255.0
                    tile_f = (tile_f - mean) / std
                else:
                    tile_f = tile_f / 255.0

                # Convert to NCHW tensor
                tensor = torch.from_numpy(tile_f.transpose(2, 0, 1)).unsqueeze(0).to(device)

                # Inference
                output = pytorch_model(tensor)  # (1, num_classes, tile_size, tile_size)
                logits = output[0].cpu().numpy()  # (num_classes, tile_size, tile_size)

                # Accumulate only the valid (non-padded) region
                prediction_sum[:, y1:y2, x1:x2] += logits[:, :th, :tw]
                count[y1:y2, x1:x2] += 1.0

        # Average overlapping predictions and get class map
        count = np.maximum(count, 1.0)
        prediction_avg = prediction_sum / count[np.newaxis, ...]
        class_map = np.argmax(prediction_avg, axis=0).astype(np.uint8)  # (H, W)

        logger.info(f"Class map unique values: {np.unique(class_map).tolist()}")

        # Vectorize each non-background class
        all_features = []
        for cls_info in classes:
            cv = cls_info['value']
            cls_name = cls_info['name']

            mask = (class_map == cv).astype(np.uint8)
            if mask.sum() == 0:
                continue

            logger.info(f"Vectorizing class '{cls_name}' (value={cv}): {mask.sum()} pixels")

            polygons = _vectorize_mask(mask, transform, horizontal_crs, pixel_size)
            if not polygons:
                continue

            # Dissolve overlapping polygons from tile overlap
            polygons = _dissolve_polygons(polygons)
            logger.info(f"  -> {len(polygons)} polygons after dissolve")

            for poly in polygons:
                if poly.is_empty:
                    continue
                all_features.append({
                    "type": "Feature",
                    "geometry": mapping(poly),
                    "properties": {
                        "class_name": cls_name,
                        "class_value": cv,
                        "source": "model_predict",
                    },
                })

        logger.info(f"Model prediction complete: {len(all_features)} features")
        return all_features

    finally:
        # Always unload model to free GPU memory
        del pytorch_model
        torch.cuda.empty_cache()
        logger.info("Model unloaded")
