"""
prep_training_data.py
Prepares exported annotation data for ArcGIS deep learning workflows.

For each IMAGENAME group found in the exported data, produces two shapefiles
in the output/ subfolder:

  TrainingGrid_Annotations_IMAGENAME.shp
      Grid rectangles for every tile in scope (annotated + unannotated).

  TrainingData_Annotations_IMAGENAME.shp
      Merged annotation polygons for all annotated tiles in the group.
      (Not created if the group has no annotations.)

Inputs
------
  TrainingGrid.shp                              Grid of rectangles (per dataset).
  <data_dir>/trainingPolygons/*.shp             Exported annotation shapefiles.
  <data_dir>/trainingPolygons/no_annotations.txt  TSV of unannotated areas.

Setup
-----
  Copy this script into the dataset's TrainingPrep/ folder alongside
  TrainingGrid.shp, then adjust the Configuration block below
  (TRAINING_POLYGONS_DIR, GRID_OID_FIELD, GRID_OID_OFFSET) as needed.

Usage
-----
  python prep_training_data.py
"""

import sys
import geopandas as gpd
import pandas as pd
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent

# Input: training grid shapefile (same folder as this script)
TRAINING_GRID_SHP = SCRIPT_DIR / "TrainingGrid.shp"

# Input: trainingPolygons folder (sibling of this script's parent data dir)
TRAINING_POLYGONS_DIR = SCRIPT_DIR.parent / "trainingPolygons"

# Output subfolder (created automatically)
OUTPUT_DIR = SCRIPT_DIR / "output"

# Field in TrainingGrid.shp that holds the tile OID / FID.
# Set to "FID" to use the shapefile row index (ArcGIS FID).
# Change to a column name (e.g. "OBJECTID") if the field is explicit.
GRID_OID_FIELD = "FID"

# Offset applied to OIDs parsed from filenames before matching against the grid.
# Use -1 if filenames use 1-based ArcGIS ObjectIDs but the grid index is 0-based.
# Use 0 if both are on the same base.
GRID_OID_OFFSET = -1

# Separator between IMAGENAME and OID in exported filenames.
# e.g. "MyOrtho_OID42.shp"  ->  imagename="MyOrtho", oid=42
OID_SEPARATOR = "_OID"

# ──────────────────────────────────────────────────────────────────────────────


def _load_grid():
    """Load TrainingGrid.shp, ensuring GRID_OID_FIELD is a usable column."""
    grid = gpd.read_file(TRAINING_GRID_SHP)

    if GRID_OID_FIELD not in grid.columns:
        # Fall back to the row index, which equals the shapefile FID in ArcGIS
        grid = grid.reset_index().rename(columns={"index": GRID_OID_FIELD})
        print(f"  Note: '{GRID_OID_FIELD}' not found as column — using row index (shapefile FID).")
    else:
        # Ensure it's integer for matching
        grid[GRID_OID_FIELD] = grid[GRID_OID_FIELD].astype(int)

    return grid


def _parse_area_stem(stem):
    """
    Parse an area_id stem into (imagename, oid).
    Returns (stem, None) if the separator is not found or OID is not an integer.
    """
    if OID_SEPARATOR in stem:
        imagename, oid_str = stem.rsplit(OID_SEPARATOR, 1)
        try:
            return imagename, int(oid_str)
        except ValueError:
            pass
    return stem, None


