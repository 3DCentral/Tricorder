"""Geological map widget for displaying rock formations from GeoJSON data

FIXED VERSION: Properly synchronizes with topographical map using same zoom/coordinate system
"""
import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
import geopandas as gpd
from shapely.geometry import Point, box


class LcarsGeologicalMap(LcarsWidget):
    """
    Interactive geological map display widget
    
    Displays rock formations and geological units from GeoJSON data.
    Supports panning and zooming with spatial indexing for performance.
    
    CRITICAL: Uses SAME coordinate system as topographical map for proper synchronization
    """
    
    # Geological time scale lookup table (ages in millions of years)
    # Based on International Commission on Stratigraphy (ICS) 2023
    GEOLOGICAL_AGES = {
        # Cenozoic Era
        'Holocene': (0.0117, 0, 'Quaternary'),
        'Pleistocene': (2.58, 0.0117, 'Quaternary'),
        'Pliocene': (5.333, 2.58, 'Neogene'),
        'Miocene': (23.03, 5.333, 'Neogene'),
        'Oligocene': (33.9, 23.03, 'Paleogene'),
        'Eocene': (56.0, 33.9, 'Paleogene'),
        'Paleocene': (66.0, 56.0, 'Paleogene'),
        
        # Mesozoic Era
        'Cretaceous': (145.0, 66.0, 'Mesozoic'),
        'Jurassic': (201.3, 145.0, 'Mesozoic'),
        'Triassic': (251.9, 201.3, 'Mesozoic'),
        
        # Paleozoic Era
        'Permian': (298.9, 251.9, 'Paleozoic'),
        'Carboniferous': (358.9, 298.9, 'Paleozoic'),
        'Pennsylvanian': (323.2, 298.9, 'Paleozoic'),
        'Mississippian': (358.9, 323.2, 'Paleozoic'),
        'Devonian': (419.2, 358.9, 'Paleozoic'),
        'Silurian': (443.8, 419.2, 'Paleozoic'),
        'Ordovician': (485.4, 443.8, 'Paleozoic'),
        'Cambrian': (541.0, 485.4, 'Paleozoic'),
        
        # Precambrian
        'Ediacaran': (635.0, 541.0, 'Precambrian'),
        'Cryogenian': (720.0, 635.0, 'Precambrian'),
        'Tonian': (1000.0, 720.0, 'Precambrian'),
        'Stenian': (1200.0, 1000.0, 'Precambrian'),
        'Ectasian': (1400.0, 1200.0, 'Precambrian'),
        'Calymmian': (1600.0, 1400.0, 'Precambrian'),
        'Statherian': (1800.0, 1600.0, 'Precambrian'),
        'Orosirian': (2050.0, 1800.0, 'Precambrian'),
        'Rhyacian': (2300.0, 2050.0, 'Precambrian'),
        'Siderian': (2500.0, 2300.0, 'Precambrian'),
        'Neoarchean': (2800.0, 2500.0, 'Precambrian'),
        'Mesoarchean': (3200.0, 2800.0, 'Precambrian'),
        'Paleoarchean': (3600.0, 3200.0, 'Precambrian'),
        'Eoarchean': (4000.0, 3600.0, 'Precambrian'),
        'Hadean': (4600.0, 4000.0, 'Precambrian'),
        
        # Combined periods (sometimes used in geological maps)
        'Quaternary': (2.58, 0, 'Cenozoic'),
        'Neogene': (23.03, 2.58, 'Cenozoic'),
        'Paleogene': (66.0, 23.03, 'Cenozoic'),
        'Mesozoic': (251.9, 66.0, 'Mesozoic'),
        'Paleozoic': (541.0, 251.9, 'Paleozoic'),
        'Precambrian': (4600.0, 541.0, 'Precambrian'),
        'Proterozoic': (2500.0, 541.0, 'Precambrian'),
        'Archean': (4000.0, 2500.0, 'Precambrian'),
    }
    
    def __init__(self, pos, size=(640, 480), geojson_file=None):
        """
        Initialize geological map display
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
            geojson_file: Path to GeoJSON file with geological data
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))  # Black background (LCARS style)
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Geological data
        self.gdf = None
        self.sindex = None
        self.geojson_file = geojson_file
        
        # Geographic bounds (matches topographical map for same area)
        # Default: Virginia area from USGS_13_n38w078_20211220.tif
        self.lat_min = 37.0
        self.lat_max = 38.0
        self.lon_min = -78.0
        self.lon_max = -77.0
        
        # CRITICAL FIX: Use same coordinate system as topographical map
        # Create a virtual "pixel space" that matches the DEM dimensions
        # This ensures zoom levels and coordinates are directly comparable
        self.virtual_width = 4096  # Match topographical map's reference size
        self.virtual_height = 4096
        
        # Camera/view state - MUST match topographical map exactly
        self.cam_x = 0  # Camera X in virtual pixel space
        self.cam_y = 0  # Camera Y in virtual pixel space
        self.zoom = 1.0  # Zoom level (same meaning as topo map)
        
        # Color cache for geological units
        self.unit_colors = {}
        self.unit_age_cache = {}  # Cache mapping unit name to age name
        
        # Click-to-show-info feature
        self.clicked_lat = None
        self.clicked_lon = None
        self.clicked_unit = None
        self.clicked_age = None
        
        # Zoom levels (same as topographical map)
        self.zoom_levels = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
        self.current_zoom_index = 5  # Start at 1.0x
        
        # Cached rendering for performance
        self.cached_surface = None
        self.cache_cam_x = None
        self.cache_cam_y = None
        self.cache_zoom = None
        
        # Load GeoJSON data if path provided
        if geojson_file:
            self.load_geojson(geojson_file)
    
    def load_geojson(self, file_path):
        """
        Load geological data from GeoJSON file
        
        Args:
            file_path: Path to GeoJSON file
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            print("Loading GeoJSON geological data: {}".format(file_path))
            
            # Load GeoJSON
            self.gdf = gpd.read_file(file_path)
            
            # Build spatial index for fast queries
            print("Building spatial index...")
            self.sindex = self.gdf.sindex
            
            self.geojson_file = file_path
            
            print("Successfully loaded {} geological units".format(len(self.gdf)))
            
            # Get actual data bounds from the GeoJSON
            bounds = self.gdf.total_bounds  # [minx, miny, maxx, maxy]
            data_lon_min, data_lat_min, data_lon_max, data_lat_max = bounds
            
            print("Geological data bounds: {:.3f} to {:.3f} lon, {:.3f} to {:.3f} lat".format(
                data_lon_min, data_lon_max, data_lat_min, data_lat_max))
            
            # Use the actual data bounds (should match USGS topo map: 37-38N, 77-78W)
            self.lat_min = data_lat_min
            self.lat_max = data_lat_max
            self.lon_min = data_lon_min
            self.lon_max = data_lon_max
            
            # Build age cache for color mapping
            print("Building age-based color cache...")
            self.unit_age_cache = {}
            for _, row in self.gdf.iterrows():
                unit_name = row.get('MapUnit', 'Unknown')
                age_name = row.get('Age', 'Unknown')
                if unit_name and unit_name != 'Unknown':
                    self.unit_age_cache[unit_name] = age_name
            
            print("Cached ages for {} units".format(len(self.unit_age_cache)))
            
            # CRITICAL: Set virtual pixel dimensions based on aspect ratio
            # Maintain same aspect ratio as geographic bounds
            lat_range = self.lat_max - self.lat_min
            lon_range = self.lon_max - self.lon_min
            aspect_ratio = lon_range / lat_range
            
            # Use 4096 as base (matches topo map reference)
            if aspect_ratio > 1:
                # Wider than tall
                self.virtual_width = 4096
                self.virtual_height = int(4096 / aspect_ratio)
            else:
                # Taller than wide
                self.virtual_height = 4096
                self.virtual_width = int(4096 * aspect_ratio)
            
            print("Virtual pixel space: {}x{} (aspect ratio: {:.3f})".format(
                self.virtual_width, self.virtual_height, aspect_ratio))
            
            # Initialize view to center on Powhatan, VA (37.5277°N, 77.4710°W)
            # This MUST use the same method as topographical map
            pixel_coords = self._latlon_to_pixel(37.5277, -77.4710)
            if pixel_coords:
                pixel_x, pixel_y = pixel_coords
                # Camera position is negative of the center point
                self.cam_x = -pixel_x
                self.cam_y = -pixel_y
                print("Centered view on Powhatan, VA")
            
            return True
            
        except Exception as e:
            print("Failed to load GeoJSON file {}: {}".format(file_path, e))
            import traceback
            traceback.print_exc()
            return False
    
    def _latlon_to_pixel(self, lat, lon):
        """
        Convert latitude/longitude to virtual pixel coordinates
        
        CRITICAL: This MUST match the topographical map's coordinate system
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            tuple: (pixel_x, pixel_y) in virtual pixel space
        """
        if self.lat_min is None or self.lon_min is None:
            return None
        
        # Calculate ratios within geographic bounds
        x_ratio = (lon - self.lon_min) / (self.lon_max - self.lon_min)
        y_ratio = (self.lat_max - lat) / (self.lat_max - self.lat_min)  # Y inverted
        
        # Convert to virtual pixel coordinates
        pixel_x = x_ratio * self.virtual_width
        pixel_y = y_ratio * self.virtual_height
        
        return pixel_x, pixel_y
    
    def _pixel_to_latlon(self, pixel_x, pixel_y):
        """
        Convert virtual pixel coordinates to latitude/longitude
        
        CRITICAL: This MUST match the topographical map's coordinate system
        
        Args:
            pixel_x: X coordinate in virtual pixel space
            pixel_y: Y coordinate in virtual pixel space
            
        Returns:
            tuple: (latitude, longitude) in decimal degrees
        """
        if self.lat_min is None or self.lon_min is None:
            return None
        
        # Calculate ratios (0.0 to 1.0)
        x_ratio = pixel_x / self.virtual_width
        y_ratio = pixel_y / self.virtual_height
        
        # Interpolate lat/lon (Y axis is inverted in image coordinates)
        lon = self.lon_min + x_ratio * (self.lon_max - self.lon_min)
        lat = self.lat_max - y_ratio * (self.lat_max - self.lat_min)
        
        return lat, lon
    
    def _get_unit_color(self, unit):
        """
        Get color for a geological unit based on age (pastel spectrum)
        
        Uses age-based color gradient:
        - Oldest rocks (4600 Ma): Deep purple/violet
        - Ancient (2000 Ma): Blue
        - Old (1000 Ma): Cyan
        - Middle (500 Ma): Green
        - Younger (250 Ma): Yellow
        - Recent (100 Ma): Orange
        - Youngest (0 Ma): Pink/red
        
        Args:
            unit: Unit name/identifier
            
        Returns:
            tuple: (R, G, B) color
        """
        if unit not in self.unit_colors:
            # Try to determine age from the cached clicked_age or look it up
            age_ma = None
            
            # If this is the unit we have data for, use it
            if hasattr(self, 'unit_age_cache') and unit in self.unit_age_cache:
                age_name = self.unit_age_cache[unit]
                age_ma = self._get_age_midpoint(age_name)
            
            # If we couldn't determine age, use neutral gray
            if age_ma is None:
                # Fallback to hash-based pastel for unknown ages
                u = str(unit)
                r = hash(u) % 80 + 150  # Lighter range (150-230)
                g = hash(u + "g") % 80 + 150
                b = hash(u + "b") % 80 + 150
                self.unit_colors[unit] = (r, g, b)
            else:
                # Map age to color spectrum
                self.unit_colors[unit] = self._age_to_pastel_color(age_ma)
        
        return self.unit_colors[unit]
    
    def _get_age_midpoint(self, age_name):
        """
        Get the midpoint age in Ma for a given geological age name
        
        Args:
            age_name: Name of geological age/period
            
        Returns:
            float: Midpoint age in millions of years, or None if unknown
        """
        if not age_name or age_name == 'Unknown':
            return None
        
        # Try exact match
        age_key = age_name.strip()
        if age_key in self.GEOLOGICAL_AGES:
            start_ma, end_ma, era = self.GEOLOGICAL_AGES[age_key]
            return (start_ma + end_ma) / 2
        
        # Try partial match
        for known_age in self.GEOLOGICAL_AGES.keys():
            if known_age.lower() in age_key.lower():
                start_ma, end_ma, era = self.GEOLOGICAL_AGES[known_age]
                return (start_ma + end_ma) / 2
        
        return None
    
    def _age_to_pastel_color(self, age_ma):
        """
        Convert geological age to pastel color on spectrum
        
        Color spectrum (pastel/light tones):
        - 4600+ Ma (Hadean): Deep violet (180, 140, 200)
        - 3000 Ma (Archean): Purple-blue (160, 160, 220)
        - 2000 Ma (Proterozoic): Blue (140, 180, 230)
        - 1000 Ma (Neoproterozoic): Cyan (140, 220, 220)
        - 500 Ma (Cambrian): Green (160, 220, 180)
        - 250 Ma (Triassic): Yellow-green (200, 230, 160)
        - 100 Ma (Cretaceous): Yellow-orange (240, 220, 160)
        - 50 Ma (Eocene): Orange (240, 190, 160)
        - 10 Ma (Miocene): Pink-orange (240, 170, 180)
        - 0 Ma (Present): Pink-red (230, 160, 180)
        
        Args:
            age_ma: Age in millions of years
            
        Returns:
            tuple: (R, G, B) pastel color
        """
        import colorsys
        
        # Use logarithmic scale for better color distribution
        # Map 0-4600 Ma to 0-1 using log scale
        if age_ma <= 0:
            ratio = 0.0
        elif age_ma >= 4600:
            ratio = 1.0
        else:
            # Logarithmic mapping emphasizes younger ages
            import math
            # Add 1 to avoid log(0), scale to log(4601)
            ratio = math.log10(age_ma + 1) / math.log10(4601)
        
        # Define color spectrum using HSV for smooth transitions
        # We'll go from pink/red (0°) through the spectrum back to violet (280°)
        # Reverse the ratio so oldest = violet, youngest = pink/red
        
        if ratio < 0.1:
            # 0-10 Ma: Pink-red to orange (HSV: 350° to 20°)
            hue = 350 + (ratio / 0.1) * 30
            hue = hue / 360.0
            saturation = 0.35  # Pastel
            value = 0.95  # Light
            
        elif ratio < 0.3:
            # 10-100 Ma: Orange to yellow (HSV: 20° to 50°)
            local_ratio = (ratio - 0.1) / 0.2
            hue = (20 + local_ratio * 30) / 360.0
            saturation = 0.30
            value = 0.95
            
        elif ratio < 0.5:
            # 100-500 Ma: Yellow to green (HSV: 50° to 120°)
            local_ratio = (ratio - 0.3) / 0.2
            hue = (50 + local_ratio * 70) / 360.0
            saturation = 0.30
            value = 0.90
            
        elif ratio < 0.7:
            # 500-2000 Ma: Green to cyan (HSV: 120° to 180°)
            local_ratio = (ratio - 0.5) / 0.2
            hue = (120 + local_ratio * 60) / 360.0
            saturation = 0.35
            value = 0.88
            
        elif ratio < 0.85:
            # 2000-3500 Ma: Cyan to blue (HSV: 180° to 220°)
            local_ratio = (ratio - 0.7) / 0.15
            hue = (180 + local_ratio * 40) / 360.0
            saturation = 0.38
            value = 0.88
            
        else:
            # 3500+ Ma: Blue to violet (HSV: 220° to 280°)
            local_ratio = (ratio - 0.85) / 0.15
            hue = (220 + local_ratio * 60) / 360.0
            saturation = 0.35
            value = 0.85
        
        # Convert HSV to RGB
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        
        # Convert to 0-255 range
        return (int(r * 255), int(g * 255), int(b * 255))
    
    def _format_age_detail(self, age_name):
        """
        Format geological age with specific time range
        
        Args:
            age_name: Name of geological age/period (e.g., "Oligocene")
            
        Returns:
            str: Formatted age string with time range
        """
        if not age_name or age_name == 'Unknown':
            return None
        
        # Try to find exact match first
        age_key = age_name.strip()
        if age_key in self.GEOLOGICAL_AGES:
            start_ma, end_ma, era = self.GEOLOGICAL_AGES[age_key]
            
            # Format the time range nicely
            if end_ma == 0:
                return "{} (~{:.1f} Ma to present)".format(age_key, start_ma)
            elif start_ma >= 1000:
                # For very old rocks, use Ga (billions of years)
                return "{} (~{:.1f} Ga to ~{:.1f} Ga)".format(
                    age_key, start_ma / 1000, end_ma / 1000)
            else:
                return "{} (~{:.1f} Ma to ~{:.1f} Ma)".format(
                    age_key, start_ma, end_ma)
        
        # Try partial match (e.g., "Early Oligocene" contains "Oligocene")
        for known_age in self.GEOLOGICAL_AGES.keys():
            if known_age.lower() in age_key.lower():
                start_ma, end_ma, era = self.GEOLOGICAL_AGES[known_age]
                
                if end_ma == 0:
                    return "{} (~{:.1f} Ma to present)".format(age_key, start_ma)
                elif start_ma >= 1000:
                    return "{} (~{:.1f} Ga to ~{:.1f} Ga)".format(
                        age_key, start_ma / 1000, end_ma / 1000)
                else:
                    return "{} (~{:.1f} Ma to ~{:.1f} Ma)".format(
                        age_key, start_ma, end_ma)
        
        # If no match found, return as-is
        return age_key
    
    def _pixel_to_screen(self, pixel_x, pixel_y):
        """
        Convert virtual pixel coordinates to screen coordinates
        
        CRITICAL: This MUST match the topographical map's rendering
        
        Args:
            pixel_x: X in virtual pixel space
            pixel_y: Y in virtual pixel space
            
        Returns:
            tuple: (screen_x, screen_y)
        """
        # Apply camera and zoom (same as topo map)
        screen_x = int((pixel_x + self.cam_x) * self.zoom)
        screen_y = int((pixel_y + self.cam_y) * self.zoom)
        
        return screen_x, screen_y
    
    def _screen_to_pixel(self, screen_x, screen_y):
        """
        Convert screen coordinates to virtual pixel coordinates
        
        Args:
            screen_x: Screen X coordinate
            screen_y: Screen Y coordinate
            
        Returns:
            tuple: (pixel_x, pixel_y)
        """
        # Reverse camera and zoom
        pixel_x = (screen_x / self.zoom) - self.cam_x
        pixel_y = (screen_y / self.zoom) - self.cam_y
        
        return pixel_x, pixel_y
    
    def get_view_center(self):
        """
        Get the current center of the view in lat/lon
        
        CRITICAL: Must match topographical map's method
        
        Returns:
            tuple: (lat, lon) of view center
        """
        # Calculate center pixel in screen coordinates
        center_screen_x = self.display_width / 2
        center_screen_y = self.display_height / 2
        
        # Convert to virtual pixel coordinates
        center_pixel_x, center_pixel_y = self._screen_to_pixel(center_screen_x, center_screen_y)
        
        # Convert to lat/lon
        coords = self._pixel_to_latlon(center_pixel_x, center_pixel_y)
        if coords:
            return coords
        else:
            # Fallback to data center
            return (self.lat_min + self.lat_max) / 2, (self.lon_min + self.lon_max) / 2
    
    def set_view_from_center(self, lat, lon, zoom_index):
        """
        Set the view to center on a specific location with given zoom
        
        CRITICAL: Must match topographical map's method EXACTLY
        
        Args:
            lat: Center latitude
            lon: Center longitude
            zoom_index: Index into zoom_levels array
        """
        self.current_zoom_index = zoom_index
        self.zoom = self.zoom_levels[zoom_index]
        
        # Convert lat/lon to virtual pixel coordinates
        pixel_coords = self._latlon_to_pixel(lat, lon)
        if not pixel_coords:
            return
        
        pixel_x, pixel_y = pixel_coords
        
        # Center camera on this location (same formula as topo map)
        # Camera position is negative of the point we want centered
        # Plus half the viewport size (in world coordinates)
        self.cam_x = -pixel_x + (self.display_width / self.zoom) / 2
        self.cam_y = -pixel_y + (self.display_height / self.zoom) / 2
        
        # Invalidate cache
        self.cached_surface = None
        
        print("Geological map synchronized: center ({:.5f}, {:.5f}), zoom {:.1f}x".format(
            lat, lon, self.zoom))
    
    def pan(self, dx, dy):
        """
        Pan the map view
        
        CRITICAL: Must match topographical map's method
        
        Args:
            dx: Horizontal pan amount (pixels)
            dy: Vertical pan amount (pixels)
        """
        # Same as topo map
        self.cam_x += dx / self.zoom
        self.cam_y += dy / self.zoom
        
        # Invalidate cache
        self.cached_surface = None
    
    def zoom_in_on_clicked(self):
        """Zoom in centered on the clicked location"""
        if self.clicked_lat is None or self.clicked_lon is None:
            print("No location selected - click on map first")
            return False
        
        # Move to next zoom level
        if self.current_zoom_index < len(self.zoom_levels) - 1:
            self.current_zoom_index += 1
            target_zoom = self.zoom_levels[self.current_zoom_index]
            
            # Get pixel coordinates of clicked location
            pixel_coords = self._latlon_to_pixel(self.clicked_lat, self.clicked_lon)
            if not pixel_coords:
                return False
            
            pixel_x, pixel_y = pixel_coords
            
            # Center camera on clicked location (same as topo map)
            self.cam_x = -pixel_x + (self.display_width / target_zoom) / 2
            self.cam_y = -pixel_y + (self.display_height / target_zoom) / 2
            
            # Set zoom
            self.zoom = target_zoom
            
            # Invalidate cache
            self.cached_surface = None
            
            print("Zoomed IN to {:.1f}x on {:.5f}°N, {:.5f}°W".format(
                self.zoom, self.clicked_lat, abs(self.clicked_lon)))
            
            return True
        else:
            print("Already at maximum zoom ({:.1f}x)".format(self.zoom))
            return False
    
    def zoom_out_on_clicked(self):
        """Zoom out centered on the clicked location"""
        if self.clicked_lat is None or self.clicked_lon is None:
            print("No location selected - click on map first")
            return False
        
        # Move to previous zoom level
        if self.current_zoom_index > 0:
            self.current_zoom_index -= 1
            target_zoom = self.zoom_levels[self.current_zoom_index]
            
            # Get pixel coordinates of clicked location
            pixel_coords = self._latlon_to_pixel(self.clicked_lat, self.clicked_lon)
            if not pixel_coords:
                return False
            
            pixel_x, pixel_y = pixel_coords
            
            # Center camera on clicked location (same as topo map)
            self.cam_x = -pixel_x + (self.display_width / target_zoom) / 2
            self.cam_y = -pixel_y + (self.display_height / target_zoom) / 2
            
            # Set zoom
            self.zoom = target_zoom
            
            # Invalidate cache
            self.cached_surface = None
            
            print("Zoomed OUT to {:.1f}x on {:.5f}°N, {:.5f}°W".format(
                self.zoom, self.clicked_lat, abs(self.clicked_lon)))
            
            return True
        else:
            print("Already at minimum zoom ({:.1f}x)".format(self.zoom))
            return False
    
    def _get_visible_bounds_latlon(self):
        """
        Calculate the visible geographic bounds
        
        Returns:
            tuple: (lon_min, lat_min, lon_max, lat_max)
        """
        # Get corners of screen
        top_left_pixel = self._screen_to_pixel(0, 0)
        bottom_right_pixel = self._screen_to_pixel(self.display_width, self.display_height)
        
        # Convert to lat/lon
        top_left_coords = self._pixel_to_latlon(top_left_pixel[0], top_left_pixel[1])
        bottom_right_coords = self._pixel_to_latlon(bottom_right_pixel[0], bottom_right_pixel[1])
        
        if not top_left_coords or not bottom_right_coords:
            return None
        
        lat_north, lon_west = top_left_coords
        lat_south, lon_east = bottom_right_coords
        
        # Return as (min_lon, min_lat, max_lon, max_lat)
        return (
            min(lon_west, lon_east),
            min(lat_north, lat_south),
            max(lon_west, lon_east),
            max(lat_north, lat_south)
        )
    
    def _draw_geological_units(self, surface):
        """Draw geological units visible in current view"""
        if self.gdf is None:
            # Draw "no data" message
            font = pygame.font.Font("assets/swiss911.ttf", 24)
            text = font.render("NO GEOLOGICAL DATA", True, (255, 153, 0))
            text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2))
            surface.blit(text, text_rect)
            
            font_small = pygame.font.Font("assets/swiss911.ttf", 16)
            text2 = font_small.render("Place GeoJSON in assets/", True, (153, 153, 255))
            text2_rect = text2.get_rect(center=(self.display_width // 2, self.display_height // 2 + 40))
            surface.blit(text2, text2_rect)
            return
        
        # Get visible bounds
        bounds = self._get_visible_bounds_latlon()
        if not bounds:
            return
        
        # Create bounding box for current view
        view_box = box(bounds[0], bounds[1], bounds[2], bounds[3])
        
        # Query spatial index for visible polygons (FAST!)
        visible_ids = self.sindex.intersection(view_box.bounds)
        visible_gdf = self.gdf.iloc[list(visible_ids)]
        
        if len(visible_gdf) == 0:
            return
        
        # Draw each geological unit
        for _, row in visible_gdf.iterrows():
            color = self._get_unit_color(row['MapUnit'])
            
            # Handle both single polygons and multipolygons
            if row.geometry.geom_type == 'Polygon':
                geoms = [row.geometry]
            else:
                geoms = list(row.geometry.geoms)
            
            # Draw each polygon
            for poly in geoms:
                # Convert exterior coordinates to screen space
                pts = []
                for p in poly.exterior.coords:
                    lon, lat = p[0], p[1]
                    # Convert lat/lon -> virtual pixel -> screen
                    pixel_coords = self._latlon_to_pixel(lat, lon)
                    if pixel_coords:
                        screen_coords = self._pixel_to_screen(pixel_coords[0], pixel_coords[1])
                        pts.append(screen_coords)
                
                # Draw filled polygon
                if len(pts) > 2:
                    pygame.draw.polygon(surface, color, pts)
                    
                    # Draw border for detail (subtle dark gray)
                    pygame.draw.lines(surface, (30, 30, 30), True, pts, 1)
    
    def _draw_unit_marker(self, surface):
        """Draw marker and info for clicked geological unit"""
        if self.clicked_lat is None or self.clicked_lon is None:
            return
        
        # Convert clicked lat/lon to screen coordinates
        pixel_coords = self._latlon_to_pixel(self.clicked_lat, self.clicked_lon)
        if not pixel_coords:
            return
        
        screen_x, screen_y = self._pixel_to_screen(pixel_coords[0], pixel_coords[1])
        
        # Only draw if in visible area
        if not (0 <= screen_x < self.display_width and 0 <= screen_y < self.display_height):
            return
        
        # Draw orange crosshair (LCARS style)
        cross_size = 12
        cross_color = (255, 153, 0)
        
        pygame.draw.line(surface, cross_color,
                        (screen_x - cross_size, screen_y),
                        (screen_x + cross_size, screen_y), 2)
        pygame.draw.line(surface, cross_color,
                        (screen_x, screen_y - cross_size),
                        (screen_x, screen_y + cross_size), 2)
        pygame.draw.circle(surface, cross_color, (screen_x, screen_y), cross_size, 2)
        
        # Draw info label if we have unit data
        if self.clicked_unit:
            font = pygame.font.Font("assets/swiss911.ttf", 14)  # Slightly smaller for more text
            
            # Format unit text (may be multi-line if very long)
            unit_text = "Unit: {}".format(self.clicked_unit)
            
            # Format age with detailed time range
            age_detail = self._format_age_detail(self.clicked_age)
            
            # Render text surfaces
            unit_surface = font.render(unit_text, True, (255, 153, 0))
            
            # Calculate text surfaces for age (may need to wrap if too long)
            age_surfaces = []
            if age_detail:
                # Check if age text is too long (>50 chars, needs wrapping)
                if len(age_detail) > 50:
                    # Split at parenthesis for cleaner wrapping
                    parts = age_detail.split('(')
                    age_surfaces.append(font.render("Age: " + parts[0].strip(), True, (153, 153, 255)))
                    if len(parts) > 1:
                        age_surfaces.append(font.render("  (" + parts[1], True, (153, 153, 255)))
                else:
                    age_surfaces.append(font.render("Age: " + age_detail, True, (153, 153, 255)))
            
            # Position label
            label_x = screen_x + cross_size + 10
            label_y = screen_y - cross_size - 10
            
            # Calculate total box size
            box_width = unit_surface.get_width() + 10
            box_height = unit_surface.get_height() + 2
            
            for age_surf in age_surfaces:
                box_width = max(box_width, age_surf.get_width() + 10)
                box_height += age_surf.get_height() + 2
            
            # Adjust if too close to edge
            if label_x + box_width > self.display_width - 10:
                label_x = screen_x - cross_size - box_width - 10
            if label_y < 10:
                label_y = screen_y + cross_size + 10
            
            # Draw background box
            bg_surf = pygame.Surface((box_width, box_height + 5))
            bg_surf.set_alpha(200)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_x - 5, label_y - 5))
            
            # Draw border
            pygame.draw.rect(surface, (255, 153, 0),
                           (label_x - 5, label_y - 5, box_width, box_height + 5), 2)
            
            # Draw text
            current_y = label_y
            surface.blit(unit_surface, (label_x, current_y))
            current_y += unit_surface.get_height() + 2
            
            for age_surf in age_surfaces:
                surface.blit(age_surf, (label_x, current_y))
                current_y += age_surf.get_height() + 2
    
    def _draw_latlon_grid(self, surface):
        """Draw latitude/longitude grid lines and labels"""
        font = pygame.font.Font("assets/swiss911.ttf", 16)
        
        # LCARS color scheme
        grid_color = (153, 153, 255, 128)  # Semi-transparent light blue
        label_color = (255, 255, 0)  # Yellow for labels
        
        # Get visible bounds
        bounds = self._get_visible_bounds_latlon()
        if not bounds:
            return
        
        lon_west, lat_south, lon_east, lat_north = bounds
        
        # Determine appropriate grid spacing based on visible area
        lat_range = abs(lat_north - lat_south)
        lon_range = abs(lon_east - lon_west)
        
        # Choose grid spacing (degrees)
        if lat_range > 0.5:
            lat_spacing = 0.25
            lon_spacing = 0.25
        elif lat_range > 0.2:
            lat_spacing = 0.1
            lon_spacing = 0.1
        elif lat_range > 0.05:
            lat_spacing = 0.05
            lon_spacing = 0.05
        else:
            lat_spacing = 0.01
            lon_spacing = 0.01
        
        # Draw latitude lines (horizontal)
        lat = np.ceil(lat_south / lat_spacing) * lat_spacing
        while lat <= lat_north:
            # Convert to screen coordinates
            pixel_coords = self._latlon_to_pixel(lat, (lon_west + lon_east) / 2)
            if pixel_coords:
                screen_x, screen_y = self._pixel_to_screen(pixel_coords[0], pixel_coords[1])
                
                if 0 <= screen_y < self.display_height:
                    # Draw grid line
                    pygame.draw.line(surface, grid_color, 
                                   (0, screen_y), 
                                   (self.display_width, screen_y), 1)
                    
                    # Draw label on left edge
                    label = "{:.3f}°N".format(lat) if lat >= 0 else "{:.3f}°S".format(abs(lat))
                    text = font.render(label, True, label_color)
                    
                    # Background for text
                    bg_rect = text.get_rect(topleft=(5, screen_y - 10))
                    bg_surf = pygame.Surface((bg_rect.width + 6, bg_rect.height + 4))
                    bg_surf.set_alpha(180)
                    bg_surf.fill((0, 0, 0))
                    surface.blit(bg_surf, (3, screen_y - 12))
                    surface.blit(text, (5, screen_y - 10))
            
            lat += lat_spacing
        
        # Draw longitude lines (vertical)
        lon = np.ceil(lon_west / lon_spacing) * lon_spacing
        while lon <= lon_east:
            # Convert to screen coordinates
            pixel_coords = self._latlon_to_pixel((lat_north + lat_south) / 2, lon)
            if pixel_coords:
                screen_x, screen_y = self._pixel_to_screen(pixel_coords[0], pixel_coords[1])
                
                if 0 <= screen_x < self.display_width:
                    # Draw grid line
                    pygame.draw.line(surface, grid_color,
                                   (screen_x, 0),
                                   (screen_x, self.display_height), 1)
                    
                    # Draw label on bottom edge
                    label = "{:.3f}°W".format(abs(lon)) if lon < 0 else "{:.3f}°E".format(lon)
                    text = font.render(label, True, label_color)
                    
                    # Background for text
                    bg_rect = text.get_rect(bottomleft=(screen_x + 5, self.display_height - 5))
                    bg_surf = pygame.Surface((bg_rect.width + 6, bg_rect.height + 4))
                    bg_surf.set_alpha(180)
                    bg_surf.fill((0, 0, 0))
                    surface.blit(bg_surf, (screen_x + 3, self.display_height - bg_rect.height - 7))
                    surface.blit(text, (screen_x + 5, self.display_height - bg_rect.height - 5))
            
            lon += lon_spacing
    
    def _draw_scale_ruler(self, surface):
        """Draw a scale ruler at the bottom of the map showing distance"""
        # Get visible bounds to calculate scale
        bounds = self._get_visible_bounds_latlon()
        if not bounds:
            return
        
        lon_west, lat_south, lon_east, lat_north = bounds
        
        # Calculate center latitude for accurate distance calculation
        center_lat = (lat_north + lat_south) / 2
        
        # Meters per degree at this latitude
        meters_per_degree_lon = 111320 * np.cos(np.radians(center_lat))
        
        # Calculate meters per screen pixel
        lon_range = lon_east - lon_west
        meters_per_screen_pixel = (lon_range * meters_per_degree_lon) / self.display_width
        
        # Determine appropriate ruler length and units
        target_pixels = 150
        target_meters = target_pixels * meters_per_screen_pixel
        
        # Convert to feet
        feet_per_meter = 3.28084
        target_feet = target_meters * feet_per_meter
        
        # Choose nice round numbers for ruler
        if target_feet < 100:
            ruler_values = [10, 25, 50, 100]
            unit = "ft"
        elif target_feet < 1000:
            ruler_values = [100, 250, 500, 1000]
            unit = "ft"
        elif target_feet < 5280:
            ruler_values = [1000, 2000, 5000]
            unit = "ft"
        else:
            # Use miles
            target_miles = target_feet / 5280
            if target_miles < 1:
                ruler_values = [0.25, 0.5, 1.0]
            elif target_miles < 5:
                ruler_values = [1, 2, 5]
            elif target_miles < 10:
                ruler_values = [2, 5, 10]
            elif target_miles < 25:
                ruler_values = [5, 10, 25]
            elif target_miles < 100:
                ruler_values = [10, 25, 50, 100]
            else:
                ruler_values = [25, 50, 100, 200]
            unit = "mi"
            ruler_values = [v * 5280 for v in ruler_values]
        
        # Find best ruler value
        best_value = ruler_values[0]
        for value in ruler_values:
            pixels = (value / feet_per_meter) / meters_per_screen_pixel
            if 100 <= pixels <= 250:
                best_value = value
                break
        
        # Calculate ruler pixel length
        ruler_feet = best_value
        ruler_meters = ruler_feet / feet_per_meter
        ruler_pixels = int(ruler_meters / meters_per_screen_pixel)
        
        # Draw ruler at bottom center
        ruler_y = self.display_height - 50
        ruler_x_start = (self.display_width - ruler_pixels) // 2
        ruler_x_end = ruler_x_start + ruler_pixels
        
        # Draw ruler bar (LCARS orange)
        ruler_color = (255, 153, 0)
        bar_height = 8
        
        # Main horizontal bar
        pygame.draw.rect(surface, ruler_color,
                        (ruler_x_start, ruler_y, ruler_pixels, bar_height))
        
        # End caps
        pygame.draw.line(surface, ruler_color,
                        (ruler_x_start, ruler_y - 5),
                        (ruler_x_start, ruler_y + bar_height + 5), 3)
        pygame.draw.line(surface, ruler_color,
                        (ruler_x_end, ruler_y - 5),
                        (ruler_x_end, ruler_y + bar_height + 5), 3)
        
        # Mid-point marker
        mid_x = (ruler_x_start + ruler_x_end) // 2
        pygame.draw.line(surface, ruler_color,
                        (mid_x, ruler_y - 3),
                        (mid_x, ruler_y + bar_height + 3), 2)
        
        # Label
        font = pygame.font.Font("assets/swiss911.ttf", 18)
        
        # Format label text
        if unit == "mi":
            label_value = ruler_feet / 5280
            if label_value < 1:
                label_text = "{:.2f} {}".format(label_value, unit)
            elif label_value < 10:
                label_text = "{:.1f} {}".format(label_value, unit)
            else:
                label_text = "{:.0f} {}".format(label_value, unit)
        else:
            label_text = "{:.0f} {}".format(ruler_feet, unit)
        
        text_surface = font.render(label_text, True, ruler_color)
        text_rect = text_surface.get_rect(center=(
            (ruler_x_start + ruler_x_end) // 2,
            ruler_y + bar_height + 20
        ))
        
        # Background for text
        bg_rect = text_rect.inflate(10, 4)
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surf.set_alpha(200)
        bg_surf.fill((0, 0, 0))
        surface.blit(bg_surf, bg_rect)
        
        # Draw text
        surface.blit(text_surface, text_rect)
    
    def _draw_info_overlay(self, surface):
        """Draw information overlay with map stats and age spectrum legend"""
        font = pygame.font.Font("assets/swiss911.ttf", 18)
        
        # LCARS colors
        text_color = (153, 153, 255)
        
        info_lines = [
            ("Geological Map", text_color),
            ("Zoom: {:.2f}x".format(self.zoom), text_color),
        ]
        
        # Add unit count if data loaded
        if self.gdf is not None:
            info_lines.append(
                ("{} units loaded".format(len(self.gdf)), text_color)
            )
        
        # Add current center coordinates
        center_lat, center_lon = self.get_view_center()
        coord_text = "Center: {:.5f}°N, {:.5f}°W".format(
            center_lat, abs(center_lon))
        info_lines.append((coord_text, text_color))
        
        y_pos = 10
        for line_text, color in info_lines:
            text = font.render(line_text, True, color)
            bg_rect = text.get_rect(topleft=(10, y_pos))
            bg_rect.inflate_ip(10, 4)
            
            # Semi-transparent dark background (LCARS style)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
            bg_surf.set_alpha(180)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, bg_rect)
            
            surface.blit(text, (10, y_pos))
            y_pos += 25
        
        # Draw age spectrum legend
        self._draw_age_legend(surface)
    
    def _draw_age_legend(self, surface):
        """Draw age spectrum color legend on right side of screen"""
        # Legend dimensions
        legend_width = 30
        legend_height = 200
        legend_x = self.display_width - legend_width - 15
        legend_y = 10
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 12)
        
        # Draw background
        bg_surf = pygame.Surface((legend_width + 70, legend_height + 40))
        bg_surf.set_alpha(180)
        bg_surf.fill((0, 0, 0))
        surface.blit(bg_surf, (legend_x - 10, legend_y - 5))
        
        # Draw border
        pygame.draw.rect(surface, (255, 153, 0),
                        (legend_x - 10, legend_y - 5, legend_width + 70, legend_height + 40), 2)
        
        # Title
        title_text = font_small.render("AGE", True, (255, 255, 0))
        surface.blit(title_text, (legend_x + 5, legend_y))
        
        # Draw color gradient bar
        for i in range(legend_height):
            # Map pixel position to age (logarithmic)
            ratio = i / legend_height
            
            # Convert ratio back to approximate age for color lookup
            # Using same log scale as color mapping
            import math
            age_ma = (10 ** (ratio * math.log10(4601))) - 1
            age_ma = max(0, min(4600, age_ma))
            
            # Get color for this age
            color = self._age_to_pastel_color(age_ma)
            
            # Draw horizontal line
            pygame.draw.line(surface, color,
                           (legend_x, legend_y + 20 + i),
                           (legend_x + legend_width, legend_y + 20 + i), 1)
        
        # Draw age labels at key points
        age_labels = [
            (0, "0 Ma"),
            (0.15, "50 Ma"),
            (0.35, "250 Ma"),
            (0.55, "1000 Ma"),
            (0.75, "2500 Ma"),
            (0.95, "4600 Ma"),
        ]
        
        for ratio, label in age_labels:
            y = legend_y + 20 + int(ratio * legend_height)
            
            # Draw tick mark
            pygame.draw.line(surface, (255, 255, 0),
                           (legend_x + legend_width, y),
                           (legend_x + legend_width + 5, y), 2)
            
            # Draw label
            label_text = font_small.render(label, True, (255, 255, 0))
            surface.blit(label_text, (legend_x + legend_width + 8, y - 6))
    
    def update(self, screen):
        """Update and render the geological map"""
        if not self.visible:
            return
        
        # Clear surface with black background (LCARS style)
        self.image.fill((0, 0, 0))
        
        # Check if we need to regenerate the cached surface
        needs_regeneration = (
            self.cached_surface is None or
            self.cache_cam_x != self.cam_x or
            self.cache_cam_y != self.cam_y or
            self.cache_zoom != self.zoom
        )
        
        if needs_regeneration and self.gdf is not None:
            # Generate new cached surface
            self.cached_surface = pygame.Surface((self.display_width, self.display_height))
            self.cached_surface.fill((0, 0, 0))
            self._draw_geological_units(self.cached_surface)
            self._draw_latlon_grid(self.cached_surface)
            
            # Update cache metadata
            self.cache_cam_x = self.cam_x
            self.cache_cam_y = self.cam_y
            self.cache_zoom = self.zoom
        
        # Blit cached surface if available
        if self.cached_surface is not None:
            self.image.blit(self.cached_surface, (0, 0))
        else:
            # No data loaded - draw message
            self._draw_geological_units(self.image)
        
        # Draw overlays (not cached - always on top)
        self._draw_scale_ruler(self.image)
        self._draw_unit_marker(self.image)
        self._draw_info_overlay(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks to identify geological units"""
        if not self.visible:
            return False
        
        # Handle mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                # Convert screen coordinates to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                # Convert to virtual pixel coordinates
                pixel_x, pixel_y = self._screen_to_pixel(x_rel, y_rel)
                
                # Convert to lat/lon
                coords = self._pixel_to_latlon(pixel_x, pixel_y)
                if not coords:
                    return False
                
                lat, lon = coords
                
                # Store clicked location
                self.clicked_lat = lat
                self.clicked_lon = lon
                
                # Query geological data at this point
                if self.gdf is not None:
                    point = Point(lon, lat)
                    match = self.gdf[self.gdf.contains(point)]
                    
                    if not match.empty:
                        unit = match.iloc[0].get('FullName', match.iloc[0].get('MapUnit', 'Unknown'))
                        age = match.iloc[0].get('Age', 'Unknown')
                        
                        self.clicked_unit = unit
                        self.clicked_age = age
                        
                        # Format detailed age for display
                        age_detail = self._format_age_detail(age)
                        
                        print("Clicked geological unit:")
                        print("  Location: {:.5f}°N, {:.5f}°W".format(lat, abs(lon)))
                        print("  Unit: {}".format(unit))
                        if age_detail:
                            print("  Age: {}".format(age_detail))
                        else:
                            print("  Age: {}".format(age))
                    else:
                        self.clicked_unit = "No unit at location"
                        self.clicked_age = None
                        print("Clicked location: {:.5f}°N, {:.5f}°W (no geological unit)".format(
                            lat, abs(lon)))
                
                return True
        
        return False
