"""Topographical contour map widget for DEM/GeoTIFF data"""
import pygame
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from ui.widgets.sprite import LcarsWidget


class LcarsTopoMap(LcarsWidget):
    """
    Interactive topographical contour map display widget
    
    Displays elevation contours from DEM (Digital Elevation Model) data.
    Supports panning and zooming with intelligent contour caching.
    
    Uses PIL/Pillow to load GeoTIFF files - no special geospatial libraries needed!
    """
    
    # Constants for contour generation
    DEFAULT_CONTOUR_LEVELS = 15
    DEFAULT_OUTLIER_THRESHOLD = 3.0
    SAMPLE_SIZE = 500
    MOVEMENT_THRESHOLD = 5  # Pixels of movement before regenerating
    ZOOM_THRESHOLD = 0.02   # Zoom change before regenerating
    
    def __init__(self, pos, size=(640, 480), dem_file_path=None):
        """
        Initialize topographical map display
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
            dem_file_path: Path to GeoTIFF DEM file (optional, can be loaded later)
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((240, 240, 230))  # Beige background
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # DEM data
        self.dem_data = None
        self.dem_width = 0
        self.dem_height = 0
        self.dem_file_path = dem_file_path
        
        # Camera/view state
        self.cam_x = 0
        self.cam_y = 0
        self.zoom = 1.0
        self.outlier_threshold = self.DEFAULT_OUTLIER_THRESHOLD
        
        # Cached rendering
        self.cached_surf = None
        self.cached_offset_x = 0
        self.cached_offset_y = 0
        self.last_cam_x = 0
        self.last_cam_y = 0
        self.last_zoom = 1.0
        self.last_threshold = self.DEFAULT_OUTLIER_THRESHOLD
        self.stats = {}
        
        # GPS integration (future)
        self.gps_lat = None
        self.gps_lon = None
        self.gps_enabled = False
        
        # Load DEM data if path provided
        if dem_file_path:
            self.load_dem(dem_file_path)
    
    def load_dem(self, file_path):
        """
        Load DEM data from GeoTIFF file using PIL/Pillow
        
        Args:
            file_path: Path to GeoTIFF file
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            from PIL import Image
            
            print("Loading DEM file: {}".format(file_path))
            
            # Open with PIL
            img = Image.open(file_path)
            
            # Convert to numpy array
            # GeoTIFF elevation data is typically stored as 16-bit or 32-bit integers
            self.dem_data = np.array(img)
            
            # Handle different data types
            if self.dem_data.dtype == np.uint16:
                # 16-bit unsigned integer - common for USGS DEMs
                print("Detected 16-bit unsigned integer DEM")
            elif self.dem_data.dtype == np.int16:
                # 16-bit signed integer
                print("Detected 16-bit signed integer DEM")
            elif self.dem_data.dtype == np.float32:
                # 32-bit float
                print("Detected 32-bit float DEM")
            elif self.dem_data.dtype == np.float64:
                # 64-bit float
                print("Detected 64-bit float DEM")
            else:
                print("Warning: Unusual data type: {}".format(self.dem_data.dtype))
            
            # Check if we got a valid 2D array
            if len(self.dem_data.shape) == 2:
                self.dem_height, self.dem_width = self.dem_data.shape
            elif len(self.dem_data.shape) == 3:
                # Sometimes TIFFs have multiple bands - take the first one
                print("Multi-band image detected, using first band")
                self.dem_data = self.dem_data[:, :, 0]
                self.dem_height, self.dem_width = self.dem_data.shape
            else:
                raise ValueError("Unexpected array shape: {}".format(self.dem_data.shape))
            
            # Handle nodata values (often -9999 or 0 in DEMs)
            # Replace with the median to avoid artifacts
            if self.dem_data.dtype in [np.int16, np.int32, np.float32, np.float64]:
                # Look for obvious nodata values
                nodata_mask = (self.dem_data < -1000) | (self.dem_data > 10000)
                if np.any(nodata_mask):
                    median_val = np.median(self.dem_data[~nodata_mask])
                    self.dem_data[nodata_mask] = median_val
                    print("Replaced {} nodata values with median".format(np.sum(nodata_mask)))
            
            self.dem_file_path = file_path
            
            # Center the view
            self.cam_x = 0
            self.cam_y = 0
            
            # Invalidate cache
            self.cached_surf = None
            
            print("Successfully loaded DEM: {}x{} elevation data".format(
                self.dem_width, self.dem_height))
            print("Elevation range: {:.1f} to {:.1f}".format(
                np.min(self.dem_data), np.max(self.dem_data)))
            
            return True
            
        except Exception as e:
            print("Failed to load DEM file {}: {}".format(file_path, e))
            import traceback
            traceback.print_exc()
            return False
    
    def set_gps_position(self, lat, lon):
        """
        Set GPS position for map centering (future enhancement)
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
        """
        self.gps_lat = lat
        self.gps_lon = lon
        self.gps_enabled = True
        
        # TODO: Convert lat/lon to pixel coordinates in DEM
        # This requires knowing the DEM's georeferencing info
    
    def pan(self, dx, dy):
        """
        Pan the map view
        
        Args:
            dx: Horizontal pan amount (pixels)
            dy: Vertical pan amount (pixels)
        """
        self.cam_x += dx / self.zoom
        self.cam_y += dy / self.zoom
    
    def zoom_in(self, factor=1.05):
        """Zoom in by given factor"""
        self.zoom *= factor
    
    def zoom_out(self, factor=0.95):
        """Zoom out by given factor"""
        self.zoom = max(0.1, self.zoom * factor)
    
    def adjust_sensitivity(self, delta):
        """
        Adjust contour filtering sensitivity
        
        Args:
            delta: Change in outlier threshold (standard deviations)
        """
        self.outlier_threshold += delta
        self.outlier_threshold = max(1.0, self.outlier_threshold)
        print("Contour sensitivity: {:.2f} std devs".format(self.outlier_threshold))
    
    def _calculate_segment_length(self, p1, p2):
        """Calculate Euclidean distance between two points"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return np.sqrt(dx*dx + dy*dy)
    
    def _analyze_contour_segments_fast(self, all_paths):
        """
        Fast sampling-based analysis of contour segments
        
        Samples contour segments to determine adaptive filtering threshold
        """
        all_lengths = []
        
        for path in all_paths:
            points = path.vertices
            if len(points) > 1:
                for i in range(1, len(points)):
                    length = self._calculate_segment_length(points[i-1], points[i])
                    all_lengths.append(length)
                    
                    if len(all_lengths) >= self.SAMPLE_SIZE:
                        break
            if len(all_lengths) >= self.SAMPLE_SIZE:
                break
        
        if len(all_lengths) == 0:
            return 100
        
        lengths_array = np.array(all_lengths)
        mean_length = np.mean(lengths_array)
        std_length = np.std(lengths_array)
        threshold = mean_length + (self.outlier_threshold * std_length)
        
        return threshold
    
    def _filter_contour_path_fast(self, points, max_length):
        """
        Fast filtering using numpy operations
        
        Breaks contour paths at discontinuities (long segments)
        """
        if len(points) < 2:
            return []
        
        points_array = np.array(points)
        diffs = np.diff(points_array, axis=0)
        lengths = np.sqrt(diffs[:, 0]**2 + diffs[:, 1]**2)
        breaks = np.where(lengths > max_length)[0]
        
        if len(breaks) == 0:
            return [points]
        
        segments = []
        start_idx = 0
        
        for break_idx in breaks:
            if break_idx > start_idx:
                segment = points[start_idx:break_idx+1]
                if len(segment) > 1:
                    segments.append(segment)
            start_idx = break_idx + 1
        
        if start_idx < len(points):
            segment = points[start_idx:]
            if len(segment) > 1:
                segments.append(segment)
        
        return segments
    
    def _get_visible_contours(self):
        """
        Generate contours for the currently visible area
        
        Returns:
            tuple: (surface, offset_x, offset_y, stats_dict)
        """
        if self.dem_data is None:
            return None, 0, 0, {}
        
        sw, sh = self.display_width, self.display_height
        buffer = int(max(sw, sh) / self.zoom * 0.3)
        
        # Calculate visible bounds with buffer
        x_start = max(0, int(-self.cam_x) - buffer)
        y_start = max(0, int(-self.cam_y) - buffer)
        x_end = min(self.dem_width, int(-self.cam_x + sw / self.zoom) + buffer)
        y_end = min(self.dem_height, int(-self.cam_y + sh / self.zoom) + buffer)
        
        visible_x_start = max(0, int(-self.cam_x))
        visible_y_start = max(0, int(-self.cam_y))
        
        # Extract patch of DEM data
        patch = self.dem_data[y_start:y_end, x_start:x_end]
        if patch.size == 0:
            return None, 0, 0, {}
        
        # Generate contours using matplotlib
        try:
            fig, ax = plt.subplots()
            contours = ax.contour(patch, levels=self.DEFAULT_CONTOUR_LEVELS)
            plt.close(fig)
            
            # Get contour paths - compatible with older matplotlib versions
            # In older versions, use contours.collections
            # In newer versions, use contours.get_paths()
            try:
                all_paths = contours.get_paths()
            except AttributeError:
                # Older matplotlib - extract paths from collections
                all_paths = []
                for collection in contours.collections:
                    for path in collection.get_paths():
                        all_paths.append(path)
                        
        except Exception as e:
            print("Error generating contours: {}".format(e))
            return None, 0, 0, {}
        adaptive_threshold = self._analyze_contour_segments_fast(all_paths)
        
        # Create surface for rendering
        surf = pygame.Surface((x_end - x_start, y_end - y_start), pygame.SRCALPHA)
        surf.fill((255, 255, 255, 0))
        
        total_segments = 0
        filtered_segments = 0
        
        # Draw contours with adaptive filtering
        for path in all_paths:
            points = path.vertices
            if len(points) > 1:
                total_segments += 1
                segments = self._filter_contour_path_fast(points, adaptive_threshold)
                
                if len(segments) == 0:
                    filtered_segments += 1
                
                for segment in segments:
                    if len(segment) > 1:
                        segment_list = segment.tolist() if isinstance(segment, np.ndarray) else segment
                        # Brown contour lines
                        pygame.draw.lines(surf, (80, 50, 20), False, segment_list, 1)
        
        offset_x = x_start - visible_x_start
        offset_y = y_start - visible_y_start
        
        stats = {
            'threshold': adaptive_threshold,
            'total_paths': total_segments,
            'filtered': filtered_segments
        }
        
        return surf, offset_x, offset_y, stats
    
    def _needs_regeneration(self):
        """Check if contours need to be regenerated"""
        if self.cached_surf is None:
            return True
        
        cam_moved = (abs(self.cam_x - self.last_cam_x) > self.MOVEMENT_THRESHOLD or 
                    abs(self.cam_y - self.last_cam_y) > self.MOVEMENT_THRESHOLD)
        zoom_changed = abs(self.zoom - self.last_zoom) / self.last_zoom > self.ZOOM_THRESHOLD
        threshold_changed = abs(self.outlier_threshold - self.last_threshold) > 0.01
        
        return cam_moved or zoom_changed or threshold_changed
    
    def _draw_info_overlay(self, surface):
        """Draw information overlay with map stats"""
        if not self.stats:
            return
        
        font = pygame.font.Font("assets/swiss911.ttf", 18)
        
        # Determine cache status
        cache_status = "CACHED" if not self._needs_regeneration() else "UPDATING"
        cache_color = (50, 150, 50) if not self._needs_regeneration() else (150, 50, 50)
        
        info_lines = [
            ("Zoom: {:.2f}x | {}".format(self.zoom, cache_status), cache_color),
            ("Sensitivity: {:.2f}σ".format(self.outlier_threshold), (80, 50, 20)),
            ("Contours: {} ({} filtered)".format(
                self.stats.get('total_paths', 0),
                self.stats.get('filtered', 0)
            ), (80, 50, 20))
        ]
        
        y_pos = 10
        for line_text, color in info_lines:
            text = font.render(line_text, True, color)
            bg_rect = text.get_rect(topleft=(10, y_pos))
            bg_rect.inflate_ip(10, 4)
            
            # Semi-transparent background
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
            bg_surf.set_alpha(200)
            bg_surf.fill((240, 240, 230))
            surface.blit(bg_surf, bg_rect)
            
            surface.blit(text, (10, y_pos))
            y_pos += 25
    
    def _draw_no_data_message(self, surface):
        """Draw message when no DEM data is loaded"""
        font = pygame.font.Font("assets/swiss911.ttf", 24)
        text = font.render("NO DEM DATA LOADED", True, (150, 50, 50))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2))
        surface.blit(text, text_rect)
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 16)
        text2 = font_small.render("Place GeoTIFF file in assets/", True, (100, 100, 100))
        text2_rect = text2.get_rect(center=(self.display_width // 2, self.display_height // 2 + 40))
        surface.blit(text2, text2_rect)
    
    def update(self, screen):
        """Update and render the topographical map"""
        if not self.visible:
            return
        
        # Clear surface
        self.image.fill((240, 240, 230))
        
        # Check if DEM data is loaded
        if self.dem_data is None:
            self._draw_no_data_message(self.image)
            screen.blit(self.image, self.rect)
            self.dirty = 0
            return
        
        # Check if we need to regenerate contours
        if self._needs_regeneration():
            result = self._get_visible_contours()
            if result[0]:
                self.cached_surf, self.cached_offset_x, self.cached_offset_y, self.stats = result
                self.last_cam_x = self.cam_x
                self.last_cam_y = self.cam_y
                self.last_zoom = self.zoom
                self.last_threshold = self.outlier_threshold
        
        # Render cached contour surface
        if self.cached_surf:
            scaled = pygame.transform.smoothscale(
                self.cached_surf,
                (int(self.cached_surf.get_width() * self.zoom),
                 int(self.cached_surf.get_height() * self.zoom))
            )
            self.image.blit(scaled, 
                          (int(self.cached_offset_x * self.zoom),
                           int(self.cached_offset_y * self.zoom)))
        
        # Draw info overlay
        self._draw_info_overlay(self.image)
        
        # Draw GPS marker if enabled (future)
        if self.gps_enabled and self.gps_lat and self.gps_lon:
            # TODO: Draw GPS position marker
            pass
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle events (reserved for future touch/click interactions)"""
        if not self.visible:
            return False
        
        # Future: handle clicks to place waypoints, etc.
        
        return False
