"""Topographical contour map widget for DEM/GeoTIFF data"""
import pygame
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from ui.widgets.sprite import LcarsWidget
import re
import os


class LcarsTopoMap(LcarsWidget):
    """
    Interactive topographical contour map display widget
    
    Displays elevation contours from DEM (Digital Elevation Model) data.
    Supports panning and zooming with intelligent contour caching.
    
    Uses PIL/Pillow to load GeoTIFF files - no special geospatial libraries needed!
    
    NEW: Includes latitude/longitude markers based on USGS file naming convention
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
        
        # Georeferencing data (extracted from filename)
        self.lat_min = None
        self.lat_max = None
        self.lon_min = None
        self.lon_max = None
        
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
        
        # Click-to-show-elevation feature
        self.clicked_lat = None
        self.clicked_lon = None
        self.clicked_elevation = None
        self.clicked_screen_x = None
        self.clicked_screen_y = None
        
        # Zoom levels for SCAN/ANALYZE buttons
        self.zoom_levels = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
        self.current_zoom_index = 2  # Start at 1.5x (index 2)
        
        # Load DEM data if path provided
        if dem_file_path:
            self.load_dem(dem_file_path)
    
    def _parse_usgs_filename(self, filename):
        """
        Parse USGS DEM filename to extract geographic bounds
        
        Format: USGS_<resolution>_n<lat>w<lon>_<date>.tif
        Example: USGS_13_n38w078_20211220.tif
        
        USGS Convention: n38w078 means the tile covers the area from:
        - Latitude: 37°N to 38°N (the number indicates the NORTH edge)
        - Longitude: 78°W to 77°W (the number indicates the WEST edge)
        
        Returns:
            tuple: (lat_min, lat_max, lon_min, lon_max) or None if parsing fails
        """
        try:
            # Extract just the filename without path
            basename = os.path.basename(filename)
            
            # Parse using regex
            # Pattern: USGS_<resolution>_n<lat>w<lon>_<date>
            pattern = r'USGS_\d+_n(\d+)w(\d+)_\d+\.tif'
            match = re.match(pattern, basename, re.IGNORECASE)
            
            if match:
                lat_north = int(match.group(1))
                lon_west = int(match.group(2))
                
                # USGS naming convention (CORRECTED):
                # n38w078 means the NW corner is at 38°N, 78°W
                # The tile covers 1 degree south and 1 degree east from there
                lat_min = lat_north - 1  # One degree south
                lat_max = lat_north
                lon_min = -lon_west      # Western hemisphere is negative
                lon_max = -lon_west + 1  # One degree east
                
                print("Parsed geographic bounds from filename:")
                print("  Latitude:  {:.3f}°N to {:.3f}°N".format(lat_min, lat_max))
                print("  Longitude: {:.3f}°W to {:.3f}°W".format(
                    abs(lon_max), abs(lon_min)))
                
                return lat_min, lat_max, lon_min, lon_max
            else:
                print("Warning: Filename does not match USGS pattern")
                print("  Expected format: USGS_##_n##w###_########.tif")
                return None
                
        except Exception as e:
            print("Error parsing USGS filename: {}".format(e))
            return None
    
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
            
            # Parse geographic bounds from filename
            bounds = self._parse_usgs_filename(file_path)
            if bounds:
                self.lat_min, self.lat_max, self.lon_min, self.lon_max = bounds
            else:
                print("Warning: Could not determine geographic bounds")
                print("  Lat/lon labels will not be displayed")
            
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
            
            # Center the view on Powhatan, Virginia (37.5277°N, 77.4710°W)
            # Convert lat/lon to pixel coordinates
            target_coords = self._latlon_to_pixel(37.5277, -77.4710)
            if target_coords:
                pixel_x, pixel_y = target_coords
                # Camera position is negative of the center point (viewport coordinates)
                self.cam_x = -pixel_x
                self.cam_y = -pixel_y
                print("Centered view on Powhatan, VA: 37.5277°N, 77.4710°W")
            else:
                # Fallback to center of DEM if coordinate conversion fails
                self.cam_x = -self.dem_width / 2
                self.cam_y = -self.dem_height / 2
                print("Centered view on DEM center (coordinate conversion unavailable)")
            
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
    
    def _pixel_to_latlon(self, pixel_x, pixel_y):
        """
        Convert pixel coordinates to latitude/longitude
        
        Args:
            pixel_x: X coordinate in DEM pixel space (0 to dem_width)
            pixel_y: Y coordinate in DEM pixel space (0 to dem_height)
            
        Returns:
            tuple: (latitude, longitude) in decimal degrees, or None if no bounds
        """
        if self.lat_min is None or self.lon_min is None:
            return None
        
        # Calculate ratios (0.0 to 1.0)
        x_ratio = pixel_x / self.dem_width
        y_ratio = pixel_y / self.dem_height
        
        # Interpolate lat/lon
        # Note: Y axis is inverted in image coordinates (0 = top = north)
        lon = self.lon_min + x_ratio * (self.lon_max - self.lon_min)
        lat = self.lat_max - y_ratio * (self.lat_max - self.lat_min)
        
        return lat, lon
    
    def _latlon_to_pixel(self, lat, lon):
        """
        Convert latitude/longitude to pixel coordinates
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            tuple: (pixel_x, pixel_y) or None if no bounds
        """
        if self.lat_min is None or self.lon_min is None:
            return None
        
        # Calculate ratios
        x_ratio = (lon - self.lon_min) / (self.lon_max - self.lon_min)
        y_ratio = (self.lat_max - lat) / (self.lat_max - self.lat_min)
        
        # Convert to pixel coordinates
        pixel_x = x_ratio * self.dem_width
        pixel_y = y_ratio * self.dem_height
        
        return pixel_x, pixel_y
    
    def _get_elevation_at_pixel(self, pixel_x, pixel_y):
        """
        Get elevation value at a specific pixel coordinate
        
        Args:
            pixel_x: X coordinate in DEM pixel space
            pixel_y: Y coordinate in DEM pixel space
            
        Returns:
            float: Elevation in meters, or None if out of bounds
        """
        if self.dem_data is None:
            return None
        
        # Clamp to valid range
        pixel_x = int(round(pixel_x))
        pixel_y = int(round(pixel_y))
        
        if pixel_x < 0 or pixel_x >= self.dem_width:
            return None
        if pixel_y < 0 or pixel_y >= self.dem_height:
            return None
        
        # Return elevation value
        # Note: Y axis is inverted in image coordinates
        return float(self.dem_data[pixel_y, pixel_x])
    
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
        
        # Convert to pixel coordinates and center view
        coords = self._latlon_to_pixel(lat, lon)
        if coords:
            pixel_x, pixel_y = coords
            # Center camera on GPS position
            self.cam_x = -pixel_x
            self.cam_y = -pixel_y
            print("Centered map on GPS: {:.6f}°, {:.6f}°".format(lat, lon))
    
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
    
    def zoom_in_on_clicked(self):
        """
        Zoom in centered on the clicked location (SCAN button)
        
        If no location is clicked, does nothing.
        Steps through predefined zoom levels.
        """
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
            
            # Center camera on clicked location
            # Camera position is negative of the point we want centered
            # Plus half the viewport size (in world coordinates)
            self.cam_x = -pixel_x + (self.display_width / target_zoom) / 2
            self.cam_y = -pixel_y + (self.display_height / target_zoom) / 2
            
            # Set zoom
            self.zoom = target_zoom
            
            print("Zoomed IN to {:.1f}x on {:.5f}°N, {:.5f}°W".format(
                self.zoom, self.clicked_lat, abs(self.clicked_lon)))
            
            return True
        else:
            print("Already at maximum zoom ({:.1f}x)".format(self.zoom))
            return False
    
    def zoom_out_on_clicked(self):
        """
        Zoom out centered on the clicked location (ANALYZE button)
        
        If no location is clicked, does nothing.
        Steps through predefined zoom levels.
        """
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
            
            # Center camera on clicked location
            self.cam_x = -pixel_x + (self.display_width / target_zoom) / 2
            self.cam_y = -pixel_y + (self.display_height / target_zoom) / 2
            
            # Set zoom
            self.zoom = target_zoom
            
            print("Zoomed OUT to {:.1f}x on {:.5f}°N, {:.5f}°W".format(
                self.zoom, self.clicked_lat, abs(self.clicked_lon)))
            
            return True
        else:
            print("Already at minimum zoom ({:.1f}x)".format(self.zoom))
            return False
    
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
    
    def _draw_latlon_grid(self, surface):
        """
        Draw latitude/longitude grid lines and labels
        
        This draws a coordinate grid overlay on the map based on the
        geographic bounds extracted from the USGS filename.
        """
        if self.lat_min is None or self.lon_min is None:
            return  # No geographic bounds available
        
        font = pygame.font.Font("assets/swiss911.ttf", 16)
        
        # LCARS color scheme
        grid_color = (153, 153, 255, 128)  # Semi-transparent light blue
        label_color = (255, 255, 0)  # Yellow for labels
        
        # Calculate visible bounds in lat/lon
        # Get corners of visible area in pixel coordinates
        visible_x_min = max(0, int(-self.cam_x))
        visible_y_min = max(0, int(-self.cam_y))
        visible_x_max = min(self.dem_width, int(-self.cam_x + self.display_width / self.zoom))
        visible_y_max = min(self.dem_height, int(-self.cam_y + self.display_height / self.zoom))
        
        # Convert to lat/lon
        nw_coords = self._pixel_to_latlon(visible_x_min, visible_y_min)
        se_coords = self._pixel_to_latlon(visible_x_max, visible_y_max)
        
        if not nw_coords or not se_coords:
            return
        
        lat_north, lon_west = nw_coords
        lat_south, lon_east = se_coords
        
        # Determine appropriate grid spacing based on zoom level
        # More zoom = finer grid
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
            # Convert lat to pixel Y coordinate
            pixel_coords = self._latlon_to_pixel(lat, (lon_west + lon_east) / 2)
            if pixel_coords:
                pixel_x, pixel_y = pixel_coords
                # Convert to screen coordinates
                screen_y = int((pixel_y + self.cam_y) * self.zoom)
                
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
            # Convert lon to pixel X coordinate
            pixel_coords = self._latlon_to_pixel((lat_north + lat_south) / 2, lon)
            if pixel_coords:
                pixel_x, pixel_y = pixel_coords
                # Convert to screen coordinates
                screen_x = int((pixel_x + self.cam_x) * self.zoom)
                
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
    
    def _draw_elevation_marker(self, surface):
        """
        Draw elevation marker at clicked location
        
        Shows a crosshair and elevation value where the user clicked
        """
        if self.clicked_lat is None or self.clicked_lon is None:
            return
        
        # Convert clicked lat/lon to current screen coordinates
        pixel_coords = self._latlon_to_pixel(self.clicked_lat, self.clicked_lon)
        if not pixel_coords:
            return
        
        pixel_x, pixel_y = pixel_coords
        screen_x = int((pixel_x + self.cam_x) * self.zoom)
        screen_y = int((pixel_y + self.cam_y) * self.zoom)
        
        # Only draw if in visible area
        if not (0 <= screen_x < self.display_width and 0 <= screen_y < self.display_height):
            return
        
        # Draw orange crosshair (LCARS style)
        cross_size = 12
        cross_color = (255, 153, 0)  # LCARS orange
        
        # Draw crosshair
        pygame.draw.line(surface, cross_color,
                        (screen_x - cross_size, screen_y),
                        (screen_x + cross_size, screen_y), 2)
        pygame.draw.line(surface, cross_color,
                        (screen_x, screen_y - cross_size),
                        (screen_x, screen_y + cross_size), 2)
        
        # Draw circle around crosshair
        pygame.draw.circle(surface, cross_color,
                         (screen_x, screen_y), cross_size, 2)
        
        # Draw elevation label
        if self.clicked_elevation is not None:
            font = pygame.font.Font("assets/swiss911.ttf", 18)
            
            # Format elevation text
            elev_text = "Elevation: {:.1f}m ({:.0f}ft)".format(
                self.clicked_elevation,
                self.clicked_elevation * 3.28084  # Convert to feet
            )
            
            # Add coordinate text
            coord_text = "{:.5f}°N, {:.5f}°W".format(
                self.clicked_lat,
                abs(self.clicked_lon)
            )
            
            # Render text
            elev_surface = font.render(elev_text, True, (255, 153, 0))
            coord_surface = font.render(coord_text, True, (153, 153, 255))
            
            # Position label near crosshair (offset to avoid obscuring the point)
            label_x = screen_x + cross_size + 10
            label_y = screen_y - cross_size - 10
            
            # Adjust if too close to edge
            if label_x + elev_surface.get_width() > self.display_width - 10:
                label_x = screen_x - cross_size - elev_surface.get_width() - 10
            if label_y < 10:
                label_y = screen_y + cross_size + 10
            
            # Draw background box
            box_width = max(elev_surface.get_width(), coord_surface.get_width()) + 10
            box_height = elev_surface.get_height() + coord_surface.get_height() + 10
            
            bg_surf = pygame.Surface((box_width, box_height))
            bg_surf.set_alpha(200)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_x - 5, label_y - 5))
            
            # Draw border
            pygame.draw.rect(surface, (255, 153, 0),
                           (label_x - 5, label_y - 5, box_width, box_height), 2)
            
            # Draw text
            surface.blit(elev_surface, (label_x, label_y))
            surface.blit(coord_surface, (label_x, label_y + elev_surface.get_height() + 2))
    
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
        
        # Add current center coordinates if available
        if self.lat_min is not None:
            # Calculate center of visible area
            center_x = -self.cam_x + (self.display_width / self.zoom) / 2
            center_y = -self.cam_y + (self.display_height / self.zoom) / 2
            center_coords = self._pixel_to_latlon(center_x, center_y)
            
            if center_coords:
                lat, lon = center_coords
                coord_text = "Center: {:.5f}°N, {:.5f}°W".format(
                    lat, abs(lon))
                info_lines.append((coord_text, text_color))
        
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
        
        # Draw lat/lon grid AFTER contours (on top)
        self._draw_latlon_grid(self.image)
        
        # Draw elevation marker if user has clicked
        self._draw_elevation_marker(self.image)
        
        # Draw info overlay
        self._draw_info_overlay(self.image)
        
        # Draw GPS marker if enabled (future)
        if self.gps_enabled and self.gps_lat and self.gps_lon:
            # Convert GPS to pixel coordinates
            gps_pixel = self._latlon_to_pixel(self.gps_lat, self.gps_lon)
            if gps_pixel:
                pixel_x, pixel_y = gps_pixel
                # Convert to screen coordinates
                screen_x = int((pixel_x + self.cam_x) * self.zoom)
                screen_y = int((pixel_y + self.cam_y) * self.zoom)
                
                # Draw GPS crosshair if in visible area
                if 0 <= screen_x < self.display_width and 0 <= screen_y < self.display_height:
                    # Draw red crosshair
                    cross_size = 15
                    pygame.draw.line(self.image, (255, 0, 0),
                                   (screen_x - cross_size, screen_y),
                                   (screen_x + cross_size, screen_y), 3)
                    pygame.draw.line(self.image, (255, 0, 0),
                                   (screen_x, screen_y - cross_size),
                                   (screen_x, screen_y + cross_size), 3)
                    
                    # Draw circle around crosshair
                    pygame.draw.circle(self.image, (255, 0, 0),
                                     (screen_x, screen_y), cross_size, 2)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks to show elevation at clicked location"""
        if not self.visible:
            return False
        
        # Handle mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
            if self.rect.collidepoint(event.pos):
                # Convert screen coordinates to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                # Convert to DEM pixel coordinates
                pixel_x = (x_rel / self.zoom) - self.cam_x
                pixel_y = (y_rel / self.zoom) - self.cam_y
                
                # Get lat/lon at this location
                coords = self._pixel_to_latlon(pixel_x, pixel_y)
                if coords:
                    lat, lon = coords
                    
                    # Get elevation at this pixel
                    elevation = self._get_elevation_at_pixel(pixel_x, pixel_y)
                    
                    # Store for rendering
                    self.clicked_lat = lat
                    self.clicked_lon = lon
                    self.clicked_elevation = elevation
                    self.clicked_screen_x = x_rel
                    self.clicked_screen_y = y_rel
                    
                    # Print to console
                    if elevation is not None:
                        print("Clicked location: {:.5f}°N, {:.5f}°W".format(lat, abs(lon)))
                        print("  Elevation: {:.1f}m ({:.0f}ft)".format(
                            elevation, elevation * 3.28084))
                    else:
                        print("Clicked location: {:.5f}°N, {:.5f}°W (no elevation data)".format(
                            lat, abs(lon)))
                    
                    return True
        
        return False
