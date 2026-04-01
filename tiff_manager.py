import os
import re
import io
import numpy as np
import rasterio
from rasterio.warp import Resampling
from rasterio.vrt import WarpedVRT
from pyproj import CRS as ProjCRS
from pyproj import Transformer
from PIL import Image
from functools import lru_cache

import config
import dataset_config as dscfg


def _parse_filename(filename):
    """Parse a TIFF filename into ortho_name and oid.
    Pattern: {ortho_name}_OID{number}.tif — returns (ortho_name, oid).
    For non-matching filenames, returns (stem, None) so all TIFFs are accepted.
    """
    stem = os.path.splitext(filename)[0]
    match = re.match(r'^(.+)_OID(\d+)$', stem)
    if match:
        return match.group(1), int(match.group(2))
    return stem, None


def _get_horizontal_crs(crs):
    """Extract the horizontal CRS from a potentially compound CRS.
    Returns a pyproj CRS object suitable for coordinate transforms.
    """
    pcrs = ProjCRS.from_wkt(crs.to_wkt())
    if pcrs.is_compound:
        for sub in pcrs.sub_crs_list:
            if sub.type_name == "Projected CRS" or sub.type_name == "Geographic 2D CRS":
                return sub
    return pcrs


class TiffManager:
    def __init__(self):
        self._areas = {}
        self._load_all()

    def _load_all(self):
        """Scan trainingTiffs directory and load metadata for all TIFFs."""
        tiff_dir = config.TIFF_DIR
        if not os.path.isdir(tiff_dir):
            return

        for fname in sorted(os.listdir(tiff_dir)):
            if not fname.lower().endswith('.tif'):
                continue
            ortho_name, oid = _parse_filename(fname)
            area_id = os.path.splitext(fname)[0]
            tiff_path = os.path.join(tiff_dir, fname)

            try:
                with rasterio.open(tiff_path) as ds:
                    native_crs = ds.crs
                    horizontal_crs = _get_horizontal_crs(native_crs)
                    epsg = horizontal_crs.to_epsg()
                    bounds = ds.bounds
                    transform = ds.transform
                    shape = ds.shape
                    band_count = ds.count
                    nodata = ds.nodata

                    # Get bounds from WarpedVRT — exactly matches the PNG
                    with WarpedVRT(ds, crs="EPSG:4326",
                                   resampling=Resampling.bilinear) as vrt:
                        vrt_bounds = vrt.bounds
                        dst_transform = vrt.transform
                        dst_width = vrt.width
                        dst_height = vrt.height
                    west = vrt_bounds.left
                    south = vrt_bounds.bottom
                    east = vrt_bounds.right
                    north = vrt_bounds.top

                self._areas[area_id] = {
                    'id': area_id,
                    'filename': fname,
                    'ortho_name': ortho_name,
                    'oid': oid,
                    'tiff_path': tiff_path,
                    'native_crs': native_crs,
                    'horizontal_crs': horizontal_crs,
                    'epsg': epsg,
                    'bounds_native': bounds,
                    'transform': transform,
                    'shape': shape,
                    'band_count': band_count,
                    'nodata': nodata,
                    'bounds_4326': [[south, west], [north, east]],
                    'center_4326': [(south + north) / 2, (west + east) / 2],
                    'dst_transform': dst_transform,
                    'dst_shape': (dst_height, dst_width),
                }
            except Exception as e:
                print(f"Warning: could not load {fname}: {e}")

    def get_area_ids(self):
        """Return sorted list of all area IDs."""
        return sorted(self._areas.keys())

    def get_area(self, area_id):
        """Return metadata dict for a single area, or None."""
        return self._areas.get(area_id)

    def get_all_areas_summary(self):
        """Return list of area summaries for the frontend."""
        result = []
        for area_id in sorted(self._areas.keys()):
            a = self._areas[area_id]
            result.append({
                'id': a['id'],
                'filename': a['filename'],
                'ortho_name': a['ortho_name'],
                'oid': a['oid'],
                'bounds_4326': a['bounds_4326'],
                'center_4326': a['center_4326'],
                'epsg': a['epsg'],
            })
        return result

    def _cache_keys(self):
        """Return (bands_tuple, stretch_key) for lru_cache keying."""
        bands, stretch = _get_display_config()
        bands_tuple = tuple(bands)
        stretch_key = (
            stretch.get("method", "clip255"),
            tuple(stretch.get("band_mins", [])),
            tuple(stretch.get("band_maxs", [])),
        )
        return bands_tuple, stretch_key

    def render_png(self, area_id):
        """Render a TIFF as RGBA PNG bytes, warped to EPSG:4326."""
        area = self._areas.get(area_id)
        if not area:
            return None
        bands_tuple, stretch_key = self._cache_keys()
        return _render_png_warped(area['tiff_path'], area['nodata'],
                                  bands_tuple, stretch_key)

    def get_image_array(self, area_id):
        """Get the RGB uint8 numpy array for SAM2. Returns (H, W, 3) or None."""
        area = self._areas.get(area_id)
        if not area:
            return None
        bands_tuple, stretch_key = self._cache_keys()
        return _load_image_array(area['tiff_path'], area['nodata'],
                                 bands_tuple, stretch_key)

    @staticmethod
    def clear_render_cache():
        """Clear cached renders (call after changing display bands or stretch)."""
        _load_image_array.cache_clear()
        _render_png_warped.cache_clear()

    def geo_to_pixel(self, area_id, lng, lat):
        """Convert lng/lat (EPSG:4326) to pixel coordinates (col, row)."""
        area = self._areas.get(area_id)
        if not area:
            return None, None
        transformer = Transformer.from_crs(
            "EPSG:4326", area['horizontal_crs'], always_xy=True
        )
        x_native, y_native = transformer.transform(lng, lat)
        col, row = ~area['transform'] * (x_native, y_native)
        return col, row


