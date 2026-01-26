from datetime import datetime
from ui.widgets.satellite_tracker import LcarsSatelliteTracker
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.waterfall import LcarsWaterfall
from ui.widgets.frequency_selector import LcarsFrequencySelector
from ui.widgets.spectrum_scan_display import LcarsSpectrumScanDisplay
from ui.widgets.demodulator import LcarsDemodulator
from ui.widgets.text_display import LcarsTextDisplay
from ui.widgets.topo_map import LcarsTopoMap
from ui.widgets.geological_map import LcarsGeologicalMap
from ui.widgets.screen import LcarsScreen
from ui.widgets.process_manager import get_process_manager
import numpy as np
from time import sleep
import subprocess
import signal
import os
import glob


class ScreenMain(LcarsScreen):
    def setup(self, all_sprites):
        # Process manager for tracking and cleaning up SDR processes
        self.process_manager = get_process_manager()
        
        all_sprites.add(LcarsBackgroundImage("assets/lcars_screen_i5.png"), layer=0)
        all_sprites.add(LcarsBlockMedium(colours.RED_BROWN, (186, 5), "SCAN", self.scanHandler), layer=1)
        all_sprites.add(LcarsBlockSmall(colours.ORANGE, (357, 5), "RECORD", self.recordHandler), layer=1)
        all_sprites.add(LcarsBlockLarge(colours.BEIGE, (463, 5), "ANALYZE", self.analyzeHandler), layer=1)

        # date display
        self.stardate = LcarsText(colours.BLUE, (12, 888), "STAR DATE", 1.5)
        self.lastClockUpdate = 0
        all_sprites.add(self.stardate, layer=1)

        # buttons
        all_sprites.add(LcarsBlockTop(colours.PEACH, (72, 248), "ATMOSPHERIC", self.weatherHandler), layer=4)  
        self.micro = LcarsMicro(colours.BEIGE, (76, 778), "MICROSCOPE", self.microscopeHandler)
        self.micro.scanning = False
        self.micro.reviewing = 0  # Initialize reviewing index
        all_sprites.add(self.micro, layer=4)
        all_sprites.add(LcarsButton(colours.RED_BROWN, (6, 1142), "LOGOUT", self.logoutHandler), layer=4)
        all_sprites.add(LcarsBlockTop(colours.PURPLE, (72, 417), "GEOSPATIAL", self.gaugesHandler), layer=4)
        self.emf = LcarsEMF(colours.PEACH, (72, 587), "EMF", self.emfHandler)
        all_sprites.add(self.emf, layer=4)
        self.spectro = LcarsSpectro(colours.BLUE, (76, 935), "SPECTRAL", self.spectralHandler)
        self.spectro.scanning = False
        self.spectro.analyzing = False
        self.emf.scanning = False
        all_sprites.add(self.spectro, layer=4)
                        
        # D pad for navigation
        all_sprites.add(LcarsNav(colours.BLUE,(492,1125),"^", self.navHandlerUp), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(634,1125),"v", self.navHandlerDown), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(560,1055),"<", self.navHandlerLeft), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(560,1194),">", self.navHandlerRight), layer=4)

        # gadgets
        all_sprites.add(LcarsGifImage("assets/gadgets/fwscan.gif", (356, 1058), 100), layer=1)

        # microscope gadget
        self.microscope_gadget = LcarsImage("assets/micro.png", (187, 299))
        self.microscope_gadget_ref = LcarsImage("assets/micro_ref.png", (187, 299))
        self.microscope_gadget.visible = False
        self.microscope_gadget_ref.visible = False
        all_sprites.add(self.microscope_gadget, layer=2)
        all_sprites.add(self.microscope_gadget_ref, layer=2)

        # Microscope file list display - positioned per user specification
        # LcarsWidget position is (top, left) = (y, x)
        # Position: y=135, x=1055, size 215x215
        self.microscope_file_list = LcarsTextDisplay((135, 1055), (215, 215), font_size=16)
        self.microscope_file_list.visible = True  # Always visible
        all_sprites.add(self.microscope_file_list, layer=4)
        
        # Geospatial mode selection - MUST BE EARLY before creating map widgets
        self.geospatial_modes = [
            {
                'name': 'Topographical',
                'description': 'Elevation contours',
                'widget': None  # Will be set after topo_map is created
            },
            {
                'name': 'Geological',
                'description': 'Rock formations',
                'widget': None  # Will be created when implemented
            },
            # Future modes can be added here:
            # {'name': 'Satellite', 'description': 'Aerial imagery', 'widget': None},
            # {'name': 'Street Map', 'description': 'Roads and labels', 'widget': None},
        ]
        self.current_geospatial_mode = 0  # Index into geospatial_modes
        self.topo_pan_speed = 100  # Topographical map pan speed

        # OLD dashboard (static images) - keeping for fallback
        self.dashboard = LcarsImage("assets/geo.png", (187, 299))
        self.dashboard_ref = LcarsImage("assets/geo_ref.png", (187, 299))
        self.dashboard.visible = False
        self.dashboard_ref.visible = False
        all_sprites.add(self.dashboard, layer=2)
        all_sprites.add(self.dashboard_ref, layer=2)

        # NEW: Topographical map widget for Geospatial mode
        # DON'T load DEM on startup - only when mode is activated (lazy loading)
        self.topo_map = LcarsTopoMap((187, 299), (640, 480), dem_file_path=None)
        self.topo_map.visible = False
        all_sprites.add(self.topo_map, layer=2)
        
        # Link topo_map to geospatial modes
        self.geospatial_modes[0]['widget'] = self.topo_map
        
        # NEW: Geological map widget for Geospatial mode
        # DON'T load GeoJSON on startup - only when mode is activated (lazy loading)
        self.geological_map = LcarsGeologicalMap((187, 299), (640, 480), geojson_file=None)
        self.geological_map.visible = False
        all_sprites.add(self.geological_map, layer=2)
        
        # Link geological_map to geospatial modes
        self.geospatial_modes[1]['widget'] = self.geological_map
        
        # Store DEM and GeoJSON file paths for lazy loading
        self.dem_file_path = "assets/usgs/USGS_13_n38w078_20211220.tif"
        self.geojson_file_path = "assets/geology/va_geology_37_38.geojson"

        # Satellite tracker for Atmospheric mode
        self.satellite_tracker = LcarsSatelliteTracker((187, 299), (640, 480), 
                                                       earth_map_path="assets/earth_map.jpg")
        self.satellite_tracker.visible = False
        all_sprites.add(self.satellite_tracker, layer=2)

        self.weather = LcarsImage("assets/atmosph.png", (187, 299))
        self.weather.visible = False
        all_sprites.add(self.weather, layer=2)
        
        self.emf_gadget = LcarsImage("assets/emf.png", (187, 299))
        self.emf_gadget.visible = False
        all_sprites.add(self.emf_gadget, layer=2)
        
        self.spectral_gadget = LcarsImage("assets/spectral.png", (187, 299))
        self.spectral_gadget.visible = False
        all_sprites.add(self.spectral_gadget, layer=2)
        
        # Waterfall display for live scanning
        self.waterfall_display = LcarsWaterfall((187, 299), (640, 480))
        self.waterfall_display.visible = False
        all_sprites.add(self.waterfall_display, layer=2)
        
        # Frequency selector for SCAN mode (top 30%)
        self.frequency_selector = LcarsFrequencySelector((187, 299), (640, 144))
        self.frequency_selector.visible = False
        all_sprites.add(self.frequency_selector, layer=2)
        
        # Interactive spectrum scan display for SCAN mode (bottom 70%)
        self.spectrum_scan_display = LcarsSpectrumScanDisplay((331, 299), (640, 336))
        self.spectrum_scan_display.visible = False
        all_sprites.add(self.spectrum_scan_display, layer=2)
        
        # Dimensions for the scan display area
        self.scan_display_size = (640, 336)

        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()
        
        # FM/AM Demodulator widget (non-visual)
        self.demodulator = LcarsDemodulator()
        
        # Connect demodulator to waterfall for bandwidth visualization
        self.waterfall_display.set_demodulator(self.demodulator)
        
        # Initialize spectrum checking throttle
        self.last_spectrum_check = 0
        
        # Scanning animation state
        self.scan_animation_frame = 0
        self.last_animation_update = 0

        # Live scan state
        self.last_waterfall_check = 0
        
        # Track scan frequency range
        self.current_scan_start_freq = None
        self.current_scan_end_freq = None

    def update(self, screenSurface, fpsClock):
        if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
            hour_formatted = int(int(format(datetime.now().strftime("%H"))) / 24 * 10)
            self.stardate.setText("STAR DATE {}".format(datetime.now().strftime("%y%m%d.")) + str(hour_formatted))
            self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)
        if self.microscope_gadget.visible and self.micro.scanning:
            self.microscope_gadget.image = self.micro.micro_image
        if self.spectral_gadget.visible and (self.spectro.scanning or self.spectro.analyzing):
            self.spectral_gadget.image = self.spectro.micro_image
        
        # LIVE EMF SPECTRUM UPDATES
        if self.spectrum_scan_display.visible and self.emf.scanning:
            current_time = pygame.time.get_ticks()
            
            # Check if scan process is still running
            if hasattr(self.emf, 'scan_process'):
                poll_result = self.emf.scan_process.poll()
                if poll_result is not None:
                    print("Scan process completed with code: {}".format(poll_result))
                    self.emf.scanning = False
                    self.emf_gadget.emf_scanning = False
                    # FIX #2: Keep scanning range visible after completion!
                    # (removed self.frequency_selector.clear_scanning_range())
                    try:
                        loaded_image = pygame.image.load("/tmp/spectrum.png")
                        scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                        self.emf.spectrum_image = scaled_image
                        self.spectrum_scan_display.set_spectrum_image(scaled_image)
                        self.spectrum_scan_display.set_scan_complete(True)
                        print("Scan complete! Click on spectrum to select new target frequency.")
                    except:
                        pass
            
            # Update scanning animation only if still scanning
            if self.emf.scanning:
                if current_time - self.last_animation_update > 200:
                    self.last_animation_update = current_time
                    self.scan_animation_frame = (self.scan_animation_frame + 1) % 4
                
                if current_time - self.last_spectrum_check > 500:
                    self.last_spectrum_check = current_time
                    try:
                        progress_files = glob.glob("/tmp/spectrum_progress_*.png")
                        
                        if progress_files:
                            # FIX: Sort by filename (numerically) to get the latest progress file
                            # spectrum_progress_0001.png, spectrum_progress_0002.png, etc.
                            sorted_files = sorted(progress_files)
                            latest_file = sorted_files[-1]  # Get the last (highest numbered) file
                            
                            if not hasattr(self.emf, 'last_spectrum_file') or latest_file != self.emf.last_spectrum_file:
                                loaded_image = pygame.image.load(latest_file)
                                scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                                self.spectrum_scan_display.set_spectrum_image(scaled_image)
                                self.emf.spectrum_image = loaded_image
                                self.emf.last_spectrum_file = latest_file
                                print("Loaded spectrum update: {}".format(latest_file))
                        else:
                            # Fallback to final spectrum if progress files don't exist
                            if os.path.exists("/tmp/spectrum.png"):
                                self.emf.spectrum_image = pygame.image.load("/tmp/spectrum.png")
                                
                    except (pygame.error, IOError, OSError) as e:
                        pass
                
                self._draw_scanning_animation(screenSurface)
        
        # LIVE WATERFALL UPDATES
        if self.waterfall_display.scan_active:
            current_time = pygame.time.get_ticks()
            if current_time - self.last_waterfall_check > 100:
                self.last_waterfall_check = current_time
                try:
                    waterfall_data = np.load("/tmp/spectrum_live_waterfall.npy")
                    psd_data = np.load("/tmp/spectrum_live_psd.npy")
                    frequencies = np.load("/tmp/spectrum_live_frequencies.npy")
                    
                    self.waterfall_display.set_data(waterfall_data, psd_data, frequencies)
                    
                except (IOError, OSError):
                    pass
        
        self.myScreen = screenSurface
    
    def _draw_scanning_animation(self, screen):
        """Draw a scanning animation indicator above the spectrum display"""
        dots = [".", "..", "...", "....", ".....", "......", ".......", "........", "........."]
        scan_text = "....." + dots[self.scan_animation_frame]

        font = pygame.font.Font("assets/swiss911.ttf", 20)
        text_surface = font.render(scan_text, True, (255, 255, 0))
        text_rect = text_surface.get_rect(center=(607, 155))
        
        bg_rect = pygame.Rect(
            text_rect.x - 10,
            text_rect.y - 10,
            text_rect.width + 10 * 2,
            text_rect.height + 10 * 2
        )
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surface.set_alpha(180)
        bg_surface.fill((0, 0, 0))
        screen.blit(bg_surface, bg_rect)
        screen.blit(text_surface, text_rect)
    
    def _stop_live_scan(self):
        """Stop the live waterfall scan process"""
        self.waterfall_display.stop_scan()
    
    def _stop_fm_demodulation(self):
        """Stop FM demodulation if active"""
        self.demodulator.stop_demodulation()
    
    def _kill_all_sdr_processes(self):
        """Nuclear option: Kill ALL SDR processes by name, even if not tracked"""
        print("ProcessManager: Performing aggressive SDR process cleanup...")
        
        # First, use ProcessManager to kill tracked processes
        self.process_manager.kill_all()
        
        # Then, use killall as backup for any rogue processes
        sdr_commands = ['rtl_fm', 'rtl_scan_2.py', 'rtl_scan_live.py', 'rtl_power', 'rtl_sdr']
        
        for cmd in sdr_commands:
            try:
                subprocess.run(['killall', '-9', cmd], 
                             stderr=subprocess.DEVNULL, 
                             stdout=subprocess.DEVNULL,
                             timeout=1)
                print("  Killed any rogue '{}' processes".format(cmd))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                pass  # No processes found or already dead
        
        print("ProcessManager: Aggressive cleanup complete")
    
    def _adjust_waterfall_filter_width(self, direction):
        """Adjust waterfall filter width (for fine-tuning frequency selection)
        
        Args:
            direction: 1 for increase, -1 for decrease
        """
        self.waterfall_display.adjust_filter_width(direction)
    
    def _adjust_waterfall_frequency(self, direction):
        """Adjust waterfall center frequency"""
        self.waterfall_display.adjust_frequency(direction)
    
    def _restart_live_scan(self, center_freq, sample_rate):
        """Restart live waterfall scan with new parameters"""
        self.waterfall_display.start_scan(center_freq, sample_rate)
    
    def _stop_all_cameras(self):
        """Stop all camera scanning"""
        if self.micro.scanning:
            self.micro.cam.stop()
            self.micro.scanning = False
        if self.spectro.scanning:
            self.spectro.cam.stop()
            self.spectro.scanning = False
    
    def _hide_all_gadgets(self):
        """Hide all gadget displays (text display stays visible)"""
        # Kill all SDR processes when switching modes (aggressive cleanup)
        self._kill_all_sdr_processes()
        
        self.emf_gadget.visible = False
        self.microscope_gadget.visible = False
        self.spectral_gadget.visible = False
        self.dashboard.visible = False
        self.topo_map.visible = False
        self.geological_map.visible = False  # NEW: Hide geological map
        self.satellite_tracker.visible = False  # ADD THIS LINE
        self.weather.visible = False
        self.waterfall_display.visible = False
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
    
        # Reset scanning flags
        self.emf_gadget.emf_scanning = False
        
    def _switch_to_mode(self, gadget_name):
        """Switch to a specific gadget mode"""
        self._stop_all_cameras()
        self._stop_live_scan()
        self._stop_fm_demodulation()
        self._hide_all_gadgets()
        
        # Show the requested gadget
        if gadget_name == 'emf':
            self.emf_gadget.visible = True
        elif gadget_name == 'microscope':
            self.microscope_gadget.visible = True
        elif gadget_name == 'spectral':
            self.spectral_gadget.visible = True
        elif gadget_name == 'dashboard':
            self.topo_map.visible = True
        elif gadget_name == 'weather':
            # Try satellite tracker first, fallback to static image
            if hasattr(self, 'satellite_tracker'):
                self.satellite_tracker.visible = True
            else:
                self.weather.visible = True

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.beep1.play()
            
            # Check if click is on waterfall display
            if self.waterfall_display.visible and self.waterfall_display.rect.collidepoint(event.pos):
                x_rel = event.pos[0] - self.waterfall_display.rect.left
                y_rel = event.pos[1] - self.waterfall_display.rect.top
                
                frequency = self.waterfall_display.get_frequency_from_x(x_rel)
                if frequency:
                    self.waterfall_display.set_selected_frequency(frequency)
                    self.emf_gadget.target_frequency = frequency / 1e6
                    print("Selected frequency: {:.3f} MHz".format(frequency / 1e6))
                    
                    self._updateDemodulationInfo(frequency)
            
            # Check if click is on spectrum scan display
            if self.spectrum_scan_display.visible and self.spectrum_scan_display.rect.collidepoint(event.pos):
                if self.spectrum_scan_display.selected_frequency:
                    self._updateDemodulationInfo(self.spectrum_scan_display.selected_frequency)
                    
                    # FIX #1 PART B: Calculate and display scan range for new target
                    target_freq = self.spectrum_scan_display.selected_frequency
                    bandwidth = 10e6  # 10 MHz bandwidth
                    
                    start_freq = int(target_freq - bandwidth / 2)
                    end_freq = int(target_freq + bandwidth / 2)
                    
                    # Clamp to valid SDR range
                    start_freq = max(int(50e6), start_freq)
                    end_freq = min(int(2.2e9), end_freq)
                    
                    # Update frequency selector with new range
                    if self.frequency_selector.visible:
                        self.frequency_selector.set_selected_frequency(target_freq)
                        self.frequency_selector.set_scanning_range(start_freq, end_freq)
                    
                    # Store for later use
                    self.current_scan_start_freq = start_freq
                    self.current_scan_end_freq = end_freq
                    
                    print("Selected {:.3f} MHz - Will scan {:.3f} to {:.3f} MHz".format(
                        target_freq / 1e6,
                        start_freq / 1e6,
                        end_freq / 1e6
                    ))
            
            # Check if click is on frequency selector
            if self.frequency_selector.visible and self.frequency_selector.rect.collidepoint(event.pos):
                if hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                    self._updateDemodulationInfo(self.frequency_selector.selected_frequency)
                    
                    # FIX #1: PREDICTIVE SCAN WIDTH - Show what WILL be scanned
                    target_freq = self.frequency_selector.selected_frequency
                    bandwidth = 10e6  # 10 MHz scan width (same as in scanHandler)
                    
                    start_freq = int(target_freq - bandwidth / 2)
                    end_freq = int(target_freq + bandwidth / 2)
                    
                    # Clamp to SDR range
                    start_freq = max(int(50e6), start_freq)
                    end_freq = min(int(2.2e9), end_freq)
                    
                    # Show the predicted scan range
                    self.frequency_selector.set_scanning_range(start_freq, end_freq)
                    
                    # Store for later use
                    self.current_scan_start_freq = start_freq
                    self.current_scan_end_freq = end_freq
                    
                    print("Selected {:.3f} MHz - Will scan {:.3f} to {:.3f} MHz".format(
                        target_freq / 1e6,
                        start_freq / 1e6,
                        end_freq / 1e6
                    ))
            
            # Check if click is on microscope file list
            if self.microscope_file_list.visible and self.microscope_file_list.rect.collidepoint(event.pos):
                pass

        if event.type == pygame.MOUSEBUTTONUP:
            # Check if file list selection changed after click
            if self.microscope_file_list.visible and self.microscope_file_list.selected_index is not None:
                # In microscope mode - load selected image
                if self.microscope_gadget.visible:
                    if self.microscope_file_list.selected_index != self.micro.reviewing:
                        self.micro.reviewing = self.microscope_file_list.selected_index
                        self._loadMicroscopeImage()
                
                # In geospatial mode - switch map mode
                elif self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
                    # Calculate which mode was clicked
                    # Mode menu format: "GEOSPATIAL MODES", "", then 3 lines per mode
                    selected_line = self.microscope_file_list.selected_index
                    if selected_line >= 2:  # Skip header lines
                        # Each mode takes 3 lines (name, description, blank)
                        mode_index = (selected_line - 2) // 3
                        if mode_index != self.current_geospatial_mode:
                            self._switch_geospatial_mode(mode_index)
            return False
            
    def _loadMicroscopeImage(self):
        """Load and display the currently selected microscope image"""
        files = glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")
        if not files:
            return
        
        sorted_files = sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)
        
        if 0 <= self.micro.reviewing < len(sorted_files):
            review_surf = pygame.Surface((640, 480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]), (-299, -187))
            self.microscope_gadget.image = review_surf
            print("Reviewing file: {} (mtime: {})".format(
                sorted_files[self.micro.reviewing], 
                os.path.getmtime(sorted_files[self.micro.reviewing])
            ))
    
    def _updateDemodulationInfo(self, frequency_hz):
        """Update text display with demodulation protocol info"""
        # Get current filter width from waterfall if available
        filter_width = None
        if self.waterfall_display.visible:
            filter_width = self.waterfall_display.get_filter_width()
        
        lines = self.demodulator.get_demodulation_info(frequency_hz, filter_width)
        self.microscope_file_list.set_lines(lines)
    
    def _update_geospatial_mode_menu(self):
        """Update text display with geospatial mode selection menu"""
        lines = ["MAP MODES", ""]
        
        # Add each mode to the menu
        for i, mode in enumerate(self.geospatial_modes):
            if i == self.current_geospatial_mode:
                # Current mode - highlight with >>> marker
                lines.append(">>> {}".format(mode['name']))
            else:
                # Other modes - show normally
                lines.append("{}".format(mode['name']))
            
            # Add description on next line, indented
            lines.append("  {}".format(mode['description']))
            lines.append("")  # Blank line between modes
        
        self.microscope_file_list.set_lines(lines)
        
        # Set selected index to current mode
        # Each mode takes 3 lines (name, description, blank), plus 2 header lines
        self.microscope_file_list.set_selected_index(2 + self.current_geospatial_mode * 3)
    
    def _switch_geospatial_mode(self, mode_index):
        """Switch to a different geospatial map mode"""
        if mode_index < 0 or mode_index >= len(self.geospatial_modes):
            return
        
        # Check if the new mode has a widget implemented
        new_mode = self.geospatial_modes[mode_index]
        if new_mode['widget'] is None:
            print("Mode '{}' not yet implemented".format(new_mode['name']))
            return
        
        # Hide current mode widget and save its view state
        current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
        if current_widget:
            current_widget.visible = False
            
            # Save current view state (center location and zoom)
            saved_lat = None
            saved_lon = None
            saved_zoom_index = None
            
            # Get view center - works for both topo and geological maps
            if hasattr(current_widget, 'get_view_center'):
                saved_lat, saved_lon = current_widget.get_view_center()
            elif hasattr(current_widget, 'clicked_lat') and current_widget.clicked_lat:
                # Fallback to clicked location if available
                saved_lat = current_widget.clicked_lat
                saved_lon = current_widget.clicked_lon
            
            if hasattr(current_widget, 'current_zoom_index'):
                saved_zoom_index = current_widget.current_zoom_index
        
        # Lazy load data for new mode if needed
        new_widget = new_mode['widget']
        
        # Load Topographical data if needed
        if mode_index == 0 and self.topo_map.dem_data is None:
            if os.path.exists(self.dem_file_path):
                print("Loading topographical data...")
                self.topo_map.load_dem(self.dem_file_path)
                
                # NEW: Set initial center to target coordinates
                # 37°31'45.2"N 77°27'11.4"W = 37.52922°N, 77.45317°W
                if hasattr(self.topo_map, 'set_view_from_center'):
                    self.topo_map.set_view_from_center(37.52922, -77.45317, 6)  # zoom index 5 = 1.0x
                    print("Centered topo map on target coordinates: 37.52922°N, 77.45317°W")
                    
        # Load Geological data if needed
        elif mode_index == 1 and self.geological_map.gdf is None:
            if os.path.exists(self.geojson_file_path):
                print("Loading geological data...")
                self.geological_map.load_geojson(self.geojson_file_path)
            else:
                print("Geological data file not found: {}".format(self.geojson_file_path))
        
        # Synchronize view state to new mode
        if new_widget and saved_lat is not None and saved_zoom_index is not None:
            # Use the new set_view_from_center method for clean synchronization
            if hasattr(new_widget, 'set_view_from_center'):
                new_widget.set_view_from_center(saved_lat, saved_lon, saved_zoom_index)
                print("Synchronized view: center at ({:.4f}, {:.4f}), zoom index {}".format(
                    saved_lat, saved_lon, saved_zoom_index))
            else:
                # Fallback for widgets without the method
                if hasattr(new_widget, 'clicked_lat'):
                    new_widget.clicked_lat = saved_lat
                    new_widget.clicked_lon = saved_lon
                if hasattr(new_widget, 'current_zoom_index'):
                    new_widget.current_zoom_index = saved_zoom_index
                    if hasattr(new_widget, 'zoom_levels'):
                        new_widget.zoom = new_widget.zoom_levels[saved_zoom_index]
                if hasattr(new_widget, '_center_on_location'):
                    new_widget._center_on_location(saved_lat, saved_lon)
            
            # Invalidate cache
            if hasattr(new_widget, 'cached_surface'):
                new_widget.cached_surface = None
        
        # Show new mode widget
        self.current_geospatial_mode = mode_index
        if new_widget:
            new_widget.visible = True
        
        print("Switched to geospatial mode: {} at zoom {:.1f}x".format(
            self.geospatial_modes[mode_index]['name'],
            new_widget.zoom if new_widget else 1.0))
        
        # Update menu
        self._update_geospatial_mode_menu()
            
    def scanHandler(self, item, event, clock):
        """SCAN: Start wide spectrum survey with frequency selection OR zoom in on map OR enable satellite tracking"""
        
        # Satellite Tracker: Enable detailed tracking for selected satellite
        if hasattr(self, 'satellite_tracker') and self.satellite_tracker.visible:
            if self.satellite_tracker.tracking_enabled:
                # Already tracking - disable to return to overview
                self.satellite_tracker.disable_tracking()
                print("Tracking disabled - showing all satellites")
            else:
                # Not tracking - try to enable
                if self.satellite_tracker.enable_tracking():
                    print("Tracking enabled - calculating ground tracks...")
                else:
                    print("No satellite selected - select one first by tapping it")
            return
        
        # Geospatial mode: Zoom in on clicked location
        if self.dashboard.visible or self.topo_map.visible or self.geological_map.visible:
            # Get current mode widget
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            
            # Zoom in if widget supports it
            if current_widget and hasattr(current_widget, 'zoom_in_on_clicked'):
                current_widget.zoom_in_on_clicked()
            else:
                print("SCAN: Current mode does not support zoom")
            return
            
        if self.microscope_gadget.visible:
            if not self.micro.scanning:
                self.micro.cam.start()
            self.micro.scanning = True
            
        if self.spectral_gadget.visible:
            if not self.spectro.scanning:
                self.spectro.cam.start()
            self.spectro.analyzing = False
            self.spectro.scanning = True
            
        if self.waterfall_display.visible:
            self.waterfall_display.visible = False
            self.frequency_selector.visible = True
            if self.spectrum_scan_display.scan_complete:
                self.spectrum_scan_display.visible = True
                print("Scan results restored")
                return
            else:
                self.spectrum_scan_display.visible = False
            
        # EMF mode: Show frequency selector and handle scanning
        if self.emf_gadget.visible or self.frequency_selector.visible or self.spectrum_scan_display.visible:
            # REMOVED: The "deactivate scan" block that required an extra SCAN press
            # Now users can select a new frequency and scan immediately!
            
            if self.emf_gadget.visible:
                self.emf_gadget.visible = False
                self.frequency_selector.visible = True
                self.spectrum_scan_display.visible = False
                
                # FIX #4: If we have a previous scan range, show it
                if self.current_scan_start_freq and self.current_scan_end_freq:
                    self.frequency_selector.set_scanning_range(
                        self.current_scan_start_freq,
                        self.current_scan_end_freq
                    )
                
                print("Select a target frequency on the scale above")
                return
            
            if self.frequency_selector.visible or self.spectrum_scan_display.visible:
                target_freq = None
                if self.spectrum_scan_display.visible and self.spectrum_scan_display.selected_frequency:
                    target_freq = self.spectrum_scan_display.selected_frequency
                elif hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                    target_freq = self.frequency_selector.selected_frequency
                
                if target_freq is None:
                    print("Please select a target frequency first")
                    return
                bandwidth = 10e6
                
                start_freq = int(target_freq - bandwidth / 2)
                end_freq = int(target_freq + bandwidth / 2)
                
                start_freq = max(int(50e6), start_freq)
                end_freq = min(int(2.2e9), end_freq)
                
                self.current_scan_start_freq = start_freq
                self.current_scan_end_freq = end_freq
                
                print("Starting spectrum scan: {} to {}".format(
                    self.frequency_selector._format_frequency(start_freq),
                    self.frequency_selector._format_frequency(end_freq)
                ))
                
                self.emf.scanning = True
                self.emf_gadget.emf_scanning = True
                
                if hasattr(self.emf, 'last_spectrum_file'):
                    delattr(self.emf, 'last_spectrum_file')
                
                self.frequency_selector.set_scanning_range(start_freq, end_freq)
                
                self.frequency_selector.visible = True
                self.spectrum_scan_display.visible = True
                self.spectrum_scan_display.set_scan_complete(False)
                self.spectrum_scan_display.clear_selection()
                
                self.spectrum_scan_display.set_frequency_range(start_freq, end_freq)
                
                self.emf.scan_process = self.process_manager.start_process(
                    'spectrum_scanner',
                    ['python3', '/home/tricorder/rpi_lcars-master/rtl_scan_2.py', 
                     str(start_freq), str(end_freq)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.spectrum_scan_display.set_spectrum_image(None)
            
                
    def recordHandler(self, item, event, clock):
        """RECORD: Save screenshot, analyze, or demodulate FM"""
        
        # Geospatial mode: Save waypoint (future)
        if self.topo_map.visible or self.geological_map.visible:
            print("RECORD: Waypoint saved (not implemented yet)")
            # TODO: Save current map center as waypoint
            return
        
        # Microscope: Save screenshot
        if self.micro.scanning and self.microscope_gadget.visible:
            filename = "microscope_{}.jpg".format(datetime.now().strftime("%y.%m.%d.%H.%M.%S"))
            pygame.image.save(self.myScreen, "/home/tricorder/rpi_lcars-master/app/screenshots/" + filename)
            print("Saved screenshot: {}".format(filename))
            
        # Spectral: Start analysis
        if self.spectro.scanning and self.spectral_gadget.visible:
            self.spectro.scanning = False
            self.spectro.analyzing = True
            self.spectro.analyze_complete = False
            print("Analyzing spectral data...")
        
        # EMF/Waterfall: Toggle FM demodulation
        target_freq = None
        
        if self.waterfall_display.visible:
            if self.waterfall_display.selected_frequency:
                target_freq = self.waterfall_display.selected_frequency / 1e6
            else:
                print("Please select a target frequency first")
                return
                
            if self.waterfall_display.scan_active:
                print("Stopping live scan for demodulation...")
                self._stop_live_scan()
                self.waterfall_display.scan_active = False
                sleep(0.5)
                
        elif self.spectrum_scan_display.visible and self.spectrum_scan_display.scan_complete:
            if not self.spectrum_scan_display.selected_frequency:
                print("Please select a target frequency first")
                return
            target_freq = self.spectrum_scan_display.selected_frequency / 1e6
        
        if target_freq is not None:
            target_freq_hz = int(target_freq * 1e6)
            
            # Get current filter width from waterfall
            filter_width = None
            if self.waterfall_display.visible:
                filter_width = self.waterfall_display.get_filter_width()
            
            if self.demodulator.is_active():
                self._stop_fm_demodulation()
                self._updateDemodulationInfo(target_freq_hz)
                
                if self.waterfall_display.visible and not self.waterfall_display.scan_active:
                    print("Restarting live waterfall scan...")
                    sleep(0.5)
                    # BUG FIX: Use waterfall's original center_frequency, not selected_frequency
                    restart_freq = self.waterfall_display.center_frequency if self.waterfall_display.center_frequency else target_freq_hz
                    self.waterfall_display.start_scan(restart_freq)
                    print("Live waterfall scan restarted at {:.3f} MHz".format(restart_freq / 1e6))
            else:
                self.demodulator.start_demodulation(target_freq_hz, filter_width)
                self._updateDemodulationInfo(target_freq_hz)
                
                if self.waterfall_display.visible:
                    print("Live waterfall paused during demodulation")        
        
            
    def analyzeHandler(self, item, event, clock):
        """ANALYZE: Start/stop live waterfall scan OR review microscope images OR zoom out on map OR jump to waterfall from satellite"""
        
        # Satellite Tracker: Jump to waterfall if satellite selected
        if hasattr(self, 'satellite_tracker') and self.satellite_tracker.visible:
            if self.satellite_tracker.selected_satellite:
                # Get the frequency for the selected satellite
                sat_name = self.satellite_tracker.selected_satellite
                target_freq = None
                
                for name, freq_mhz, mode in self.satellite_tracker.satellite_list:
                    if name == sat_name:
                        target_freq = int(freq_mhz * 1e6)  # Convert MHz to Hz
                        break
                
                if target_freq:
                    print("Jumping to waterfall for {} at {:.4f} MHz".format(sat_name, target_freq / 1e6))
                    
                    # Hide satellite tracker and weather mode
                    self.satellite_tracker.visible = False
                    self.weather.visible = False
                    
                    # Show EMF mode waterfall
                    self.emf_gadget.visible = False
                    self.frequency_selector.visible = False
                    self.spectrum_scan_display.visible = False
                    
                    # Start live waterfall at satellite frequency
                    self.waterfall_display.start_scan(target_freq)
                    self.waterfall_display.visible = True
                    self.waterfall_display.set_selected_frequency(target_freq)
                    
                    self._updateDemodulationInfo(target_freq)
                    print("Live waterfall started - use RECORD to demodulate")
                else:
                    print("ERROR: Could not find frequency for {}".format(sat_name))
            else:
                print("No satellite selected - select one first by tapping it")
            return
        
        # Geospatial mode: Zoom out on clicked location
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            # Get current mode widget
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            
            # Zoom out if widget supports it
            if current_widget and hasattr(current_widget, 'zoom_out_on_clicked'):
                current_widget.zoom_out_on_clicked()
            else:
                print("ANALYZE: Current mode does not support zoom")
            return
        
        # Microscope: Review saved images
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
            
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            
            files = glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")
            if not files:
                return
                
            sorted_files = sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)
            
            self.microscope_file_list.visible = True
            
            file_display_names = []
            for f in sorted_files:
                mtime = os.path.getmtime(f)
                timestamp = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M:%S")
                file_display_names.append(timestamp)
            
            self.microscope_file_list.set_lines(file_display_names)
            
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            self.microscope_file_list.set_selected_index(self.micro.reviewing)
            
            self._loadMicroscopeImage()
            self.micro.reviewing += 1
            
        # EMF: Toggle live waterfall scan
        if self.emf_gadget.visible or self.frequency_selector.visible or self.waterfall_display.visible or self.spectrum_scan_display.visible:
            target_freq = None
            
            if self.spectrum_scan_display.visible and self.spectrum_scan_display.selected_frequency:
                target_freq = self.spectrum_scan_display.selected_frequency
            elif hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                target_freq = self.frequency_selector.selected_frequency
            else:
                print("Please select a target frequency first")
                return
            
            self.frequency_selector.visible = False
            self.spectrum_scan_display.visible = False
            self.emf_gadget.visible = False
            
            if not self.waterfall_display.scan_active:
                print("Starting live waterfall at {:.3f} MHz...".format(target_freq / 1e6))
                self.waterfall_display.start_scan(target_freq)
                self.waterfall_display.visible = True
                self.waterfall_display.set_selected_frequency(target_freq)
                
                self._updateDemodulationInfo(target_freq)
            else:
                print("Stopping live scan - waterfall frozen")
                self._stop_live_scan()
                self._stop_fm_demodulation()
            
       
    # Navigation handlers - NOW WITH FILTER WIDTH CONTROL (not bandwidth)
    def navHandlerUp(self, item, event, clock):
        """Navigation Up: Pan north (map) OR increase filter width (waterfall)"""
        # Map pan: Pan north
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(0, self.topo_pan_speed)
            return
        
        # Waterfall: INCREASE FILTER WIDTH (changed from bandwidth)
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self._adjust_waterfall_filter_width(1)
            return
        
        # Microscope navigation
        self._handleMicroscopeNavigation(review_index=0)
            
    def navHandlerDown(self, item, event, clock):
        """Navigation Down: Pan south (map) OR decrease filter width (waterfall)"""
        # Map pan: Pan south
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(0, -self.topo_pan_speed)
            return
        
        # Waterfall: DECREASE FILTER WIDTH (changed from bandwidth)
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self._adjust_waterfall_filter_width(-1)
            return
        
        # Microscope navigation
        self._handleMicroscopeNavigation(review_index=-1)
                       
    def navHandlerLeft(self, item, event, clock):
        # Map pan: Pan west
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(self.topo_pan_speed, 0)
            return
        
        # Waterfall: decrease frequency
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self._adjust_waterfall_frequency(-1)
            return
        
        # Microscope navigation
        self._handleMicroscopeNavigation(increment=-1)
        if self.emf_gadget.emf_scanning:
            self.emf_gadget.target_frequency -= 1
                          
    def navHandlerRight(self, item, event, clock):
        # Map pan: Pan east
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(-self.topo_pan_speed, 0)
            return
        
        # Waterfall: increase frequency
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self._adjust_waterfall_frequency(1)
            return
        
        # Microscope navigation
        self._handleMicroscopeNavigation(increment=1)
        if self.emf_gadget.emf_scanning:
            self.emf_gadget.target_frequency += 1
    
    def _handleMicroscopeNavigation(self, review_index=None, increment=None):
        """Handle microscope image navigation with file list sync"""
        
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
            
        if not self.microscope_gadget.visible:
            return
             
        if self.micro.scanning:
            self.micro.cam.stop()
        self.micro.scanning = False
        
        files = glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")
        if not files:
            return
            
        sorted_files = sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)
        
        if review_index is not None:
            if review_index == -1:
                self.micro.reviewing = len(files) - 1
            else:
                self.micro.reviewing = review_index
        elif increment is not None:
            self.micro.reviewing += increment
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            elif self.micro.reviewing < 0:
                self.micro.reviewing = len(files) - 1
        
        if self.microscope_file_list.visible:
            self.microscope_file_list.set_selected_index(self.micro.reviewing)
        
        self._loadMicroscopeImage()
            
    def gaugesHandler(self, item, event, clock):
        """Switch to GEOSPATIAL mode (now with topo map!)"""
        self._switch_to_mode('dashboard')
        
        # Lazy load DEM data if not already loaded
        if self.topo_map.dem_data is None and os.path.exists(self.dem_file_path):
            print("Loading DEM data for first time...")
            
            # Show loading message
            self.microscope_file_list.set_lines([
                "LOADING DEM DATA",
                "",
                "Please wait...",
                "",
                "Processing elevation",
                "data from GeoTIFF",
                "",
                "This may take",
                "10-20 seconds"
            ])
            
            # Force update display to show loading message
            self.microscope_file_list.dirty = 1
            
            # Load the DEM (this is the slow part)
            self.topo_map.load_dem(self.dem_file_path)

            # NEW: Set initial center to target coordinates
            # 37°31'45.2"N 77°27'11.4"W = 37.52922°N, 77.45317°W
            if hasattr(self.topo_map, 'set_view_from_center'):
                self.topo_map.set_view_from_center(37.52922, -77.45317, 6)  # zoom index 5 = 1.0x
                print("Centered topo map on target coordinates: 37.52922°N, 77.45317°W")
        
        # Set up map mode selection menu
        self._update_geospatial_mode_menu()

    def microscopeHandler(self, item, event, clock):
        """Switch to MICROSCOPE view and start scanning"""
        self._switch_to_mode('microscope')
        
        self.microscope_file_list.clear()
        
        if not self.micro.scanning:
            self.micro.cam.start()
        self.micro.scanning = True
        self.micro.reviewing = 0

    def weatherHandler(self, item, event, clock):
        """Switch to ATMOSPHERIC satellite tracker view"""
        self._switch_to_mode('weather')
        
        # Try to show satellite tracker first
        if hasattr(self, 'satellite_tracker'):
            self.satellite_tracker.visible = True
            self.weather.visible = False  # Hide fallback image
        else:
            # Fallback to static image if tracker not available
            self.weather.visible = True

    def emfHandler(self, item, event, clock):
        """Switch to EMF spectrum analyzer view"""
        self._switch_to_mode('emf')
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        
        self._updateDemodulationInfo(None)
        
    def spectralHandler(self, item, event, clock):
        """Switch to SPECTRAL analysis view"""
        self._switch_to_mode('spectral')
        if not self.spectro.scanning and not self.spectro.analyzing:
            self.spectro.cam.start()
        self.spectro.scanning = True
        self.spectro.analyzing = False
    
    def homeHandler(self, item, event, clock):
        """Return to home screen"""
        self._stop_all_cameras()
        self._stop_live_scan()
        self._stop_fm_demodulation()
        self._hide_all_gadgets()
        self.emf_gadget.emf_scanning = False
        
    def logoutHandler(self, item, event, clock):
        # Kill all SDR processes before logout (aggressive cleanup)
        self._kill_all_sdr_processes()
        
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())
