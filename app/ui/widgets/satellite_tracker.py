"""Satellite tracker widget for real-time orbital visualization

Displays NOAA weather satellites with ground track overlay on Earth map
"""
import os
import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
from datetime import datetime, timedelta


class LcarsSatelliteTracker(LcarsWidget):
    """
    Real-time satellite tracking widget
    
    Displays weather satellites (NOAA 21) with orbital ground track
    on an Earth map projection. Updates position in real-time.
    """
    
    def __init__(self, pos, size=(640, 480), earth_map_path=None):
        """
        Initialize satellite tracker
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
            earth_map_path: Path to Earth map image (2:1 equirectangular projection)
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))  # Black background (LCARS style)
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Satellite tracking data
        self.sat = None
        self.ts = None
        self.earth_map = None
        self.earth_map_path = earth_map_path
        
        # TLE cache configuration
        self.tle_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle'
        self.cache_file = '/tmp/noaa21_data.tle'
        self.cache_expiry_hours = 6  # Refresh TLE data every 6 hours
        self.last_tle_update = None
        
        # Display state
        self.current_lat = None
        self.current_lon = None
        self.current_alt_km = None
        self.ground_track_points = []
        self.track_minutes = 90  # Show last 90 minutes of orbit
        
        # Animation state
        self.pulse_phase = 0  # For satellite position pulse effect
        self.last_update_time = 0
        
        # Click-to-show-info feature
        self.clicked_lat = None
        self.clicked_lon = None
        
        # Load Earth map if provided
        if earth_map_path:
            self.load_earth_map(earth_map_path)
        
        # Initialize satellite tracking (lazy load)
        # Don't load TLE data until widget is first displayed
        self.initialized = False
    
    def load_earth_map(self, image_path):
        """
        Load Earth map background image
        
        Args:
            image_path: Path to Earth map (should be 2:1 equirectangular projection)
            
        Returns:
            bool: True if loaded successfully
        """
        try:
            print("Loading Earth map: {}".format(image_path))
            
            # Load and scale to widget size
            self.earth_map = pygame.image.load(image_path).convert()
            self.earth_map = pygame.transform.scale(
                self.earth_map, 
                (self.display_width, self.display_height)
            )
            
            self.earth_map_path = image_path
            
            print("Earth map loaded successfully")
            return True
            
        except Exception as e:
            print("Failed to load Earth map {}: {}".format(image_path, e))
            return False
    
    def _download_tle_data(self):
        """
        Download fresh TLE data from CelesTrak
        
        Returns:
            bool: True if download successful
        """
        try:
            import requests
            
            print("Downloading fresh TLE data for NOAA 21...")
            response = requests.get(self.tle_url, timeout=10)
            response.raise_for_status()
            
            # Verify we didn't get an HTML error page
            if "<html" in response.text.lower():
                raise ValueError("CelesTrak returned HTML instead of TLE")
            
            # Save to cache
            with open(self.cache_file, 'w') as f:
                f.write(response.text)
            
            self.last_tle_update = datetime.now()
            
            print("TLE data updated successfully")
            return True
            
        except Exception as e:
            print("TLE download failed: {}".format(e))
            return False
    
    def _load_tle_from_cache(self):
        """
        Load TLE data from cache file
        
        Returns:
            bool: True if cache exists and is valid
        """
        if not os.path.exists(self.cache_file):
            return False
        
        # Check cache age
        cache_age = datetime.now() - datetime.fromtimestamp(
            os.path.getmtime(self.cache_file)
        )
        
        if cache_age.total_seconds() > self.cache_expiry_hours * 3600:
            print("TLE cache expired (age: {:.1f} hours)".format(
                cache_age.total_seconds() / 3600))
            return False
        
        print("Using cached TLE data (age: {:.1f} hours)".format(
            cache_age.total_seconds() / 3600))
        return True
    
    def initialize_tracking(self):
        """
        Initialize satellite tracking system
        
        Loads TLE data and sets up Skyfield for orbit calculations
        
        Returns:
            bool: True if initialized successfully
        """
        try:
            from skyfield.api import load, wgs84
            
            # Try to use cache first, download if needed
            if not self._load_tle_from_cache():
                if not self._download_tle_data():
                    # Download failed, check if cache exists as fallback
                    if not os.path.exists(self.cache_file):
                        print("ERROR: No TLE data available (download failed, no cache)")
                        return False
                    print("Using old cached TLE data as fallback")
            
            # Load TLE data with Skyfield
            print("Loading TLE data with Skyfield...")
            satellites = load.tle_file(self.cache_file)
            
            if not satellites:
                print("ERROR: No satellites found in TLE file")
                return False
            
            # Use first satellite (NOAA 21)
            self.sat = satellites[0]
            self.ts = load.timescale()
            
            print("Satellite tracking initialized: {}".format(self.sat.name))
            
            self.initialized = True
            return True
            
        except ImportError as e:
            print("ERROR: Required libraries not installed: {}".format(e))
            print("Please install: pip install skyfield requests --break-system-packages")
            return False
        except Exception as e:
            print("Failed to initialize satellite tracking: {}".format(e))
            import traceback
            traceback.print_exc()
            return False
    
    def _latlon_to_screen(self, lat, lon):
        """
        Convert latitude/longitude to screen pixel coordinates
        
        Uses equirectangular projection (simple linear mapping)
        
        Args:
            lat: Latitude in degrees (-90 to 90)
            lon: Longitude in degrees (-180 to 180)
            
        Returns:
            tuple: (x, y) screen coordinates
        """
        # Map lon from -180,180 to 0,width
        x = int((lon + 180) * (self.display_width / 360))
        
        # Map lat from 90,-90 to 0,height (inverted Y axis)
        y = int((90 - lat) * (self.display_height / 180))
        
        # Clamp to screen bounds
        x = max(0, min(self.display_width - 1, x))
        y = max(0, min(self.display_height - 1, y))
        
        return x, y
    
    def _screen_to_latlon(self, x, y):
        """
        Convert screen coordinates to latitude/longitude
        
        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            
        Returns:
            tuple: (lat, lon) in degrees
        """
        # Map x from 0,width to -180,180
        lon = (x / self.display_width) * 360 - 180
        
        # Map y from 0,height to 90,-90 (inverted Y axis)
        lat = 90 - (y / self.display_height) * 180
        
        return lat, lon
    
    def update_satellite_position(self):
        """
        Update satellite position and ground track
        
        Calculates current position and historical ground track
        """
        if not self.initialized or not self.sat or not self.ts:
            return
        
        try:
            from skyfield.api import wgs84
            
            # Get current time
            now = self.ts.now()
            
            # Calculate current position
            geocentric = self.sat.at(now)
            subpoint = wgs84.subpoint(geocentric)
            
            self.current_lat = subpoint.latitude.degrees
            self.current_lon = subpoint.longitude.degrees
            self.current_alt_km = subpoint.elevation.km
            
            # Calculate ground track (last N minutes)
            self.ground_track_points = []
            
            # Sample every 2 minutes for performance
            for i in range(0, self.track_minutes + 1, 2):
                time_step = now - timedelta(minutes=i)
                geo = self.sat.at(time_step)
                sub = wgs84.subpoint(geo)
                
                screen_pos = self._latlon_to_screen(
                    sub.latitude.degrees,
                    sub.longitude.degrees
                )
                self.ground_track_points.append(screen_pos)
            
        except Exception as e:
            print("Error updating satellite position: {}".format(e))
    
    def _draw_earth_map(self, surface):
        """Draw the Earth map background"""
        if self.earth_map:
            surface.blit(self.earth_map, (0, 0))
        else:
            # Draw placeholder grid if no map available
            surface.fill((0, 0, 0))
            
            # Draw latitude lines
            for lat in range(-90, 91, 30):
                y = int((90 - lat) * (self.display_height / 180))
                pygame.draw.line(surface, (40, 40, 40), 
                               (0, y), (self.display_width, y), 1)
            
            # Draw longitude lines
            for lon in range(-180, 181, 30):
                x = int((lon + 180) * (self.display_width / 360))
                pygame.draw.line(surface, (40, 40, 40),
                               (x, 0), (x, self.display_height), 1)
    
    def _draw_ground_track(self, surface):
        """Draw the satellite's ground track (orbital path)"""
        if len(self.ground_track_points) < 2:
            return
        
        # Draw track with date line wrap-around protection
        for i in range(len(self.ground_track_points) - 1):
            p1 = self.ground_track_points[i]
            p2 = self.ground_track_points[i + 1]
            
            # Only draw if line doesn't cross the date line
            # (avoid drawing line across entire screen)
            if abs(p1[0] - p2[0]) < self.display_width / 2:
                # Fade older parts of the track
                alpha = int(255 * (1 - i / len(self.ground_track_points)))
                color = (255, 255, 0, alpha)  # Yellow with fade
                
                pygame.draw.line(surface, (255, 255, 0), p1, p2, 2)
    
    def _draw_satellite_position(self, surface):
        """Draw the satellite's current position with pulse effect"""
        if self.current_lat is None or self.current_lon is None:
            return
        
        pos = self._latlon_to_screen(self.current_lat, self.current_lon)
        
        # Pulse effect
        pulse_size = int(6 + 2 * np.sin(self.pulse_phase))
        
        # Draw satellite dot
        pygame.draw.circle(surface, (255, 0, 0), pos, pulse_size)  # Red outer
        pygame.draw.circle(surface, (255, 255, 255), pos, 2)  # White center
        
        # Update pulse animation
        self.pulse_phase += 0.1
        if self.pulse_phase > 2 * np.pi:
            self.pulse_phase = 0
    
    def _draw_info_overlay(self, surface):
        """Draw satellite information overlay"""
        if self.current_lat is None:
            return
        
        font = pygame.font.Font("assets/swiss911.ttf", 16)
        
        # LCARS colors
        text_color = (255, 255, 0)  # Yellow
        
        # Format satellite info
        info_lines = [
            "NOAA 21 Weather Satellite",
            "Lat: {:.2f}° | Lon: {:.2f}°".format(
                self.current_lat, self.current_lon),
            "Altitude: {:.0f} km".format(self.current_alt_km) if self.current_alt_km else "",
        ]
        
        # Draw info box at bottom
        y_pos = self.display_height - 70
        
        for line in info_lines:
            if line:  # Skip empty lines
                text = font.render(line, True, text_color)
                bg_rect = text.get_rect(topleft=(10, y_pos))
                bg_rect.inflate_ip(10, 4)
                
                # Semi-transparent background
                bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
                bg_surf.set_alpha(180)
                bg_surf.fill((0, 0, 0))
                surface.blit(bg_surf, bg_rect)
                
                surface.blit(text, (10, y_pos))
                y_pos += 20
    
    def _draw_no_data_message(self, surface):
        """Draw message when tracking not initialized"""
        font = pygame.font.Font("assets/swiss911.ttf", 24)
        text = font.render("SATELLITE TRACKING", True, (255, 153, 0))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2 - 40))
        surface.blit(text, text_rect)
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 16)
        text2 = font_small.render("Initializing orbital data...", True, (153, 153, 255))
        text2_rect = text2.get_rect(center=(self.display_width // 2, self.display_height // 2))
        surface.blit(text2, text2_rect)
    
    def update(self, screen):
        """Update and render the satellite tracker"""
        if not self.visible:
            return
        
        # Lazy initialization on first display
        if not self.initialized:
            self.initialize_tracking()
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        # Check if initialized successfully
        if not self.initialized:
            self._draw_no_data_message(self.image)
            screen.blit(self.image, self.rect)
            self.dirty = 0
            return
        
        # Update satellite position periodically (every 100ms)
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time > 100:
            self.update_satellite_position()
            self.last_update_time = current_time
        
        # Draw components
        self._draw_earth_map(self.image)
        self._draw_ground_track(self.image)
        self._draw_satellite_position(self.image)
        self._draw_info_overlay(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks (future: click to show satellite pass times)"""
        if not self.visible:
            return False
        
        # Handle mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                # Convert to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                # Convert to lat/lon
                lat, lon = self._screen_to_latlon(x_rel, y_rel)
                
                self.clicked_lat = lat
                self.clicked_lon = lon
                
                print("Clicked location: {:.2f}°N, {:.2f}°W".format(lat, abs(lon)))
                
                # Future: Calculate next pass time for this location
                
                return True
        
        return False