def _get_display_config():
    """Get display bands and stretch config from dataset_config."""
    cfg = dscfg.load()
    if cfg is None:
        cfg = dscfg.auto_detect()
    bands = cfg.get("display_bands", [1, 2, 3])
    stretch = cfg.get("stretch", {})
    return bands, stretch


def _apply_stretch(data, stretch, nodata=None):
    """Apply stretch to multi-band data. data: (N, H, W) float64.

    Returns (3, H, W) uint8 array and nodata_mask (H, W) bool.
    """
    method = stretch.get("method", "clip255")
    band_mins = stretch.get("band_mins", [0.0] * data.shape[0])
    band_maxs = stretch.get("band_maxs", [255.0] * data.shape[0])

    # Build nodata mask from original values
    if nodata is not None:
        nodata_mask = np.any(data == nodata, axis=0)
    else:
        nodata_mask = np.zeros(data.shape[1:], dtype=bool)

    result = np.zeros_like(data, dtype=np.float64)
    for i in range(data.shape[0]):
        bmin = band_mins[i] if i < len(band_mins) else 0.0
        bmax = band_maxs[i] if i < len(band_maxs) else 255.0

        if method == "none" or method == "clip255":
            result[i] = np.clip(data[i], 0, 255)
        else:
            # Linear stretch: map [bmin, bmax] -> [0, 255]
            if bmax > bmin:
                result[i] = (data[i] - bmin) / (bmax - bmin) * 255.0
            else:
                result[i] = 0.0
            result[i] = np.clip(result[i], 0, 255)

    return result.astype(np.uint8), nodata_mask


@lru_cache(maxsize=50)
def _load_image_array(tiff_path, nodata, bands_tuple, stretch_key):
    """Load TIFF as RGB uint8 array (H, W, 3). Cached.

    bands_tuple: tuple of band indices (1-based).
    stretch_key: hashable representation of stretch config for cache keying.
    """
    bands, stretch = _get_display_config()
    with rasterio.open(tiff_path) as ds:
        # Read requested bands, fall back gracefully if band doesn't exist
        actual_bands = [b for b in bands if b <= ds.count]
        while len(actual_bands) < 3:
            actual_bands.append(actual_bands[-1] if actual_bands else 1)

        data = ds.read(actual_bands).astype(np.float64)  # (3, H, W)

    rgb, nodata_mask = _apply_stretch(data, stretch, nodata)
    rgb = rgb.transpose(1, 2, 0)  # (H, W, 3)
    rgb[nodata_mask] = 0
    return rgb


@lru_cache(maxsize=50)
def _render_png_warped(tiff_path, nodata, bands_tuple, stretch_key):
    """Render TIFF to RGBA PNG bytes, warped to EPSG:4326 via WarpedVRT.

    Warping ensures the pixel grid matches Leaflet's coordinate system,
    eliminating the misalignment caused by displaying a UTM image as
    an axis-aligned rectangle in lat/lng space.
    """
    from rasterio.crs import CRS as RioCRS

    bands, stretch = _get_display_config()
    dst_crs = RioCRS.from_epsg(4326)

    with rasterio.open(tiff_path) as ds:
        with WarpedVRT(ds, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
            actual_bands = [b for b in bands if b <= vrt.count]
            while len(actual_bands) < 3:
                actual_bands.append(actual_bands[-1] if actual_bands else 1)

            data = vrt.read(actual_bands).astype(np.float64)  # (3, H, W)

    rgb, nodata_mask = _apply_stretch(data, stretch, nodata)

    # Also mask pixels that are all zeros (outside source extent after warp)
    zero_mask = np.all(rgb == 0, axis=0)
    alpha = np.where(nodata_mask | zero_mask, 0, 255).astype(np.uint8)

    rgba = np.concatenate([rgb, alpha[np.newaxis]], axis=0)  # (4, H, W)
    rgba = rgba.transpose(1, 2, 0)  # (H, W, 4)

    img = Image.fromarray(rgba, 'RGBA')
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=False)
    return buf.getvalue()
