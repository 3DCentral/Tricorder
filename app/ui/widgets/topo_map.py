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
    DEFAULT_CONTOUR_LEVELS = 10  # Reduced from 15 for better performance
    DEFAULT_OUTLIER_THRESHOLD = 3.0
    SAMPLE_SIZE = 500
    MOVEMENT_THRESHOLD = 15  # Increased from 5 - regenerate less often
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
        self.image.fill((0, 0, 0))  # Black background (LCARS style)
        
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
            
            # Increase PIL's decompression bomb limit for large DEMs
            # Default is 178,956,970 pixels, we'll increase to 500M for USGS DEMs
            Image.MAX_IMAGE_PIXELS = 500000000
            
            # Open with PIL
            img = Image.open(file_path)
            
            # Get image dimensions before loading
            width, height = img.size
            print("DEM dimensions: {}x{} pixels ({:.1f} megapixels)".format(
                width, height, (width * height) / 1000000))
            
            # Check if image is too large - if so, downsample
            max_size = 8000  # Maximum dimension we'll load
            if width > max_size or height > max_size:
                print("WARNING: DEM is very large. Downsampling for performance...")
                scale = min(max_size / width, max_size / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                # Downsample the image
                img = img.resize((new_width, new_height), Image.BILINEAR)
                print("Downsampled to: {}x{} pixels".format(new_width, new_height))
            
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
            
            # Center the view on the middle of the DEM
            # Camera position is negative of the center point (viewport coordinates)
            self.cam_x = -self.dem_width / 2
            self.cam_y = -self.dem_height / 2
            
            # Start zoomed in for better detail (but not too much)
            # Zoom of 1.5 = good balance of overview and detail
            self.zoom = 1.5
            
            # Invalidate cache
            self.cached_surf = None
            
            print("Successfully loaded DEM: {}x{} elevation data".format(
                self.dem_width, self.dem_height))
            print("Elevation range: {:.1f} to {:.1f}".format(
                np.min(self.dem_data), np.max(self.dem_data)))
            print("Memory usage: ~{:.1f} MB".format(
                self.dem_data.nbytes / 1024 / 1024))
            print("Starting view: centered at ({:.0f}, {:.0f}), zoom {:.1f}x".format(
                self.dem_width / 2, self.dem_height / 2, self.zoom))
            
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
        
        # Create surface for rendering
        surf = pygame.Surface((x_end - x_start, y_end - y_start), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 255))  # Start with black background
        
        # STEP 1: Draw elevation-based color gradient FIRST (underneath contours)
        # Normalize elevation data to 0-1 range for this patch
        patch_min = np.min(patch)
        patch_max = np.max(patch)
        patch_range = patch_max - patch_min
        
        if patch_range > 0:
            # PERFORMANCE: Downsample elevation data for coloring
            # We don't need full resolution for the color gradient
            # Downsample to roughly screen resolution
            target_size = 200  # pixels - good balance of quality and speed
            height, width = patch.shape
            
            if height > target_size or width > target_size:
                # Calculate downsample factor
                downsample = max(height // target_size, width // target_size, 1)
                # Downsample using slicing (very fast)
                patch_small = patch[::downsample, ::downsample]
            else:
                patch_small = patch
            
            # Normalize to 0-1 (VECTORIZED - very fast!)
            normalized = (patch_small - patch_min) / patch_range
            
            # Create color gradient using VECTORIZED operations (100x faster than loops!)
            height_small, width_small = normalized.shape
            
            # Pre-allocate RGB array
            color_array = np.zeros((height_small, width_small, 3), dtype=np.uint8)
            
            # Lower half: black to dark blue (VECTORIZED)
            lower_mask = normalized < 0.5
            intensity_lower = normalized[lower_mask] * 2
            color_array[lower_mask, 2] = (intensity_lower * 128).astype(np.uint8)  # Blue channel
            
            # Upper half: blue to light blue/white (VECTORIZED)
            upper_mask = normalized >= 0.5
            intensity_upper = (normalized[upper_mask] - 0.5) * 2
            color_array[upper_mask, 0] = (intensity_upper * 200).astype(np.uint8)  # Red channel
            color_array[upper_mask, 1] = (intensity_upper * 220).astype(np.uint8)  # Green channel
            color_array[upper_mask, 2] = (128 + intensity_upper * 127).astype(np.uint8)  # Blue channel
            
            # Convert to pygame surface (fast!)
            elevation_surface = pygame.surfarray.make_surface(np.transpose(color_array, (1, 0, 2)))
            
            # Scale up to full size if we downsampled
            if height > target_size or width > target_size:
                elevation_surface = pygame.transform.smoothscale(elevation_surface, (width, height))
            
            # Blit to main surface
            surf.blit(elevation_surface, (0, 0))
        
        # STEP 2: Generate and draw contours ON TOP of elevation colors
        try:
            fig, ax = plt.subplots()
            contours = ax.contour(patch, levels=self.DEFAULT_CONTOUR_LEVELS)
            plt.close(fig)
            
            # Get contour paths - compatible with older matplotlib versions
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
            return surf, x_start - visible_x_start, y_start - visible_y_start, {}
        
        adaptive_threshold = self._analyze_contour_segments_fast(all_paths)
        
        total_segments = 0
        filtered_segments = 0
        
        # Create a separate surface for contours with transparency
        contour_surf = pygame.Surface((x_end - x_start, y_end - y_start), pygame.SRCALPHA)
        contour_surf.fill((0, 0, 0, 0))  # Fully transparent
        
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
                        # Yellow contour lines (LCARS style) on transparent surface
                        pygame.draw.lines(contour_surf, (255, 255, 0, 255), False, segment_list, 1)
        
        # Blit contours on top of elevation colors
        surf.blit(contour_surf, (0, 0))
        
        offset_x = x_start - visible_x_start
        offset_y = y_start - visible_y_start
        
        stats = {
            'threshold': adaptive_threshold,
            'total_paths': total_segments,
            'filtered': filtered_segments,
            'elev_min': patch_min if patch_range > 0 else 0,
            'elev_max': patch_max if patch_range > 0 else 0
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
        cache_color = (153, 255, 153) if not self._needs_regeneration() else (255, 153, 153)  # Light green / light red
        
        # LCARS colors: light blue for text
        text_color = (153, 153, 255)  # Light blue (LCARS BLUE)
        
        info_lines = [
            ("Zoom: {:.2f}x | {}".format(self.zoom, cache_status), cache_color),
            ("Sensitivity: {:.2f}σ".format(self.outlier_threshold), text_color),
            ("Contours: {} ({} filtered)".format(
                self.stats.get('total_paths', 0),
                self.stats.get('filtered', 0)
            ), text_color)
        ]
        
        # Add elevation range if available
        if 'elev_min' in self.stats and 'elev_max' in self.stats:
            elev_min = self.stats['elev_min']
            elev_max = self.stats['elev_max']
            if elev_max > elev_min:
                info_lines.append(
                    ("Elevation: {:.0f} - {:.0f}m".format(elev_min, elev_max), text_color)
                )
        
        y_pos = 10
        for line_text, color in info_lines:
            text = font.render(line_text, True, color)
            bg_rect = text.get_rect(topleft=(10, y_pos))
            bg_rect.inflate_ip(10, 4)
            
            # Semi-transparent dark background (LCARS style)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
            bg_surf.set_alpha(180)
            bg_surf.fill((0, 0, 0))  # Black background
            surface.blit(bg_surf, bg_rect)
            
            surface.blit(text, (10, y_pos))
            y_pos += 25
    
    def _draw_no_data_message(self, surface):
        """Draw message when no DEM data is loaded"""
        font = pygame.font.Font("assets/swiss911.ttf", 24)
        text = font.render("NO DEM DATA LOADED", True, (255, 153, 0))  # LCARS Orange
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2))
        surface.blit(text, text_rect)
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 16)
        text2 = font_small.render("Place GeoTIFF file in assets/", True, (153, 153, 255))  # LCARS Blue
        text2_rect = text2.get_rect(center=(self.display_width // 2, self.display_height // 2 + 40))
        surface.blit(text2, text2_rect)
    
    def update(self, screen):
        """Update and render the topographical map"""
        if not self.visible:
            return
        
        # Clear surface with black background (LCARS style)
        self.image.fill((0, 0, 0))
        
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
