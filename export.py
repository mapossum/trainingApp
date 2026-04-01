import os
import json
import geopandas as gpd
from shapely.geometry import shape

import config
import annotation_store


def export_area(area_id, tiff_manager):
    """Export annotations for one area to GeoJSON + Shapefile in trainingPolygons/.
    Reprojects from EPSG:4326 to the native CRS of the source TIFF.
    Returns (geojson_path, shp_path) or None if no annotations.
    """
    fc = annotation_store.load_annotations(area_id)
    features = fc.get("features", [])
    if not features:
        return None

    area = tiff_manager.get_area(area_id)
    if not area:
        return None

    # Build GeoDataFrame from features
    geometries = []
    properties_list = []
    for feat in features:
        geom = shape(feat["geometry"])
        props = dict(feat.get("properties", {}))
        geometries.append(geom)
        properties_list.append(props)

    gdf = gpd.GeoDataFrame(properties_list, geometry=geometries, crs="EPSG:4326")

    # Reproject to native CRS
    target_crs = area['horizontal_crs']
    gdf = gdf.to_crs(target_crs.to_epsg())

    # Write GeoJSON
    geojson_path = os.path.join(config.EXPORT_DIR, f"{area_id}.geojson")
    gdf.to_file(geojson_path, driver="GeoJSON")

    # Write Shapefile
    shp_path = os.path.join(config.EXPORT_DIR, f"{area_id}.shp")
    gdf.to_file(shp_path, driver="ESRI Shapefile")

    return geojson_path, shp_path


def export_all(tiff_manager):
    """Export all areas that have annotations. Returns list of exported area_ids."""
    exported = []
    annotations_dir = config.ANNOTATIONS_DIR
    if not os.path.isdir(annotations_dir):
        return exported

    for fname in os.listdir(annotations_dir):
        if not fname.endswith('.geojson'):
            continue
        area_id = fname[:-8]  # strip .geojson
        result = export_area(area_id, tiff_manager)
        if result:
            exported.append(area_id)

    return exported
