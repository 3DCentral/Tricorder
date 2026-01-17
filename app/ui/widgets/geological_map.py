"""Geological map widget for displaying rock formations from GeoJSON data"""
import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget

# Import geopandas only when needed (lazy import to avoid startup delay)
try:
    import geopandas as gpd
    from shapely.geometry import Point, box
    GEOPANDAS_AVAILABLE = True
except ImportError:
    print("Warning: geopandas not available - geological map will not work")
    GEOPANDAS_AVAILABLE = False


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
        
        # Load GeoJSON data if path provided
        if geojson_file and GEOPANDAS_AVAILABLE:
            self.load_geojson(geojson_file)
    
    def load_geojson(self, file_path):
        """
        Load geological data from GeoJSON file
        
        Args:
            file_path: Path to GeoJSON file
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        if not GEOPANDAS_AVAILABLE:
            print("Cannot load GeoJSON: geopandas not installed")
            return False
        
        try:
            print("Loading GeoJSON geological data: {}".format(file_path))
            
            # Load GeoJSON
            self.gdf = gpd.read_file(file_path)
            
            # Build spatial index for fast queries
            print("Building spatial index...")
            self.sindex = self.gdf.sindex
            
            self.geojson_file = file_path
            
            print("Successfully loaded {} geological units".format(len(self.gdf)))
            
            # Update view to center on Powhatan, VA (37.5277°N, 77.4710°W)
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
        
        Args:
            lat: Latitude
            lon: Longitude
        """
        # Calculate current view span
        lon_span = (self.lon_max - self.lon_min) / self.zoom
        lat_span = (self.lat_max - self.lat_min) / self.zoom
        
        # Center on location
        self.view_min_lon = lon - lon_span / 2
        self.view_max_lon = lon + lon_span / 2
        self.view_min_lat = lat - lat_span / 2
        self.view_max_lat = lat + lat_span / 2
    
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
            
            # Recenter on clicked location
            self._center_on_location(self.clicked_lat, self.clicked_lon)
            
            print("Zoomed OUT to {:.1f}x on geological map".format(self.zoom))
            return True
        else:
            print("Already at minimum zoom ({:.1f}x)".format(self.zoom))
            return False
    
    def _draw_geological_units(self, surface):
        """Draw geological units visible in current view"""
        if self.gdf is None or not GEOPANDAS_AVAILABLE:
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
        
        # Draw geological units
        self._draw_geological_units(self.image)
        
        # Draw unit marker if clicked
        self._draw_unit_marker(self.image)
        
        # Draw info overlay
        self._draw_info_overlay(self.image)
        
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
                if self.gdf is not None and GEOPANDAS_AVAILABLE:
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
