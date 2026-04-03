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

    # Rename fields to ArcGIS deep learning preferred names (no underscores)
    rename = {}
    if 'class_name' in gdf.columns:
        rename['class_name'] = 'classname'
    if 'class_value' in gdf.columns:
        rename['class_value'] = 'classvalue'
    if rename:
        gdf = gdf.rename(columns=rename)

    # Ensure classvalue is integer (LONG), not float
    if 'classvalue' in gdf.columns:
        gdf['classvalue'] = gdf['classvalue'].fillna(0).astype('int32')

    # Write GeoJSON
    geojson_path = os.path.join(config.EXPORT_DIR, f"{area_id}.geojson")
    gdf.to_file(geojson_path, driver="GeoJSON")

    # Write Shapefile
    shp_path = os.path.join(config.EXPORT_DIR, f"{area_id}.shp")
    gdf.to_file(shp_path, driver="ESRI Shapefile")

    return geojson_path, shp_path


def _write_empty_list(empty_ids, tiff_manager, label):
    """Write a no_annotations.txt TSV listing areas in the export with no annotations."""
    os.makedirs(config.EXPORT_DIR, exist_ok=True)
    path = os.path.join(config.EXPORT_DIR, "no_annotations.txt")
    with open(path, 'w') as f:
        f.write(f"# Areas without annotations ({label})\n")
        f.write("imagename\toid\n")
        for area_id in sorted(empty_ids):
            area = tiff_manager.get_area(area_id)
            if area and area.get('ortho_name'):
                f.write(f"{area['ortho_name']}\t{area.get('oid', '')}\n")
            else:
                f.write(f"{area_id}\t\n")


def export_all(tiff_manager):
    """Export all known areas that have annotations. Returns list of exported area_ids."""
    exported = []
    empty = []

    for area_id in tiff_manager.get_area_ids():
        result = export_area(area_id, tiff_manager)
        if result:
            exported.append(area_id)
        else:
            empty.append(area_id)

    _write_empty_list(empty, tiff_manager, "Export All")
    return exported


def export_complete(tiff_manager):
    """Export areas marked as complete that have annotations. Returns list of exported area_ids."""
    exported = []
    empty = []
    state = annotation_store.load_state()
    complete_map = state.get("complete", {})

    for area_id in tiff_manager.get_area_ids():
        if not complete_map.get(area_id, False):
            continue
        result = export_area(area_id, tiff_manager)
        if result:
            exported.append(area_id)
        else:
            empty.append(area_id)

    _write_empty_list(empty, tiff_manager, "Export Complete")
    return exported
