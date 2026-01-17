import pygame
import geopandas as gpd
from shapely.geometry import Point

# --- CONFIGURATION ---
INPUT_FILE = "va_geology_37_38.geojson"
# Boundaries for coordinate translation (37-38N, 77-78W)
BBOX = (-78.0, 37.0, -77.0, 38.0) 
WIDTH, HEIGHT = 800, 800

def to_screen(lon, lat):
    """Converts geographic coordinates to pixel coordinates."""
    x = (lon - BBOX[0]) / (BBOX[2] - BBOX[0]) * WIDTH
    # Invert Y because screen coordinates start at the top (0)
    y = HEIGHT - ((lat - BBOX[1]) / (BBOX[3] - BBOX[1]) * HEIGHT)
    return int(x), int(y)

def to_geo(x, y):
    """Converts pixel coordinates back to geographic coordinates for clicking."""
    lon = BBOX[0] + (x / WIDTH) * (BBOX[2] - BBOX[0])
    lat = BBOX[1] + ((HEIGHT - y) / HEIGHT) * (BBOX[3] - BBOX[1])
    return lon, lat

def run_viewer():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Geology Explorer: Richmond Region")
    
    # .convert() is crucial for performance on Raspberry Pi
    map_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
    map_surface.fill((30, 30, 30))

    # Check if file exists before trying to load
    try:
        gdf = gpd.read_file(INPUT_FILE)
    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found. Run your preprocessing script first!")
        return

    print(f"Loading {len(gdf)} features into viewer...")
    
    # Pre-render the map to a surface once
    for _, row in gdf.iterrows():
        if row.geometry.is_empty: continue
        
        # Color logic: Create a unique RGB from the MapUnit ID
        u = str(row['MapUnit'])
        color = (hash(u) % 150 + 100, hash(u+"g") % 150 + 100, hash(u+"b") % 150 + 100)
        
        # Handle Geometry
        geoms = [row.geometry] if row.geometry.geom_type == 'Polygon' else list(row.geometry.geoms)
        for poly in geoms:
            pts = [to_screen(p[0], p[1]) for p in poly.exterior.coords]
            if len(pts) > 2:
                pygame.draw.polygon(map_surface, color, pts)
                pygame.draw.lines(map_surface, (20, 20, 20), True, pts, 1)

    print("Map loaded. Click any area to identify the geology.")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            # Identify Geology on Click
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                lon, lat = to_geo(mx, my)
                click_pt = Point(lon, lat)
                
                # Check which polygon contains the click point
                match = gdf[gdf.contains(click_pt)]
                if not match.empty:
                    info = match.iloc[0]
                    print("\n--- GEOLOGIC UNIT INFO ---")
                    print(f"Name: {info.get('FullName', 'Unknown')}")
                    print(f"Age:  {info.get('Age', 'Unknown')}")
                    print(f"Unit: {info.get('MapUnit', 'N/A')}")
                else:
                    print("No unit found at this location.")

        # Display the static map surface
        screen.blit(map_surface, (0, 0))
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    run_viewer()

