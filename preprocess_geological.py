import geopandas as gpd
from shapely.geometry import box
import pyproj

# --- CONFIGURATION ---
GDB_PATH = "/home/workstation-lambda/Desktop/Working Projects/tricorder/usgs/NGMDB_GeMS_3436/ngs_surface_2025_v1/ngs_surface_2025_v1-database/ngs_surface_2025_v1.gdb"  # Path to your 2.1GB file
OUTPUT_FILE = "va_geology_37_38.geojson"

# Your target area in Lat/Lon
LAT_LON_BBOX = (-78.0, 37.0, -77.0, 38.0) 

def run_preprocess():
    print(f"Opening {GDB_PATH}...")
    
    # 1. Determine the CRS of the Geodatabase first
    # We load a single row just to grab the projection metadata
    sample = gpd.read_file(GDB_PATH, layer='MapUnitPolys', rows=1, engine='pyogrio')
    native_crs = sample.crs
    print(f"Detected Native CRS: {native_crs}")

    # 2. Transform our Lat/Lon BBOX to the Native CRS (likely EPSG:5070)
    transformer = pyproj.Transformer.from_crs("EPSG:4326", native_crs, always_xy=True)
    minx, miny = transformer.transform(LAT_LON_BBOX[0], LAT_LON_BBOX[1])
    maxx, maxy = transformer.transform(LAT_LON_BBOX[2], LAT_LON_BBOX[3])
    native_bbox = (minx, miny, maxx, maxy)
    
    print(f"Transformed BBOX: {native_bbox}")

    # 3. Load polygons using the transformed BBOX
    polys = gpd.read_file(GDB_PATH, layer='MapUnitPolys', bbox=native_bbox, engine='pyogrio')
    
    if polys.empty:
        print("Error: No data found in that bounding box. Check your coordinates!")
        return

    # 4. Convert the data to Lat/Lon (WGS84) for the viewer
    polys = polys.to_crs("EPSG:4326")
    
    # 5. Load and Join the Map Unit descriptions
    dmu = gpd.read_file(GDB_PATH, layer='DescriptionOfMapUnits', engine='pyogrio')
    merged = polys.merge(dmu[['MapUnit', 'Name', 'FullName', 'Age']], on='MapUnit', how='left')
    
    # 6. Simplify and Save
    merged['geometry'] = merged['geometry'].simplify(0.0001, preserve_topology=True)
    merged.to_file(OUTPUT_FILE, driver='GeoJSON')
    
    print(f"Success! Extracted {len(merged)} features to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_preprocess()

