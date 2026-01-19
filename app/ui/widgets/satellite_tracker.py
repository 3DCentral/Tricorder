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
        
        # Calculate map dimensions to maintain 2:1 aspect ratio
        # Map should be 2:1, so if we have 640x480 display:
        # - Map width = 640
        # - Map height = 320 (to maintain 2:1 ratio)
        # - Top bar = 80 pixels
        # - Bottom bar = 80 pixels
        self.map_width = self.display_width
        self.map_height = self.map_width // 2  # Maintain 2:1 ratio
        
        # Calculate vertical offset to center the map
        self.map_offset_y = (self.display_height - self.map_height) // 2
        
        # Info display areas (top and bottom bars)
        self.top_bar_height = self.map_offset_y
        self.bottom_bar_height = self.display_height - self.map_height - self.map_offset_y
        
        print("Map layout: {}x{} map, {} top bar, {} bottom bar".format(
            self.map_width, self.map_height, 
            self.top_bar_height, self.bottom_bar_height))
        
        # Satellite tracking data
        self.satellites = {}  # Dict of satellite name -> satellite object
        self.satellite_info = {}  # Dict of satellite name -> current info
        self.ts = None
        self.earth_map = None
        self.earth_map_path = earth_map_path
        
        # TLE cache configuration
        self.tle_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle'
        self.cache_file = '/tmp/weather_satellites.tle'
        self.cache_expiry_hours = 6  # Refresh TLE data every 6 hours
        self.last_tle_update = None
        
        # Satellites to track (RTL-SDR demodulatable weather satellites)
        # Format: (Display Name, Frequency MHz, Modulation)
        self.satellite_list = [
            ('NOAA 20', 137.62, 'APT'),
            ('NOAA 21', 137.9125, 'APT'),
            ('METEOR-M2 3', 137.9, 'LRPT'),
            ('METEOR-M2 4', 137.9, 'LRPT'),    # Ham Radio / Voice
            ('ISS (ZARYA)', 145.800, 'FM/APRS/SSTV'),
            ('SO-50', 145.850, 'FM Voice'),
            ('AO-91', 145.960, 'FM Voice'),
            ('AO-92', 145.880, 'FM Voice'),
        ]
        
        # Selected satellite (None = show all, or satellite name)
        self.selected_satellite = None
        
        # Mini trails for overview mode (when no satellite selected)
        self.mini_trail_minutes_past = 20  # Show last 20 minutes
        self.mini_trail_minutes_future = 20  # Show next 40 minutes
        self.mini_trails = {}  # Dict of satellite name -> {'past': [...], 'future': [...]}
        
        # Display state for selected satellite
        self.current_lat = None
        self.current_lon = None
        self.current_alt_km = None
        self.current_velocity_kms = None
        self.ground_track_points = []
        self.future_track_points = []
        self.track_minutes_past = 90  # Show last 90 minutes of orbit
        self.track_minutes_future = 180  # Show next 180 minutes (2 orbits)
        
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
            
            # Load and scale to map dimensions (2:1 ratio)
            self.earth_map = pygame.image.load(image_path).convert()
            self.earth_map = pygame.transform.scale(
                self.earth_map, 
                (self.map_width, self.map_height)
            )
            
            self.earth_map_path = image_path
            
            print("Earth map loaded successfully: {}x{}".format(
                self.map_width, self.map_height))
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
            all_satellites = load.tle_file(self.cache_file)
            
            if not all_satellites:
                print("ERROR: No satellites found in TLE file")
                return False
            
            # Build dictionary of satellites by name
            sat_by_name = {sat.name: sat for sat in all_satellites}
            
            # Find our weather satellites
            self.satellites = {}
            for sat_name, freq, mod in self.satellite_list:
                # Try exact match first
                if sat_name in sat_by_name:
                    self.satellites[sat_name] = sat_by_name[sat_name]
                    print("Found satellite: {} ({} MHz {})".format(sat_name, freq, mod))
                else:
                    # Try partial match (e.g., "NOAA 15" might be "NOAA 15 [+]")
                    found = False
                    for name, sat in sat_by_name.items():
                        if sat_name in name or name in sat_name:
                            self.satellites[sat_name] = sat
                            print("Found satellite: {} as '{}' ({} MHz {})".format(
                                sat_name, name, freq, mod))
                            found = True
                            break
                    
                    if not found:
                        print("Warning: Satellite '{}' not found in TLE data".format(sat_name))
            
            if not self.satellites:
                print("ERROR: No weather satellites found in TLE data")
                return False
            
            # Initialize timescale
            self.ts = load.timescale()
            
            print("Satellite tracking initialized: {} satellites loaded".format(
                len(self.satellites)))
            
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
        Accounts for map offset (top/bottom bars)
        
        Args:
            lat: Latitude in degrees (-90 to 90)
            lon: Longitude in degrees (-180 to 180)
            
        Returns:
            tuple: (x, y) screen coordinates
        """
        # Map lon from -180,180 to 0,map_width
        x = int((lon + 180) * (self.map_width / 360))
        
        # Map lat from 90,-90 to 0,map_height (inverted Y axis)
        y = int((90 - lat) * (self.map_height / 180))
        
        # Add vertical offset for top bar
        y += self.map_offset_y
        
        # Clamp to screen bounds
        x = max(0, min(self.display_width - 1, x))
        y = max(self.map_offset_y, min(self.map_offset_y + self.map_height - 1, y))
        
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
        # Remove vertical offset
        y_map = y - self.map_offset_y
        
        # Map x from 0,map_width to -180,180
        lon = (x / self.map_width) * 360 - 180
        
        # Map y from 0,map_height to 90,-90 (inverted Y axis)
        lat = 90 - (y_map / self.map_height) * 180
        
        return lat, lon
    
    def update_satellite_positions(self):
        """
        Update all satellite positions
        
        Calculates current positions for all satellites and mini trails
        """
        if not self.initialized or not self.satellites or not self.ts:
            return
        
        try:
            from skyfield.api import wgs84
            
            # Get current time
            now = self.ts.now()
            
            # Update position for all satellites
            self.satellite_info = {}
            self.mini_trails = {}
            
            for sat_name, sat in self.satellites.items():
                # Calculate current position
                geocentric = sat.at(now)
                subpoint = wgs84.subpoint(geocentric)
                
                # Store info
                self.satellite_info[sat_name] = {
                    'lat': subpoint.latitude.degrees,
                    'lon': subpoint.longitude.degrees,
                    'alt_km': subpoint.elevation.km,
                    'velocity_kms': 7.8,  # Approximate LEO velocity
                }
                
                # Calculate mini trails for overview mode
                # (always calculate these so they're ready)
                past_trail = []
                future_trail = []
                
                # Past trail (sample every 2 minutes for smoother mini trail)
                for i in range(0, self.mini_trail_minutes_past + 1, 2):
                    time_step = now - timedelta(minutes=i)
                    geo = sat.at(time_step)
                    sub = wgs84.subpoint(geo)
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    past_trail.append(screen_pos)
                
                # Future trail (sample every 2 minutes for smoother mini trail, start at 0)
                for i in range(0, self.mini_trail_minutes_future + 1, 2):
                    time_step = now + timedelta(minutes=i)
                    geo = sat.at(time_step)
                    sub = wgs84.subpoint(geo)
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    future_trail.append(screen_pos)
                
                self.mini_trails[sat_name] = {
                    'past': past_trail,
                    'future': future_trail
                }
            
            # If a satellite is selected, calculate detailed track
            if self.selected_satellite and self.selected_satellite in self.satellites:
                sat = self.satellites[self.selected_satellite]
                info = self.satellite_info[self.selected_satellite]
                
                # Store selected satellite info
                self.current_lat = info['lat']
                self.current_lon = info['lon']
                self.current_alt_km = info['alt_km']
                self.current_velocity_kms = info['velocity_kms']
                
                # Calculate PAST ground track (full detail)
                self.ground_track_points = []
                for i in range(0, self.track_minutes_past + 1, 2):
                    time_step = now - timedelta(minutes=i)
                    geo = sat.at(time_step)
                    sub = wgs84.subpoint(geo)
                    
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    self.ground_track_points.append(screen_pos)
                
                # Calculate FUTURE ground track (full detail)
                self.future_track_points = []
                for i in range(0, self.track_minutes_future + 1, 2):  # Start at 0 instead of 2
                    time_step = now + timedelta(minutes=i)
                    geo = sat.at(time_step)
                    sub = wgs84.subpoint(geo)
                    
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    self.future_track_points.append(screen_pos)
            else:
                # No selection - clear detailed track data
                self.current_lat = None
                self.current_lon = None
                self.current_alt_km = None
                self.current_velocity_kms = None
                self.ground_track_points = []
                self.future_track_points = []
            
        except Exception as e:
            print("Error updating satellite positions: {}".format(e))
    
    def _draw_earth_map(self, surface):
        """Draw the Earth map background with proper positioning"""
        if self.earth_map:
            # Blit map at vertical offset (leaving top and bottom bars black)
            surface.blit(self.earth_map, (0, self.map_offset_y))
        else:
            # Draw placeholder grid if no map available
            # Fill entire surface with black
            surface.fill((0, 0, 0))
            
            # Draw latitude lines (only in map area)
            for lat in range(-90, 91, 30):
                y = int((90 - lat) * (self.map_height / 180)) + self.map_offset_y
                pygame.draw.line(surface, (40, 40, 40), 
                               (0, y), (self.display_width, y), 1)
            
            # Draw longitude lines (only in map area)
            for lon in range(-180, 181, 30):
                x = int((lon + 180) * (self.map_width / 360))
                pygame.draw.line(surface, (40, 40, 40),
                               (x, self.map_offset_y), 
                               (x, self.map_offset_y + self.map_height), 1)
    
    def _draw_ground_track(self, surface):
        """Draw the satellite's ground track (orbital path)"""
        if len(self.ground_track_points) < 2:
            return
        
        # Draw PAST track in yellow with date line wrap-around protection
        for i in range(len(self.ground_track_points) - 1):
            p1 = self.ground_track_points[i]
            p2 = self.ground_track_points[i + 1]
            
            # Only draw if line doesn't cross the date line
            # (avoid drawing line across entire screen)
            if abs(p1[0] - p2[0]) < self.display_width / 2:
                # Fade older parts of the track
                alpha = int(255 * (1 - i / len(self.ground_track_points)))
                color = (255, 255, 0)  # Yellow (past track)
                
                pygame.draw.line(surface, color, p1, p2, 2)
    
    def _draw_future_track(self, surface):
        """Draw the satellite's predicted future ground track"""
        if len(self.future_track_points) < 2:
            return
        
        # Draw FUTURE track in cyan with date line wrap-around protection
        for i in range(len(self.future_track_points) - 1):
            p1 = self.future_track_points[i]
            p2 = self.future_track_points[i + 1]
            
            # Only draw if line doesn't cross the date line
            if abs(p1[0] - p2[0]) < self.display_width / 2:
                # Cyan for future prediction
                color = (0, 255, 255)  # Cyan (future track)
                
                # Optional: Make it slightly dashed to distinguish from past
                pygame.draw.line(surface, color, p1, p2, 2)
    
    def _draw_mini_trails(self, surface):
        """Draw mini trails for all satellites in overview mode"""
        if not self.mini_trails:
            return
        
        for sat_name, trails in self.mini_trails.items():
            # Draw past trail (thin, yellow)
            past_points = trails['past']
            if len(past_points) > 1:
                for i in range(len(past_points) - 1):
                    p1 = past_points[i]
                    p2 = past_points[i + 1]
                    
                    # Date line wrap protection
                    if abs(p1[0] - p2[0]) < self.display_width / 2:
                        pygame.draw.line(surface, (200, 200, 0), p1, p2, 1)  # Dim yellow
            
            # Draw future trail (thin, cyan)
            future_points = trails['future']
            if len(future_points) > 1:
                for i in range(len(future_points) - 1):
                    p1 = future_points[i]
                    p2 = future_points[i + 1]
                    
                    # Date line wrap protection
                    if abs(p1[0] - p2[0]) < self.display_width / 2:
                        pygame.draw.line(surface, (0, 200, 200), p1, p2, 1)  # Dim cyan
    
    def _draw_all_satellites(self, surface):
        """Draw all satellite positions when none is selected"""
        if not self.satellite_info:
            return
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 12)
        
        for sat_name, info in self.satellite_info.items():
            pos = self._latlon_to_screen(info['lat'], info['lon'])
            
            # Draw satellite dot (smaller than selected)
            pygame.draw.circle(surface, (255, 153, 0), pos, 4)  # Orange
            pygame.draw.circle(surface, (255, 255, 255), pos, 2)  # White center
            
            # Draw label next to satellite
            label_text = font_small.render(sat_name, True, (255, 153, 0))
            label_rect = label_text.get_rect(topleft=(pos[0] + 6, pos[1] - 6))
            
            # Background for label
            bg_surf = pygame.Surface((label_rect.width + 4, label_rect.height + 2))
            bg_surf.set_alpha(180)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_rect.x - 2, label_rect.y - 1))
            
            # Draw label
            surface.blit(label_text, label_rect)
    
    def _draw_other_satellites(self, surface):
        """Draw other satellites (not selected) when one is selected"""
        if not self.satellite_info or not self.selected_satellite:
            return
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 10)
        
        for sat_name, info in self.satellite_info.items():
            # Skip the selected satellite (it's drawn separately)
            if sat_name == self.selected_satellite:
                continue
            
            pos = self._latlon_to_screen(info['lat'], info['lon'])
            
            # Draw satellite dot (dimmer, smaller)
            pygame.draw.circle(surface, (150, 100, 0), pos, 3)  # Dim orange
            pygame.draw.circle(surface, (200, 200, 200), pos, 1)  # Light gray center
            
            # Draw label next to satellite (smaller, dimmer)
            label_text = font_small.render(sat_name, True, (150, 100, 0))
            label_rect = label_text.get_rect(topleft=(pos[0] + 5, pos[1] - 5))
            
            # Background for label
            bg_surf = pygame.Surface((label_rect.width + 3, label_rect.height + 2))
            bg_surf.set_alpha(150)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_rect.x - 1, label_rect.y - 1))
            
            # Draw label
            surface.blit(label_text, label_rect)
    
    def _draw_satellite_position(self, surface):
        """Draw the selected satellite's current position with pulse effect"""
        if self.current_lat is None or self.current_lon is None:
            return
        
        pos = self._latlon_to_screen(self.current_lat, self.current_lon)
        
        # Pulse effect
        pulse_size = int(6 + 2 * np.sin(self.pulse_phase))
        
        # Draw satellite dot (larger when selected)
        pygame.draw.circle(surface, (255, 0, 0), pos, pulse_size)  # Red outer
        pygame.draw.circle(surface, (255, 255, 255), pos, 3)  # White center
        
        # Update pulse animation
        self.pulse_phase += 0.1
        if self.pulse_phase > 2 * np.pi:
            self.pulse_phase = 0
    
    def _draw_info_overlay(self, surface):
        """Draw satellite information in top and bottom bars"""
        font_large = pygame.font.Font("assets/swiss911.ttf", 20)
        font_small = pygame.font.Font("assets/swiss911.ttf", 16)
        
        # LCARS colors
        title_color = (255, 153, 0)  # Orange
        text_color = (255, 255, 0)  # Yellow
        
        # === TOP BAR ===
        if self.selected_satellite:
            # Show selected satellite name
            # Find frequency and modulation for this satellite
            freq = None
            mod = None
            for sat_name, f, m in self.satellite_list:
                if sat_name == self.selected_satellite:
                    freq = f
                    mod = m
                    break
            
            title_text = font_large.render(
                "{} ({} MHz {})".format(self.selected_satellite, freq, mod),
                True, title_color
            )
        else:
            # Show "all satellites" mode
            title_text = font_large.render(
                "WEATHER SATELLITES ({})".format(len(self.satellites)),
                True, title_color
            )
        
        surface.blit(title_text, (10, 10))
        
        # Draw current time (right side)
        current_time = datetime.now().strftime("%H:%M:%S UTC")
        time_text = font_small.render(current_time, True, text_color)
        time_rect = time_text.get_rect(topright=(self.display_width - 10, 15))
        surface.blit(time_text, time_rect)
        
        # === BOTTOM BAR ===
        bottom_y = self.map_offset_y + self.map_height + 10
        
        if self.selected_satellite and self.current_lat is not None:
            # Show detailed telemetry for selected satellite
            # Line 1: Position
            pos_text = "Position: {:.2f}°N, {:.2f}°{}".format(
                self.current_lat, 
                abs(self.current_lon),
                'E' if self.current_lon >= 0 else 'W'
            )
            text1 = font_small.render(pos_text, True, text_color)
            
            # Line 2: Altitude and velocity
            alt_text = "Altitude: {:.0f} km | Velocity: ~{:.1f} km/s".format(
                self.current_alt_km if self.current_alt_km else 0,
                self.current_velocity_kms if self.current_velocity_kms else 0
            )
            text2 = font_small.render(alt_text, True, text_color)
            
            # Line 3: Track legend
            legend_text = "Track: "
            text3 = font_small.render(legend_text, True, text_color)
            
            # Draw texts in bottom bar
            surface.blit(text1, (10, bottom_y))
            surface.blit(text2, (10, bottom_y + 20))
            surface.blit(text3, (10, bottom_y + 40))
            
            # Draw colored track indicators after "Track: " text
            legend_x = 10 + text3.get_width() + 5
            legend_y = bottom_y + 43
            
            # Yellow line for past
            pygame.draw.line(surface, (255, 255, 0), 
                            (legend_x, legend_y), 
                            (legend_x + 30, legend_y), 3)
            past_label = font_small.render("Past", True, (255, 255, 0))
            surface.blit(past_label, (legend_x + 35, bottom_y + 40))
            
            # Cyan line for future
            future_x = legend_x + 100
            pygame.draw.line(surface, (0, 255, 255), 
                            (future_x, legend_y), 
                            (future_x + 30, legend_y), 3)
            future_label = font_small.render("Future (2 orbits)", True, (0, 255, 255))
            surface.blit(future_label, (future_x + 35, bottom_y + 40))
        else:
            # Show satellite list when none selected
            help_text = "Click on a satellite to see orbital track"
            text1 = font_small.render(help_text, True, text_color)
            surface.blit(text1, (10, bottom_y))
            
            # List satellites with frequencies
            y_offset = bottom_y + 20
            for sat_name, freq, mod in self.satellite_list:
                if sat_name in self.satellites:
                    sat_text = "{}: {} MHz ({})".format(sat_name, freq, mod)
                    color = (255, 153, 0)  # Orange if available
                else:
                    sat_text = "{}: {} MHz ({}) - NOT FOUND".format(sat_name, freq, mod)
                    color = (100, 100, 100)  # Gray if not found
                
                text = font_small.render(sat_text, True, color)
                surface.blit(text, (10, y_offset))
                y_offset += 18
                
                # Don't overflow the bottom bar
                if y_offset > self.display_height - 10:
                    break
    
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
        
        # Update satellite positions periodically (every 100ms)
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time > 100:
            self.update_satellite_positions()
            self.last_update_time = current_time
        
        # Draw components in order (back to front)
        self._draw_earth_map(self.image)
        
        # If satellite selected, draw its tracks and other satellites
        if self.selected_satellite:
            # Draw selected satellite's full tracks
            self._draw_future_track(self.image)  # Draw future track first (behind past)
            self._draw_ground_track(self.image)  # Draw past track
            
            # Draw other satellites (dimmer, no trails)
            self._draw_other_satellites(self.image)
            
            # Draw selected satellite on top
            self._draw_satellite_position(self.image)
        else:
            # No selection - draw mini trails for all satellites
            self._draw_mini_trails(self.image)
            
            # Draw all satellites
            self._draw_all_satellites(self.image)
        
        self._draw_info_overlay(self.image)  # Draw text overlays last
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks to select satellites"""
        if not self.visible:
            return False
        
        # Handle mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                # Convert to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                # Only process clicks in map area
                if y_rel < self.map_offset_y or y_rel > self.map_offset_y + self.map_height:
                    return False
                
                # Convert to lat/lon
                lat, lon = self._screen_to_latlon(x_rel, y_rel)
                
                # Check if click is near any satellite
                click_threshold = 20  # pixels
                closest_sat = None
                closest_dist = float('inf')
                
                for sat_name, info in self.satellite_info.items():
                    sat_screen_pos = self._latlon_to_screen(info['lat'], info['lon'])
                    
                    # Calculate distance from click to satellite
                    dx = x_rel - sat_screen_pos[0]
                    dy = y_rel - sat_screen_pos[1]
                    dist = np.sqrt(dx*dx + dy*dy)
                    
                    if dist < click_threshold and dist < closest_dist:
                        closest_sat = sat_name
                        closest_dist = dist
                
                if closest_sat:
                    # Toggle selection
                    if self.selected_satellite == closest_sat:
                        # Deselect
                        self.selected_satellite = None
                        print("Deselected satellite")
                    else:
                        # Select new satellite
                        self.selected_satellite = closest_sat
                        # Find frequency and modulation
                        freq = None
                        mod = None
                        for sat_name, f, m in self.satellite_list:
                            if sat_name == closest_sat:
                                freq = f
                                mod = m
                                break
                        
                        print("Selected satellite: {} ({} MHz {})".format(
                            closest_sat, freq, mod))
                    
                    return True
                else:
                    # Click not near any satellite - deselect if one was selected
                    if self.selected_satellite:
                        self.selected_satellite = None
                        print("Deselected satellite")
                        return True
        
        return False
