"""Geological map widget for displaying rock formations from GeoJSON data"""
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
    
    Uses geopandas for efficient geospatial queries and rendering.
    """
    
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
        
        # Camera/view state
        self.cam_x = 0
        self.cam_y = 0
        self.zoom = 1.0
        
        # View bounds in lat/lon (what the camera is currently looking at)
        self.view_min_lon = self.lon_min
        self.view_max_lon = self.lon_max
        self.view_min_lat = self.lat_min
        self.view_max_lat = self.lat_max
        
        # Color cache for geological units
        self.unit_colors = {}
        
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
        self.cache_view_bounds = None
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
            
            # Initialize view to full data extent
            self.view_min_lon = self.lon_min
            self.view_max_lon = self.lon_max
            self.view_min_lat = self.lat_min
            self.view_max_lat = self.lat_max
            
            # Update view to center on Powhatan, VA (37.5277°N, 77.4710°W)
            # Start at 1.0x zoom
            self.zoom = 1.0
            self.current_zoom_index = 5  # 1.0x in zoom_levels array
            self._center_on_location(37.5277, -77.4710)
            
            return True
            
        except Exception as e:
            print("Failed to load GeoJSON file {}: {}".format(file_path, e))
            import traceback
            traceback.print_exc()
            return False
    
    def _get_unit_color(self, unit):
        """
        Get consistent color for a geological unit
        
        Uses hash-based color generation for consistency
        
        Args:
            unit: Unit name/identifier
            
        Returns:
            tuple: (R, G, B) color
        """
        if unit not in self.unit_colors:
            u = str(unit)
            # Generate color based on hash (reproducible)
            r = hash(u) % 150 + 100
            g = hash(u + "g") % 150 + 100
            b = hash(u + "b") % 150 + 100
            self.unit_colors[unit] = (r, g, b)
        
        return self.unit_colors[unit]
    
    def _latlon_to_screen(self, lon, lat):
        """
        Convert lat/lon to screen pixel coordinates
        
        Maintains proper aspect ratio to prevent squishing.
        
        Args:
            lon: Longitude
            lat: Latitude
            
        Returns:
            tuple: (x, y) screen coordinates
        """
        # Calculate position within current view bounds
        x_ratio = (lon - self.view_min_lon) / (self.view_max_lon - self.view_min_lon)
        y_ratio = (lat - self.view_min_lat) / (self.view_max_lat - self.view_min_lat)
        
        # Convert to screen coordinates (Y is inverted)
        x = int(x_ratio * self.display_width)
        y = int(self.display_height - (y_ratio * self.display_height))
        
        return x, y
    
    def _screen_to_latlon(self, x, y):
        """
        Convert screen pixel coordinates to lat/lon
        
        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            
        Returns:
            tuple: (lon, lat)
        """
        # Calculate ratio within screen
        x_ratio = x / self.display_width
        y_ratio = (self.display_height - y) / self.display_height
        
        # Convert to lat/lon
        lon = self.view_min_lon + x_ratio * (self.view_max_lon - self.view_min_lon)
        lat = self.view_min_lat + y_ratio * (self.view_max_lat - self.view_min_lat)
        
        return lon, lat
    
    def _center_on_location(self, lat, lon):
        """
        Center view on a specific lat/lon location
        
        Maintains proper aspect ratio based on screen dimensions.
        Matches topographical map's zoom behavior.
        
        Args:
            lat: Latitude
            lon: Longitude
        """
        # Calculate the full data extent
        full_lon_span = self.lon_max - self.lon_min
        full_lat_span = self.lat_max - self.lat_min
        
        # CRITICAL FIX: To match topographical map's zoom behavior,
        # we need to define what "1.0x zoom" means.
        # 
        # For topographical map: zoom 1.0 means the DEM (4096 pixels) fits in viewport
        # For geological map: we want the same ground coverage
        #
        # The topo map downsamples to max 4096 pixels, so we use that as reference
        
        REFERENCE_PIXELS = 4096.0
        
        # At zoom 1.0, we want to show the fraction of data that would
        # fit on screen if the full extent were 4096 pixels wide/tall
        
        base_lon_span = full_lon_span * (self.display_width / REFERENCE_PIXELS)
        base_lat_span = full_lat_span * (self.display_height / REFERENCE_PIXELS)
        
        # Apply zoom factor
        lon_span = base_lon_span / self.zoom
        lat_span = base_lat_span / self.zoom
        
        # Calculate aspect ratios for final adjustment
        data_aspect = full_lon_span / full_lat_span
        screen_aspect = self.display_width / self.display_height
        
        # Maintain aspect ratio
        if data_aspect > screen_aspect:
            # Data is wider - adjust latitude span
            lat_span = lon_span / screen_aspect
        else:
            # Data is taller - adjust longitude span  
            lon_span = lat_span * screen_aspect
        
        # Center on location
        self.view_min_lon = lon - lon_span / 2
        self.view_max_lon = lon + lon_span / 2
        self.view_min_lat = lat - lat_span / 2
        self.view_max_lat = lat + lat_span / 2
    
    def get_view_center(self):
        """
        Get the current center of the view
        
        Returns:
            tuple: (lat, lon) of view center
        """
        center_lat = (self.view_min_lat + self.view_max_lat) / 2
        center_lon = (self.view_min_lon + self.view_max_lon) / 2
        return center_lat, center_lon
    
    def set_view_from_center(self, lat, lon, zoom_index):
        """
        Set the view to center on a specific location with given zoom
        
        Args:
            lat: Center latitude
            lon: Center longitude  
            zoom_index: Index into zoom_levels array
        """
        self.current_zoom_index = zoom_index
        self.zoom = self.zoom_levels[zoom_index]
        self._center_on_location(lat, lon)
    
    def _update_view_from_camera(self):
        """Update view bounds based on camera position and zoom"""
        # Calculate view span based on zoom
        lon_span = (self.lon_max - self.lon_min) / self.zoom
        lat_span = (self.lat_max - self.lat_min) / self.zoom
        
        # Calculate center from camera position
        # Camera is in pixel coordinates relative to full data bounds
        center_lon = self.lon_min + (-self.cam_x / self.display_width) * (self.lon_max - self.lon_min)
        center_lat = self.lat_min + (-self.cam_y / self.display_height) * (self.lat_max - self.lat_min)
        
        # Set view bounds
        self.view_min_lon = center_lon - lon_span / 2
        self.view_max_lon = center_lon + lon_span / 2
        self.view_min_lat = center_lat - lat_span / 2
        self.view_max_lat = center_lat + lat_span / 2
    
    def pan(self, dx, dy):
        """
        Pan the map view
        
        Args:
            dx: Horizontal pan amount (pixels)
            dy: Vertical pan amount (pixels)
        """
        # Convert pixel movement to lat/lon movement
        lon_per_pixel = (self.view_max_lon - self.view_min_lon) / self.display_width
        lat_per_pixel = (self.view_max_lat - self.view_min_lat) / self.display_height
        
        # Update view bounds
        self.view_min_lon -= dx * lon_per_pixel
        self.view_max_lon -= dx * lon_per_pixel
        self.view_min_lat += dy * lat_per_pixel  # Y is inverted
        self.view_max_lat += dy * lat_per_pixel
        
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
            self.zoom = self.zoom_levels[self.current_zoom_index]
            
            # Recenter on clicked location
            self._center_on_location(self.clicked_lat, self.clicked_lon)
            
            # Invalidate cache
            self.cached_surface = None
            
            print("Zoomed IN to {:.1f}x on geological map".format(self.zoom))
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
            self.zoom = self.zoom_levels[self.current_zoom_index]
            
            # Don't allow zooming out past the full data extent
            # At zoom 1.0, we show the full extent, so don't go below that
            if self.zoom < 1.0:
                self.current_zoom_index += 1
                self.zoom = self.zoom_levels[self.current_zoom_index]
                print("Cannot zoom out past full data extent")
                return False
            
            # Recenter on clicked location
            self._center_on_location(self.clicked_lat, self.clicked_lon)
            
            # Invalidate cache
            self.cached_surface = None
            
            print("Zoomed OUT to {:.1f}x on geological map".format(self.zoom))
            return True
        else:
            print("Already at minimum zoom ({:.1f}x)".format(self.zoom))
            return False
    
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
        
        # Create bounding box for current view
        view_box = box(self.view_min_lon, self.view_min_lat, 
                       self.view_max_lon, self.view_max_lat)
        
        # Query spatial index for visible polygons (FAST!)
        # Compatible with older geopandas versions
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
                pts = [self._latlon_to_screen(p[0], p[1]) 
                       for p in poly.exterior.coords]
                
                # Draw filled polygon
                if len(pts) > 2:
                    pygame.draw.polygon(surface, color, pts)
                    
                    # Draw border for detail (subtle dark gray)
                    pygame.draw.lines(surface, (30, 30, 30), True, pts, 1)
    
    def _draw_unit_marker(self, surface):
        """Draw marker and info for clicked geological unit"""
        if self.clicked_lat is None or self.clicked_lon is None:
            return
        
        # Convert to screen coordinates
        screen_x, screen_y = self._latlon_to_screen(self.clicked_lon, self.clicked_lat)
        
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
            font = pygame.font.Font("assets/swiss911.ttf", 16)
            
            # Format text
            unit_text = "Unit: {}".format(self.clicked_unit)
            age_text = "Age: {}".format(self.clicked_age) if self.clicked_age else ""
            
            # Render text
            unit_surface = font.render(unit_text, True, (255, 153, 0))
            
            # Position label
            label_x = screen_x + cross_size + 10
            label_y = screen_y - cross_size - 10
            
            # Adjust if too close to edge
            if label_x + unit_surface.get_width() > self.display_width - 10:
                label_x = screen_x - cross_size - unit_surface.get_width() - 10
            if label_y < 10:
                label_y = screen_y + cross_size + 10
            
            # Calculate box size
            box_width = unit_surface.get_width() + 10
            box_height = unit_surface.get_height()
            if age_text:
                age_surface = font.render(age_text, True, (153, 153, 255))
                box_width = max(box_width, age_surface.get_width() + 10)
                box_height += age_surface.get_height() + 2
            
            # Draw background box
            bg_surf = pygame.Surface((box_width, box_height))
            bg_surf.set_alpha(200)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_x - 5, label_y - 5))
            
            # Draw border
            pygame.draw.rect(surface, (255, 153, 0),
                           (label_x - 5, label_y - 5, box_width, box_height), 2)
            
            # Draw text
            surface.blit(unit_surface, (label_x, label_y))
            if age_text:
                surface.blit(age_surface, (label_x, label_y + unit_surface.get_height() + 2))
    
    def _draw_latlon_grid(self, surface):
        """Draw latitude/longitude grid lines and labels"""
        font = pygame.font.Font("assets/swiss911.ttf", 16)
        
        # LCARS color scheme
        grid_color = (153, 153, 255, 128)  # Semi-transparent light blue
        label_color = (255, 255, 0)  # Yellow for labels
        
        # Get visible lat/lon bounds
        lat_north = max(self.view_min_lat, self.view_max_lat)
        lat_south = min(self.view_min_lat, self.view_max_lat)
        lon_west = min(self.view_min_lon, self.view_max_lon)
        lon_east = max(self.view_min_lon, self.view_max_lon)
        
        # Determine appropriate grid spacing based on zoom level
        lat_range = abs(lat_north - lat_south)
        lon_range = abs(lon_east - lon_west)
        
        # Choose grid spacing (degrees)
        if lat_range > 0.5:
            lat_spacing = 0.25  # 15 arc-minutes
            lon_spacing = 0.25
        elif lat_range > 0.2:
            lat_spacing = 0.1  # 6 arc-minutes
            lon_spacing = 0.1
        elif lat_range > 0.05:
            lat_spacing = 0.05  # 3 arc-minutes
            lon_spacing = 0.05
        else:
            lat_spacing = 0.01  # 36 arc-seconds
            lon_spacing = 0.01
        
        # Draw latitude lines (horizontal)
        lat = np.ceil(lat_south / lat_spacing) * lat_spacing
        while lat <= lat_north:
            # Convert lat to screen Y coordinate
            screen_x, screen_y = self._latlon_to_screen((lon_west + lon_east) / 2, lat)
            
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
            # Convert lon to screen X coordinate
            screen_x, screen_y = self._latlon_to_screen(lon, (lat_north + lat_south) / 2)
            
            if 0 <= screen_x < self.display_width:
                # Draw grid line
                pygame.draw.line(surface, grid_color,
                               (screen_x, 0),
                               (screen_x, self.display_height), 1)
                
                # Draw label on bottom edge
                label = "{:.3f}°W".format(abs(lon)) if lon < 0 else "{:.3f}°E".format(lon)
                text = font.render(label, True, label_color)
                
                # Background for text
                bg_rect = text.get_rect(topleft=(screen_x + 3, self.display_height - 25))
                bg_surf = pygame.Surface((bg_rect.width + 6, bg_rect.height + 4))
                bg_surf.set_alpha(180)
                bg_surf.fill((0, 0, 0))
                surface.blit(bg_surf, (screen_x + 1, self.display_height - 27))
                surface.blit(text, (screen_x + 3, self.display_height - 25))
            
            lon += lon_spacing
    
    def _draw_scale_ruler(self, surface):
        """Draw a scale ruler at the bottom of the map showing distance"""
        # Calculate meters per degree at center latitude
        center_lat = (self.view_min_lat + self.view_max_lat) / 2
        
        # Approximate meters per degree at this latitude
        meters_per_degree_lon = 111320 * np.cos(np.radians(center_lat))
        
        # Calculate meters per screen pixel
        lon_range = self.view_max_lon - self.view_min_lon
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
        """Draw information overlay with map stats"""
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
    
    def update(self, screen):
        """Update and render the geological map"""
        if not self.visible:
            return
        
        # Clear surface with black background (LCARS style)
        self.image.fill((0, 0, 0))
        
        # Check if we need to regenerate the cached surface
        current_bounds = (self.view_min_lon, self.view_min_lat, 
                         self.view_max_lon, self.view_max_lat)
        
        needs_regeneration = (
            self.cached_surface is None or
            self.cache_view_bounds != current_bounds or
            self.cache_zoom != self.zoom
        )
        
        if needs_regeneration and self.gdf is not None:
            # Generate new cached surface
            self.cached_surface = pygame.Surface((self.display_width, self.display_height))
            self.cached_surface.fill((0, 0, 0))
            self._draw_geological_units(self.cached_surface)
            self._draw_latlon_grid(self.cached_surface)  # Add lat/lon grid to cache
            
            # Update cache metadata
            self.cache_view_bounds = current_bounds
            self.cache_zoom = self.zoom
        
        # Blit cached surface if available
        if self.cached_surface is not None:
            self.image.blit(self.cached_surface, (0, 0))
        else:
            # No data loaded - draw message
            self._draw_geological_units(self.image)
        
        # Draw overlays (not cached - always on top)
        self._draw_scale_ruler(self.image)  # Scale ruler
        self._draw_unit_marker(self.image)  # Unit marker
        self._draw_info_overlay(self.image)  # Info overlay
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks to identify geological units"""
        if not self.visible:
            return False
        
        # Handle mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
            if self.rect.collidepoint(event.pos):
                # Convert screen coordinates to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                # Convert to lat/lon
                lon, lat = self._screen_to_latlon(x_rel, y_rel)
                
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
                        
                        print("Clicked geological unit:")
                        print("  Location: {:.5f}°N, {:.5f}°W".format(lat, abs(lon)))
                        print("  Unit: {}".format(unit))
                        print("  Age: {}".format(age))
                    else:
                        self.clicked_unit = "No unit at location"
                        self.clicked_age = None
                        print("Clicked location: {:.5f}°N, {:.5f}°W (no geological unit)".format(
                            lat, abs(lon)))
                
                return True
        
        return False