def _read_no_annotations(path):
    """
    Read no_annotations.txt (TSV with header 'imagename\\toid').
    Returns list of (imagename, oid) tuples.
    Comment lines starting with '#' and the header row are skipped.
    """
    result = []
    if not path.exists():
        print(f"  Note: {path.name} not found — no unannotated areas will be included.")
        return result

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("imagename"):
                continue  # header row
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].strip():
                try:
                    result.append((parts[0].strip(), int(parts[1].strip())))
                except ValueError:
                    print(f"  Warning: could not parse line in no_annotations.txt: {line!r}")
    return result


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Load grid ──
    print(f"Loading training grid: {TRAINING_GRID_SHP.name}")
    grid = _load_grid()
    print(f"  {len(grid)} rectangles, CRS: {grid.crs}")

    # ── Collect annotation shapefiles ──
    shp_files = sorted(TRAINING_POLYGONS_DIR.glob("*.shp"))
    print(f"\nAnnotation shapefiles in {TRAINING_POLYGONS_DIR.name}/: {len(shp_files)}")

    annotated = {}   # imagename -> list of (oid, Path)
    for shp in shp_files:
        imagename, oid = _parse_area_stem(shp.stem)
        if oid is None:
            print(f"  Skipping unrecognised filename: {shp.name}")
            continue
        annotated.setdefault(imagename, []).append((oid, shp))

    # ── Read unannotated list ──
    no_ann_path = TRAINING_POLYGONS_DIR / "no_annotations.txt"
    no_ann_list = _read_no_annotations(no_ann_path)
    print(f"Unannotated areas listed: {len(no_ann_list)}")

    empty = {}   # imagename -> list of oids
    for imagename, oid in no_ann_list:
        empty.setdefault(imagename, []).append(oid)

    # ── Process each IMAGENAME group ──
    all_imagenames = sorted(set(list(annotated) + list(empty)))
    if not all_imagenames:
        print("\nNo data found. Check TRAINING_POLYGONS_DIR and no_annotations.txt.")
        sys.exit(0)

    print(f"\nProcessing {len(all_imagenames)} IMAGENAME group(s):")
    for name in all_imagenames:
        print(f"  {name}")

    for imagename in all_imagenames:
        print(f"\n-- {imagename} --")
        ann_entries = annotated.get(imagename, [])
        empty_oids  = empty.get(imagename, [])
        all_oids    = sorted(set(
            [oid + GRID_OID_OFFSET for oid, _ in ann_entries] +
            [oid + GRID_OID_OFFSET for oid in empty_oids]
        ))

        # ── TrainingGrid_Annotations ──
        grid_subset = grid[grid[GRID_OID_FIELD].isin(all_oids)].copy()
        if grid_subset.empty:
            print(f"  WARNING: no grid rows matched OIDs {all_oids[:5]}{'...' if len(all_oids)>5 else ''}")
            print(f"           Check GRID_OID_FIELD ('{GRID_OID_FIELD}') and OID values.")
        grid_out = OUTPUT_DIR / f"TrainingGrid_Annotations_{imagename}.shp"
        grid_subset.to_file(grid_out)
        print(f"  Grid:        {len(grid_subset):4d} rectangles  ->  {grid_out.name}")

        # ── TrainingData_Annotations ──
        if ann_entries:
            gdfs = []
            for oid, shp_path in sorted(ann_entries, key=lambda x: x[0]):
                try:
                    gdf = gpd.read_file(shp_path)
                    # Reproject to grid CRS if needed
                    if gdf.crs and gdf.crs != grid.crs:
                        gdf = gdf.to_crs(grid.crs)
                    gdfs.append(gdf)
                except Exception as exc:
                    print(f"  WARNING: could not read {shp_path.name}: {exc}")

            if gdfs:
                merged = gpd.GeoDataFrame(
                    pd.concat(gdfs, ignore_index=True),
                    crs=gdfs[0].crs
                )
                # Ensure classvalue is integer (LONG), not float
                if 'classvalue' in merged.columns:
                    merged['classvalue'] = merged['classvalue'].fillna(0).astype('int32')
                data_out = OUTPUT_DIR / f"TrainingData_Annotations_{imagename}.shp"
                merged.to_file(data_out)
                print(f"  Annotations: {len(merged):4d} features     ->  {data_out.name}")
            else:
                print(f"  Annotations: no readable shapefiles — skipping TrainingData file.")
        else:
            print(f"  Annotations: none — skipping TrainingData file.")

    print("\nDone.")


if __name__ == "__main__":
    main()
