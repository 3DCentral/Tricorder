"""Enhanced Satellite tracker widget with target location crosshair and pass predictions

Adds Richmond, Virginia crosshair as GPS stand-in and calculates when selected 
satellite will be close enough for RTL-SDR reception.
"""
import os
import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
from datetime import datetime, timedelta


class LcarsSatelliteTracker(LcarsWidget):
    """
    Real-time satellite tracking widget with ground station targeting
    
    Displays weather satellites with orbital ground track on Earth map.
    Shows target location (Richmond, VA) and calculates pass predictions
    for RTL-SDR reception planning.
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
        self.image.fill((0, 0, 0))
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Calculate map dimensions to maintain 2:1 aspect ratio
        self.map_width = self.display_width
        self.map_height = self.map_width // 2
        self.map_offset_y = (self.display_height - self.map_height) // 2
        
        # Info display areas
        self.top_bar_height = self.map_offset_y
        self.bottom_bar_height = self.display_height - self.map_height - self.map_offset_y
        
        print("Map layout: {}x{} map, {} top bar, {} bottom bar".format(
            self.map_width, self.map_height, 
            self.top_bar_height, self.bottom_bar_height))
        
        # TARGET LOCATION (Richmond, Virginia - GPS stand-in)
        self.target_lat = 37.5407  # Richmond, VA latitude
        self.target_lon = -77.4360  # Richmond, VA longitude
        self.target_name = "Richmond, VA"
        
        # RTL-SDR reception parameters
        self.min_elevation_angle = 20  # Minimum elevation for good reception (degrees)
        self.max_reception_distance = 3000  # Max line-of-sight distance (km)
        
        # Satellite tracking data
        self.satellites = {}
        self.satellite_info = {}
        self.ts = None
        self.earth_map = None
        self.earth_map_path = earth_map_path
        
        # TLE cache configuration
        # Need multiple groups: weather (NOAA/METEOR), stations (ISS), amateur (ham sats)
        self.tle_urls = [
            'https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle',
            'https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle',  # ISS
            'https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle',   # Ham sats
        ]
        self.cache_file = '/tmp/all_satellites.tle'
        self.cache_expiry_hours = 6
        self.last_tle_update = None
        
        # Satellites to track (RTL-SDR demodulatable)
        self.satellite_list = [
            ('NOAA 20', 137.62, 'APT'),
            ('NOAA 21', 137.9125, 'APT'),
            ('METEOR-M2 3', 137.9, 'LRPT'),
            ('METEOR-M2 4', 137.9, 'LRPT'),
            ('ISS (ZARYA)', 145.800, 'FM/APRS/SSTV'),
            ('SO-50', 145.850, 'FM Voice'),
            ('AO-91', 145.960, 'FM Voice'),
            ('AO-92', 145.880, 'FM Voice'),
        ]
        
        # Selected satellite
        self.selected_satellite = None
        self.tracking_enabled = False  # NEW: Track calculation only enabled via SCAN button
        self.last_tracking_state = False  # Track previous state to avoid immediate recalc
        
        # Pass prediction data
        self.next_pass_info = None  # Will store: time_until, duration, max_elevation
        
        # Trail data
        self.mini_trail_minutes_past = 5  # REDUCED: Shorter trail (was 20)
        self.mini_trail_minutes_future = 20  # RESTORED: Keep future trail longer
        self.mini_trails = {}
        
        # Display state for selected satellite
        self.current_lat = None
        self.current_lon = None
        self.current_alt_km = None
        self.current_velocity_kms = None
        self.ground_track_points = []
        self.future_track_points = []
        self.pass_segments = []  # Info about each receivable pass
        self.track_minutes_past = 10  # REDUCED: Shorter trail (was 90)
        self.track_minutes_future = 180
        
        # Animation state
        self.pulse_phase = 0
        self.last_update_time = 0  # Position updates every 100ms
        self.last_trail_update_time = 0  # Mini trail updates every 5 seconds
        
        # Load Earth map if provided
        if earth_map_path:
            self.load_earth_map(earth_map_path)
        
        # Initialize satellite tracking (lazy load)
        self.initialized = False
    
    def enable_tracking(self):
        """Enable detailed track calculation for selected satellite (called when SCAN pressed)"""
        if self.selected_satellite:
            self.tracking_enabled = True
            print("Tracking enabled for {}".format(self.selected_satellite))
            return True
        else:
            print("No satellite selected - select one first by tapping it")
            return False
    
    def disable_tracking(self):
        """Disable detailed tracking (returns to overview mode with all satellites)"""
        self.tracking_enabled = False
        print("Tracking disabled - showing all satellites")
    
    def load_earth_map(self, image_path):
        """Load Earth map background image"""
        try:
            print("Loading Earth map: {}".format(image_path))
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
        """Download fresh TLE data from CelesTrak (multiple groups)"""
        try:
            import requests
            print("Downloading TLE data from multiple groups...")
            
            all_tle_data = []
            
            # Download each group
            for url in self.tle_urls:
                group_name = url.split('GROUP=')[1].split('&')[0]
                print("  Fetching {} group...".format(group_name))
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                all_tle_data.append(response.text)
            
            # Combine all TLE data into one file
            with open(self.cache_file, 'w') as f:
                f.write('\n'.join(all_tle_data))
            
            self.last_tle_update = datetime.now()
            print("TLE data downloaded and cached ({} groups)".format(len(self.tle_urls)))
            return True
        except Exception as e:
            print("Failed to download TLE data: {}".format(e))
            return False
    
    def _load_tle_from_cache(self):
        """Load TLE data from cache file"""
        if not os.path.exists(self.cache_file):
            return False
        
        # Check if cache is expired
        file_time = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
        age_hours = (datetime.now() - file_time).total_seconds() / 3600
        
        if age_hours > self.cache_expiry_hours:
            print("TLE cache expired ({:.1f} hours old)".format(age_hours))
            return False
        
        print("Using cached TLE data ({:.1f} hours old)".format(age_hours))
        self.last_tle_update = file_time
        return True
    
    def initialize_tracking(self):
        """Initialize satellite tracking with TLE data"""
        try:
            from skyfield.api import load, wgs84, EarthSatellite
            
            # Try cache first, download if needed
            if not self._load_tle_from_cache():
                if not self._download_tle_data():
                    print("ERROR: Could not load or download TLE data")
                    return False
            
            # Load TLE data
            satellites_data = load.tle_file(self.cache_file)
            print("Loaded {} satellites from TLE file".format(len(satellites_data)))
            
            if len(satellites_data) == 0:
                print("ERROR: No satellites found in TLE file")
                return False
            
            # Build dictionary of satellites by name
            sat_by_name = {sat.name: sat for sat in satellites_data}
            
            # Find our weather satellites
            self.satellites = {}
            for sat_name, freq, mod in self.satellite_list:
                if sat_name in sat_by_name:
                    self.satellites[sat_name] = sat_by_name[sat_name]
                    print("Found satellite: {} ({} MHz {})".format(sat_name, freq, mod))
                else:
                    # Try partial match
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
    
    def _calculate_distance_and_elevation(self, sat_lat, sat_lon, sat_alt_km):
        """
        Calculate distance and elevation angle from target to satellite
        
        Args:
            sat_lat: Satellite latitude (degrees)
            sat_lon: Satellite longitude (degrees)
            sat_alt_km: Satellite altitude (km)
            
        Returns:
            tuple: (distance_km, elevation_angle_deg)
        """
        from skyfield.api import wgs84
        
        # Earth radius
        R = 6371.0  # km
        
        # Convert to radians
        lat1 = np.radians(self.target_lat)
        lon1 = np.radians(self.target_lon)
        lat2 = np.radians(sat_lat)
        lon2 = np.radians(sat_lon)
        
        # Haversine formula for great circle distance
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        ground_distance = R * c
        
        # Calculate elevation angle
        # This is simplified - proper calculation would account for Earth curvature
        altitude_diff = sat_alt_km
        elevation_rad = np.arctan2(altitude_diff, ground_distance)
        elevation_deg = np.degrees(elevation_rad)
        
        # Total slant range distance
        slant_range = np.sqrt(ground_distance**2 + altitude_diff**2)
        
        return slant_range, elevation_deg
    
    def _predict_next_pass(self):
        """
        Predict when selected satellite will next be receivable from target location
        
        Returns:
            dict: {'time_until': timedelta, 'duration': timedelta, 'max_elevation': float}
                  or None if no good pass in next 24 hours
        """
        if not self.selected_satellite or self.selected_satellite not in self.satellites:
            return None
        
        try:
            from skyfield.api import wgs84
            
            satellite = self.satellites[self.selected_satellite]
            
            # Create ground station at target location
            ground_station = wgs84.latlon(self.target_lat, self.target_lon)
            
            # Look ahead 24 hours
            t0 = self.ts.now()
            t1 = self.ts.ut1_jd(t0.ut1 + 1.0)  # +1 day
            
            # Find passes using skyfield's built-in function
            t, events = satellite.find_events(
                ground_station, 
                t0, 
                t1, 
                altitude_degrees=self.min_elevation_angle
            )
            
            # events: 0 = rise, 1 = culminate (max elevation), 2 = set
            
            # Find first complete pass (rise -> culminate -> set)
            for i in range(len(events) - 2):
                if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2:
                    # Found a complete pass
                    rise_time = t[i].utc_datetime()
                    culminate_time = t[i+1].utc_datetime()
                    set_time = t[i+2].utc_datetime()
                    
                    # Calculate max elevation at culmination
                    difference = satellite - ground_station
                    topocentric = difference.at(t[i+1])
                    alt, az, distance = topocentric.altaz()
                    max_elevation = alt.degrees
                    
                    # Time until pass starts
                    time_until = rise_time - datetime.now().replace(tzinfo=rise_time.tzinfo)
                    
                    # Pass duration
                    duration = set_time - rise_time
                    
                    return {
                        'time_until': time_until,
                        'duration': duration,
                        'max_elevation': max_elevation,
                        'rise_time': rise_time,
                        'set_time': set_time
                    }
            
            return None  # No good pass found
            
        except Exception as e:
            print("Error predicting pass: {}".format(e))
            return None
    
    def update_satellite_positions(self):
        """Update current satellite positions and predictions"""
        if not self.satellites or not self.ts:
            return
        
        try:
            from skyfield.api import wgs84
            
            t = self.ts.now()
            self.pulse_phase = (self.pulse_phase + 0.1) % (2 * np.pi)
            
            # Update all satellite positions
            self.satellite_info = {}
            for sat_name, satellite in self.satellites.items():
                geocentric = satellite.at(t)
                subpoint = wgs84.subpoint(geocentric)
                
                self.satellite_info[sat_name] = {
                    'lat': subpoint.latitude.degrees,
                    'lon': subpoint.longitude.degrees,
                    'alt_km': subpoint.elevation.km,
                    'velocity_kms': geocentric.velocity.km_per_s
                }
            
            # Update mini trails for all satellites (when no tracking active)
            # Update trails less frequently (every 5 seconds) to avoid lag
            if not self.tracking_enabled:
                current_time_ms = pygame.time.get_ticks()
                time_since_trail_update = current_time_ms - self.last_trail_update_time
                
                # Recalculate trails only every 5 seconds, or if we don't have any yet
                should_update_trails = (
                    len(self.mini_trails) == 0 or 
                    time_since_trail_update > 5000
                )
                
                if should_update_trails:
                    self.mini_trails = {}
                    for sat_name, satellite in self.satellites.items():
                        past_points = []
                        future_points = []
                        
                        # Past trail
                        for minutes_ago in range(self.mini_trail_minutes_past, 0, -2):
                            t_past = self.ts.ut1_jd(t.ut1 - minutes_ago / (24 * 60))
                            geocentric_past = satellite.at(t_past)
                            sub_past = wgs84.subpoint(geocentric_past)
                            screen_pos = self._latlon_to_screen(
                                sub_past.latitude.degrees,
                                sub_past.longitude.degrees
                            )
                            past_points.append(screen_pos)
                        
                        # Add current position to connect past and future trails
                        current_pos = self._latlon_to_screen(
                            self.satellite_info[sat_name]['lat'],
                            self.satellite_info[sat_name]['lon']
                        )
                        past_points.append(current_pos)  # End of past trail
                        future_points.insert(0, current_pos)  # Start of future trail
                        
                        # Future trail
                        for minutes_ahead in range(2, self.mini_trail_minutes_future, 2):
                            t_future = self.ts.ut1_jd(t.ut1 + minutes_ahead / (24 * 60))
                            geocentric_future = satellite.at(t_future)
                            sub_future = wgs84.subpoint(geocentric_future)
                            screen_pos = self._latlon_to_screen(
                                sub_future.latitude.degrees,
                                sub_future.longitude.degrees
                            )
                            future_points.append(screen_pos)
                        
                        self.mini_trails[sat_name] = {
                            'past': past_points,
                            'future': future_points
                        }
                    
                    self.last_trail_update_time = current_time_ms
            else:
                # When tracking is enabled, clear mini trails to save memory
                # They'll be recalculated when tracking is disabled
                if len(self.mini_trails) > 0:
                    self.mini_trails = {}
            
            # Store current tracking state
            self.last_tracking_state = self.tracking_enabled
            
            # Update detailed track ONLY when tracking is enabled (via SCAN button)
            if self.tracking_enabled and self.selected_satellite and self.selected_satellite in self.satellites:
                satellite = self.satellites[self.selected_satellite]
                geocentric = satellite.at(t)
                subpoint = wgs84.subpoint(geocentric)
                
                self.current_lat = subpoint.latitude.degrees
                self.current_lon = subpoint.longitude.degrees
                self.current_alt_km = subpoint.elevation.km
                
                vel = geocentric.velocity.km_per_s
                self.current_velocity_kms = np.sqrt(vel[0]**2 + vel[1]**2 + vel[2]**2)
                
                # Calculate past ground track
                self.ground_track_points = []
                for minutes_ago in range(self.track_minutes_past, 0, -1):
                    t_past = self.ts.ut1_jd(t.ut1 - minutes_ago / (24 * 60))
                    geocentric_past = satellite.at(t_past)
                    sub = wgs84.subpoint(geocentric_past)
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    self.ground_track_points.append(screen_pos)
                
                # Calculate future ground track - extend to show next 2 passes
                self.future_track_points = []
                max_future_minutes = 1440  # Search up to 24 hours ahead
                self.pass_segments = []  # Store info about each receivable pass
                
                current_pass = None
                passes_found = 0
                max_passes = 2  # Only show next 2 passes
                stop_at_minute = None  # Will be set after finding passes
                
                for minutes_ahead in range(1, max_future_minutes):
                    # Stop drawing track shortly after the second pass ends
                    if stop_at_minute is not None and minutes_ahead > stop_at_minute:
                        break
                    
                    t_future = self.ts.ut1_jd(t.ut1 + minutes_ahead / (24 * 60))
                    geocentric_future = satellite.at(t_future)
                    sub = wgs84.subpoint(geocentric_future)
                    
                    screen_pos = self._latlon_to_screen(
                        sub.latitude.degrees,
                        sub.longitude.degrees
                    )
                    self.future_track_points.append(screen_pos)
                    
                    # Check if satellite is close enough to target for reception
                    distance, elevation = self._calculate_distance_and_elevation(
                        sub.latitude.degrees,
                        sub.longitude.degrees,
                        sub.elevation.km
                    )
                    
                    # Track receivable passes
                    is_receivable = (elevation >= self.min_elevation_angle and 
                                   distance <= self.max_reception_distance)
                    
                    if is_receivable:
                        if current_pass is None:
                            # Start of a new pass
                            current_pass = {
                                'start_minute': minutes_ahead,
                                'start_lon': sub.longitude.degrees,  # NEW: Track start longitude
                                'max_elevation': elevation,
                                'max_elevation_minute': minutes_ahead,
                                'max_elevation_lon': sub.longitude.degrees,  # NEW: Track peak longitude
                                'end_minute': minutes_ahead
                            }
                        else:
                            # Continue current pass
                            current_pass['end_minute'] = minutes_ahead
                            if elevation > current_pass['max_elevation']:
                                current_pass['max_elevation'] = elevation
                                current_pass['max_elevation_minute'] = minutes_ahead
                                current_pass['max_elevation_lon'] = sub.longitude.degrees  # NEW: Update peak longitude
                    else:
                        if current_pass is not None:
                            # End of pass - save it
                            current_pass['duration'] = current_pass['end_minute'] - current_pass['start_minute']
                            
                            # NEW: Calculate direction (East or West)
                            # Satellites move west-to-east or east-to-west based on longitude change
                            lon_change = current_pass['max_elevation_lon'] - current_pass['start_lon']
                            
                            # Handle dateline crossing
                            if lon_change > 180:
                                lon_change -= 360
                            elif lon_change < -180:
                                lon_change += 360
                            
                            # Determine cardinal direction based on longitude change
                            if abs(lon_change) < 5:
                                # Nearly overhead, check if trending east or west
                                direction = "N" if lon_change >= 0 else "S"
                            else:
                                # Clear east or west movement
                                direction = "E" if lon_change > 0 else "W"
                            
                            current_pass['direction'] = direction
                            
                            self.pass_segments.append(current_pass)
                            passes_found += 1
                            
                            # After finding 2 passes, set stop point 30 min after last pass
                            if passes_found >= max_passes:
                                stop_at_minute = current_pass['end_minute'] + 30
                            
                            current_pass = None
                
                # Save final pass if we ended in the middle of one
                if current_pass is not None and passes_found < max_passes:
                    current_pass['duration'] = current_pass['end_minute'] - current_pass['start_minute']
                    
                    # NEW: Calculate direction for final pass too
                    lon_change = current_pass['max_elevation_lon'] - current_pass['start_lon']
                    if lon_change > 180:
                        lon_change -= 360
                    elif lon_change < -180:
                        lon_change += 360
                    direction = "E" if lon_change > 0 else "W"
                    if abs(lon_change) < 5:
                        direction = "N" if lon_change >= 0 else "S"
                    current_pass['direction'] = direction
                    
                    self.pass_segments.append(current_pass)
                
                # Predict next pass over target location
                self.next_pass_info = self._predict_next_pass()
            else:
                self.current_lat = None
                self.current_lon = None
                self.current_alt_km = None
                self.current_velocity_kms = None
                self.ground_track_points = []
                self.future_track_points = []
                self.next_pass_info = None
                self.pass_segments = []
            
        except Exception as e:
            print("Error updating satellite positions: {}".format(e))
    
    def _latlon_to_screen(self, lat, lon):
        """Convert latitude/longitude to screen pixel coordinates"""
        x = int((lon + 180) * (self.map_width / 360))
        y = int((90 - lat) * (self.map_height / 180)) + self.map_offset_y
        return (x, y)
    
    def _screen_to_latlon(self, x, y):
        """Convert screen coordinates to latitude/longitude"""
        lon = (x / self.map_width) * 360 - 180
        lat = 90 - ((y - self.map_offset_y) / self.map_height) * 180
        return (lat, lon)
    
    def _draw_earth_map(self, surface):
        """Draw the Earth map background"""
        if self.earth_map:
            surface.blit(self.earth_map, (0, self.map_offset_y))
        else:
            surface.fill((0, 0, 0))
            # Draw grid
            for lat in range(-90, 91, 30):
                y = int((90 - lat) * (self.map_height / 180)) + self.map_offset_y
                pygame.draw.line(surface, (40, 40, 40), 
                               (0, y), (self.display_width, y), 1)
            for lon in range(-180, 181, 30):
                x = int((lon + 180) * (self.map_width / 360))
                pygame.draw.line(surface, (40, 40, 40),
                               (x, self.map_offset_y), 
                               (x, self.map_offset_y + self.map_height), 1)
    
    def _draw_target_crosshair(self, surface):
        """Draw crosshair at target location (Richmond, VA)"""
        pos = self._latlon_to_screen(self.target_lat, self.target_lon)
        
        # Draw crosshair
        crosshair_size = 15
        line_color = (0, 255, 0)  # Green for ground station
        
        # Vertical line
        pygame.draw.line(surface, line_color,
                        (pos[0], pos[1] - crosshair_size),
                        (pos[0], pos[1] + crosshair_size), 2)
        # Horizontal line
        pygame.draw.line(surface, line_color,
                        (pos[0] - crosshair_size, pos[1]),
                        (pos[0] + crosshair_size, pos[1]), 2)
        
        # Draw circle around crosshair
        pygame.draw.circle(surface, line_color, pos, 8, 2)
    
    def _draw_ground_track(self, surface):
        """Draw the satellite's past ground track"""
        if len(self.ground_track_points) < 2:
            return
        
        for i in range(len(self.ground_track_points) - 1):
            p1 = self.ground_track_points[i]
            p2 = self.ground_track_points[i + 1]
            
            if abs(p1[0] - p2[0]) < self.display_width / 2:
                color = (255, 255, 0)  # Yellow
                pygame.draw.line(surface, color, p1, p2, 2)
    
    def _draw_future_track(self, surface):
        """Draw the satellite's predicted future ground track with reception zones highlighted"""
        if len(self.future_track_points) < 2:
            return
        
        try:
            from skyfield.api import wgs84
            
            if not self.selected_satellite or self.selected_satellite not in self.satellites:
                return
            
            satellite = self.satellites[self.selected_satellite]
            t = self.ts.now()
            
            # Draw future track with color coding for receivability
            for i in range(len(self.future_track_points) - 1):
                p1 = self.future_track_points[i]
                p2 = self.future_track_points[i + 1]
                
                # Only draw if line doesn't cross the date line
                if abs(p1[0] - p2[0]) < self.display_width / 2:
                    # Calculate position at this point in the future track
                    minutes_ahead = i + 1
                    t_future = self.ts.ut1_jd(t.ut1 + minutes_ahead / (24 * 60))
                    geocentric_future = satellite.at(t_future)
                    sub = wgs84.subpoint(geocentric_future)
                    
                    # Check if receivable at this point
                    distance, elevation = self._calculate_distance_and_elevation(
                        sub.latitude.degrees,
                        sub.longitude.degrees,
                        sub.elevation.km
                    )
                    
                    # Color code: green if receivable, cyan if not
                    if elevation >= self.min_elevation_angle and distance <= self.max_reception_distance:
                        color = (0, 255, 0)  # Green - receivable zone!
                        thickness = 3  # Thicker line for receivable portions
                    else:
                        color = (0, 255, 255)  # Cyan - future track
                        thickness = 2
                    
                    pygame.draw.line(surface, color, p1, p2, thickness)
            
            # Draw markers at the peak of each pass
            font_tiny = pygame.font.Font("assets/swiss911.ttf", 12)
            for i, pass_info in enumerate(self.pass_segments[:2]):  # Mark only next 2 passes
                max_elev_minute = pass_info['max_elevation_minute']
                
                if max_elev_minute < len(self.future_track_points):
                    marker_pos = self.future_track_points[max_elev_minute]
                    
                    # Draw a circle marker at peak elevation
                    pygame.draw.circle(surface, (255, 255, 0), marker_pos, 6, 2)
                    pygame.draw.circle(surface, (0, 255, 0), marker_pos, 3)
                    
                    # Draw pass number label
                    label = font_tiny.render(str(i + 1), True, (255, 255, 0))
                    label_rect = label.get_rect(center=(marker_pos[0], marker_pos[1] - 12))
                    
                    # Background for label
                    bg_surf = pygame.Surface((label_rect.width + 4, label_rect.height + 2))
                    bg_surf.set_alpha(200)
                    bg_surf.fill((0, 0, 0))
                    surface.blit(bg_surf, (label_rect.x - 2, label_rect.y - 1))
                    surface.blit(label, label_rect)
                    
        except Exception as e:
            # Fallback to simple cyan line if calculation fails
            for i in range(len(self.future_track_points) - 1):
                p1 = self.future_track_points[i]
                p2 = self.future_track_points[i + 1]
                if abs(p1[0] - p2[0]) < self.display_width / 2:
                    pygame.draw.line(surface, (0, 255, 255), p1, p2, 2)
    
    def _draw_mini_trails(self, surface):
        """Draw mini trails for all satellites in overview mode"""
        if not self.mini_trails:
            return
        
        for sat_name, trails in self.mini_trails.items():
            # Draw past trail
            past_points = trails['past']
            if len(past_points) > 1:
                for i in range(len(past_points) - 1):
                    p1 = past_points[i]
                    p2 = past_points[i + 1]
                    if abs(p1[0] - p2[0]) < self.display_width / 2:
                        pygame.draw.line(surface, (200, 200, 0), p1, p2, 1)
            
            # Draw future trail
            future_points = trails['future']
            if len(future_points) > 1:
                for i in range(len(future_points) - 1):
                    p1 = future_points[i]
                    p2 = future_points[i + 1]
                    if abs(p1[0] - p2[0]) < self.display_width / 2:
                        pygame.draw.line(surface, (0, 200, 200), p1, p2, 1)
    
    def _draw_all_satellites(self, surface):
        """Draw all satellite positions, highlighting selected one if any"""
        if not self.satellite_info:
            return
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 18)  # INCREASED from 16
        
        for sat_name, info in self.satellite_info.items():
            pos = self._latlon_to_screen(info['lat'], info['lon'])
            
            # Check if this is the selected satellite
            is_selected = (sat_name == self.selected_satellite)
            
            if is_selected:
                # HIGHLIGHTED: Selected satellite - larger and brighter
                pygame.draw.circle(surface, (255, 0, 0), pos, 8)  # Larger red circle
                pygame.draw.circle(surface, (255, 255, 255), pos, 4)  # White center
                color = (255, 255, 0)  # Yellow text for selected
            else:
                # NORMAL: Regular satellite markers
                pygame.draw.circle(surface, (255, 153, 0), pos, 6)
                pygame.draw.circle(surface, (255, 255, 255), pos, 3)
                color = (255, 153, 0)  # Orange text for unselected
            
            label_text = font_small.render(sat_name, True, color)
            label_rect = label_text.get_rect(topleft=(pos[0] + 8, pos[1] - 8))  # ADJUSTED offset
            
            bg_surf = pygame.Surface((label_rect.width + 4, label_rect.height + 2))
            bg_surf.set_alpha(180)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_rect.x - 2, label_rect.y - 1))
            surface.blit(label_text, label_rect)
    
    def _draw_other_satellites(self, surface):
        """Draw other satellites (not selected) when one is selected"""
        if not self.satellite_info or not self.selected_satellite:
            return
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 16)  # INCREASED from 14
        
        for sat_name, info in self.satellite_info.items():
            if sat_name == self.selected_satellite:
                continue
            
            pos = self._latlon_to_screen(info['lat'], info['lon'])
            
            # INCREASED: Larger dimmed satellites (was 3/1)
            pygame.draw.circle(surface, (150, 100, 0), pos, 5)
            pygame.draw.circle(surface, (200, 200, 200), pos, 2)
            
            label_text = font_small.render(sat_name, True, (150, 100, 0))
            label_rect = label_text.get_rect(topleft=(pos[0] + 7, pos[1] - 7))  # ADJUSTED offset
            
            bg_surf = pygame.Surface((label_rect.width + 3, label_rect.height + 2))
            bg_surf.set_alpha(150)
            bg_surf.fill((0, 0, 0))
            surface.blit(bg_surf, (label_rect.x - 1, label_rect.y - 1))
            surface.blit(label_text, label_rect)
    
    def _draw_satellite_position(self, surface):
        """Draw the selected satellite's current position with pulse effect"""
        if self.current_lat is None or self.current_lon is None:
            return
        
        pos = self._latlon_to_screen(self.current_lat, self.current_lon)
        
        # ENHANCED: Larger pulse effect for better visibility
        pulse_size = int(10 + 4 * np.sin(self.pulse_phase))  # INCREASED from (6 + 2)
        
        # Draw pulsing outer circle
        pygame.draw.circle(surface, (255, 0, 0), pos, pulse_size)
        # Draw solid inner circle
        pygame.draw.circle(surface, (255, 255, 255), pos, 4)  # INCREASED from 2
        
        # Draw line to target if satellite is selected
        if self.selected_satellite:
            target_pos = self._latlon_to_screen(self.target_lat, self.target_lon)
            
            # Calculate distance and elevation
            distance, elevation = self._calculate_distance_and_elevation(
                self.current_lat, self.current_lon, self.current_alt_km
            )
            
            # Color code the line based on receivability
            if elevation >= self.min_elevation_angle and distance <= self.max_reception_distance:
                line_color = (0, 255, 0)  # Green - receivable now!
            else:
                line_color = (100, 100, 100)  # Gray - not receivable
            
            pygame.draw.line(surface, line_color, pos, target_pos, 2)  # THICKER line
    
    def _draw_info_overlay(self, surface):
        """Draw text information overlay"""
        font_medium = pygame.font.Font("assets/swiss911.ttf", 28)  # INCREASED from 24
        font_small = pygame.font.Font("assets/swiss911.ttf", 22)  # INCREASED from 20
        
        if self.selected_satellite:
            # Top bar - satellite info
            sat_name = self.selected_satellite
            freq = None
            mod = None
            for name, f, m in self.satellite_list:
                if name == sat_name:
                    freq = f
                    mod = m
                    break
            
            info_text = "{} - {:.4f} MHz ({})".format(sat_name, freq, mod)
            text = font_medium.render(info_text, True, (255, 255, 255))
            surface.blit(text, (10, 10))
            
            if self.current_alt_km and self.current_velocity_kms:
                detail_text = "Alt: {:.0f} km  Vel: {:.2f} km/s".format(
                    self.current_alt_km, self.current_velocity_kms
                )
                text2 = font_small.render(detail_text, True, (153, 153, 255))
                surface.blit(text2, (10, 35))
            
            # Bottom bar - show all upcoming passes
            if self.pass_segments and len(self.pass_segments) > 0:
                y_offset = self.display_height - 25
                
                # Reverse the order so Pass 1 (soonest) appears at bottom
                passes_to_show = list(reversed(self.pass_segments[:2]))
                
                for i, pass_info in enumerate(passes_to_show):
                    # Pass number should count from closest (1) to furthest (2)
                    pass_number = len(passes_to_show) - i
                    
                    start_min = pass_info['start_minute']
                    duration_min = pass_info['duration']
                    max_elev = pass_info['max_elevation']
                    direction = pass_info.get('direction', '?')  # NEW: Get direction (default '?' if missing)
                    
                    # Determine color based on how soon
                    if start_min < 0:
                        # Pass is happening now!
                        pass_text = "PASS {} IN PROGRESS! ({}, max elev: {:.0f}°, dur: {:.0f} min)".format(
                            pass_number, direction, max_elev, duration_min
                        )
                        pass_color = (0, 255, 0)  # Bright green
                    elif start_min < 60:
                        # Less than 1 hour
                        pass_text = "Pass {} in {} min ({}, max elev: {:.0f}°, dur: {:.0f} min)".format(
                            pass_number, start_min, direction, max_elev, duration_min
                        )
                        pass_color = (255, 255, 0)  # Yellow
                    elif start_min < 360:
                        # Less than 6 hours
                        hours = start_min // 60
                        mins = start_min % 60
                        pass_text = "Pass {} in {}h{}m ({}, max elev: {:.0f}°, dur: {:.0f} min)".format(
                            pass_number, hours, mins, direction, max_elev, duration_min
                        )
                        pass_color = (153, 153, 255)  # Light blue
                    else:
                        # More than 6 hours
                        hours = start_min // 60
                        pass_text = "Pass {} in ~{}h ({}, max elev: {:.0f}°, dur: {:.0f} min)".format(
                            pass_number, hours, direction, max_elev, duration_min
                        )
                        pass_color = (100, 100, 200)  # Dimmer blue
                    
                    text_pass = font_small.render(pass_text, True, pass_color)
                    surface.blit(text_pass, (10, y_offset))
                    y_offset -= 20  # Move up for next pass
                
            else:
                no_pass_text = "No good passes in next 24 hours"
                text3 = font_small.render(no_pass_text, True, (255, 100, 100))
                surface.blit(text3, (10, self.display_height - 25))
            
            # Current distance/elevation to target
            if self.current_lat and self.current_lon and self.current_alt_km:
                distance, elevation = self._calculate_distance_and_elevation(
                    self.current_lat, self.current_lon, self.current_alt_km
                )
                
                status_text = "Distance to {}: {:.0f} km, Elevation: {:.1f}°".format(
                    self.target_name, distance, elevation
                )
                
                if elevation >= self.min_elevation_angle and distance <= self.max_reception_distance:
                    status_color = (0, 255, 0)  # Green - receivable
                else:
                    status_color = (153, 153, 153)  # Gray - not receivable
                
                # Position this above the pass list (2 passes instead of 4)
                y_pos = self.display_height - 25 - (20 * min(len(self.pass_segments), 2)) - 5
                text4 = font_small.render(status_text, True, status_color)
                surface.blit(text4, (10, y_pos))
        else:
            # No satellite selected - show overview info
            title_text = "SATELLITE TRACKER - Click satellite to select"
            text = font_medium.render(title_text, True, (153, 153, 255))
            surface.blit(text, (10, 10))
            
            target_text = "Target: {} ({:.4f}°N, {:.4f}°W)".format(
                self.target_name, self.target_lat, abs(self.target_lon)
            )
            text2 = font_small.render(target_text, True, (0, 255, 0))
            surface.blit(text2, (10, 35))
    
    def _draw_no_data_message(self, surface):
        """Draw message when satellite data unavailable"""
        font = pygame.font.Font("assets/swiss911.ttf", 24)  # Increased from 20
        text = font.render("SATELLITE DATA UNAVAILABLE", True, (255, 100, 100))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2 - 40))
        surface.blit(text, text_rect)
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 18)  # Increased from 16
        text2 = font_small.render("Check network connection and TLE data", True, (153, 153, 255))
        text2_rect = text2.get_rect(center=(self.display_width // 2, self.display_height // 2))
        surface.blit(text2, text2_rect)
    
    def update(self, screen):
        """Update and render the satellite tracker"""
        if not self.visible:
            return
        
        # Lazy initialization
        if not self.initialized:
            self.initialize_tracking()
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        if not self.initialized:
            self._draw_no_data_message(self.image)
            screen.blit(self.image, self.rect)
            self.dirty = 0
            return
        
        # Update satellite positions periodically
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time > 100:
            self.update_satellite_positions()
            self.last_update_time = current_time
        
        # Draw components
        self._draw_earth_map(self.image)
        self._draw_target_crosshair(self.image)  # Always draw target
        
        # Drawing logic based on selection and tracking state
        if self.tracking_enabled and self.selected_satellite:
            # SCAN activated: Show detailed track, hide other satellites
            self._draw_future_track(self.image)
            self._draw_ground_track(self.image)
            self._draw_other_satellites(self.image)
            self._draw_satellite_position(self.image)
        else:
            # Normal view: Show all satellites with mini trails
            # Selected satellite will be highlighted but all are visible
            self._draw_mini_trails(self.image)
            self._draw_all_satellites(self.image)
        
        self._draw_info_overlay(self.image)
        
        screen.blit(self.image, self.rect)
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse clicks to select satellites"""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                x_rel = event.pos[0] - self.rect.left
                y_rel = event.pos[1] - self.rect.top
                
                if y_rel < self.map_offset_y or y_rel > self.map_offset_y + self.map_height:
                    return False
                
                # Check if click is near any satellite
                click_threshold = 20
                closest_sat = None
                closest_dist = float('inf')
                
                for sat_name, info in self.satellite_info.items():
                    sat_screen_pos = self._latlon_to_screen(info['lat'], info['lon'])
                    dx = x_rel - sat_screen_pos[0]
                    dy = y_rel - sat_screen_pos[1]
                    dist = np.sqrt(dx*dx + dy*dy)
                    
                    if dist < click_threshold and dist < closest_dist:
                        closest_sat = sat_name
                        closest_dist = dist
                
                if closest_sat:
                    if self.selected_satellite == closest_sat:
                        # Deselect if clicking same satellite
                        self.selected_satellite = None
                        self.tracking_enabled = False
                        print("Deselected satellite")
                    else:
                        # Just select satellite (don't calculate track yet)
                        self.selected_satellite = closest_sat
                        
                        freq = None
                        mod = None
                        for sat_name, f, m in self.satellite_list:
                            if sat_name == closest_sat:
                                freq = f
                                mod = m
                                break
                        print("Selected satellite: {} ({} MHz {})".format(
                            closest_sat, freq, mod))
                        print("Press SCAN to show detailed track")
                    return True
                else:
                    if self.selected_satellite:
                        self.selected_satellite = None
                        self.tracking_enabled = False
                        print("Deselected satellite")
                        return True
        
        return False
