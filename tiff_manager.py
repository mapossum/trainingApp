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


def _parse_filename(filename):
    """Parse a TIFF filename into ortho_name and oid.
    Pattern: {ortho_name}_OID{number}.tif
    """
    stem = os.path.splitext(filename)[0]
    match = re.match(r'^(.+)_OID(\d+)$', stem)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


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
            if ortho_name is None:
                continue

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

    def render_png(self, area_id):
        """Render a TIFF as RGBA PNG bytes, warped to EPSG:4326."""
        area = self._areas.get(area_id)
        if not area:
            return None
        return _render_png_warped(area['tiff_path'], area['nodata'])

    def get_image_array(self, area_id):
        """Get the RGB uint8 numpy array for SAM2. Returns (H, W, 3) or None."""
        area = self._areas.get(area_id)
        if not area:
            return None
        return _load_image_array(area['tiff_path'], area['nodata'])

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


@lru_cache(maxsize=50)
def _load_image_array(tiff_path, nodata):
    """Load TIFF as RGB uint8 array (H, W, 3). Cached."""
    with rasterio.open(tiff_path) as ds:
        rgb = ds.read([1, 2, 3])  # (3, H, W), uint16
        if nodata is not None:
            nodata_mask = np.any(rgb >= int(nodata), axis=0)
        else:
            nodata_mask = None
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        rgb = rgb.transpose(1, 2, 0)  # (H, W, 3)
        if nodata_mask is not None:
            rgb[nodata_mask] = 0
        return rgb


@lru_cache(maxsize=50)
def _render_png_warped(tiff_path, nodata):
    """Render TIFF to RGBA PNG bytes, warped to EPSG:4326 via WarpedVRT.

    Warping ensures the pixel grid matches Leaflet's coordinate system,
    eliminating the misalignment caused by displaying a UTM image as
    an axis-aligned rectangle in lat/lng space.
    """
    from rasterio.crs import CRS as RioCRS

    dst_crs = RioCRS.from_epsg(4326)

    with rasterio.open(tiff_path) as ds:
        with WarpedVRT(ds, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
            rgb = vrt.read([1, 2, 3])  # (3, H, W), uint16

            # Build alpha: nodata -> transparent
            if nodata is not None:
                nodata_mask = np.any(rgb >= int(nodata), axis=0)
            else:
                nodata_mask = np.zeros(rgb.shape[1:], dtype=bool)

            # Also mask pixels that are all zeros (outside source extent after warp)
            zero_mask = np.all(rgb == 0, axis=0)
            alpha = np.where(nodata_mask | zero_mask, 0, 255).astype(np.uint8)

            rgb = np.clip(rgb, 0, 255).astype(np.uint8)
            rgba = np.concatenate([rgb, alpha[np.newaxis]], axis=0)  # (4, H, W)
            rgba = rgba.transpose(1, 2, 0)  # (H, W, 4)

    img = Image.fromarray(rgba, 'RGBA')
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=False)
    return buf.getvalue()
