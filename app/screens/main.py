from datetime import datetime
from ui.widgets.satellite_tracker import LcarsSatelliteTracker
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.waterfall import LcarsWaterfall
from ui.widgets.frequency_selector import LcarsFrequencySelector
from ui.widgets.spectrum_scan_display import LcarsSpectrumScanDisplay
from ui.widgets.demodulator import LcarsDemodulator
from ui.widgets.antenna_analysis import LcarsAntennaAnalysis
from ui.widgets.text_display import LcarsTextDisplay
from ui.widgets.topo_map import LcarsTopoMap
from ui.widgets.geological_map import LcarsGeologicalMap
from ui.widgets.screen import LcarsScreen
from ui.widgets.process_manager import get_process_manager
from ui.widgets.microscope_widget import LcarsMicroscopeWidget
from ui.widgets.emf_manager import LcarsEMFManager
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

        self.microscope_widget = LcarsMicroscopeWidget(
            pos=(187, 299),
            size=(640, 480),
            camera=self.micro.cam,
            screenshot_dir="/home/tricorder/rpi_lcars-master/app/screenshots",
            micro_button=self.micro
        )
        all_sprites.add(self.microscope_widget, layer=2)
        
        self.microscope_file_list = LcarsTextDisplay((135, 1055), (215, 215), font_size=22)
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
        all_sprites.add(self.dashboard, layer=2)
        all_sprites.add(self.dashboard_ref, layer=2)

        # NEW: Topographical map widget for Geospatial mode
        # DON'T load DEM on startup - only when mode is activated (lazy loading)
        self.topo_map = LcarsTopoMap((187, 299), (640, 480), dem_file_path=None)
        all_sprites.add(self.topo_map, layer=2)
        
        # Link topo_map to geospatial modes
        self.geospatial_modes[0]['widget'] = self.topo_map
        
        # NEW: Geological map widget for Geospatial mode
        # DON'T load GeoJSON on startup - only when mode is activated (lazy loading)
        self.geological_map = LcarsGeologicalMap((187, 299), (640, 480), geojson_file=None)
        all_sprites.add(self.geological_map, layer=2)
        
        # Link geological_map to geospatial modes
        self.geospatial_modes[1]['widget'] = self.geological_map
        
        # Store DEM and GeoJSON file paths for lazy loading
        self.dem_file_path = "assets/usgs/USGS_13_n38w078_20211220.tif"
        self.geojson_file_path = "assets/geology/va_geology_37_38.geojson"

        # Satellite tracker for Atmospheric mode
        self.satellite_tracker = LcarsSatelliteTracker((187, 299), (640, 480), 
                                                       earth_map_path="assets/earth_map.jpg")
        all_sprites.add(self.satellite_tracker, layer=2)

        self.weather = LcarsImage("assets/atmosph.png", (187, 299))
        all_sprites.add(self.weather, layer=2)
        
        self.emf_gadget = LcarsImage("assets/emf.png", (187, 299))
        all_sprites.add(self.emf_gadget, layer=2)
        
        self.spectral_gadget = LcarsImage("assets/spectral.png", (187, 299))
        all_sprites.add(self.spectral_gadget, layer=2)
        
        # Waterfall display for live scanning
        self.waterfall_display = LcarsWaterfall((187, 299), (640, 480))
        all_sprites.add(self.waterfall_display, layer=2)
        
        # Frequency selector for SCAN mode (top 30%)
        self.frequency_selector = LcarsFrequencySelector((187, 299), (640, 144))
        all_sprites.add(self.frequency_selector, layer=2)
        
        # Interactive spectrum scan display for SCAN mode (bottom 70%)
        self.spectrum_scan_display = LcarsSpectrumScanDisplay((331, 299), (640, 336))
        all_sprites.add(self.spectrum_scan_display, layer=2)

        # FM/AM Demodulator (non-visual)
        self.demodulator = LcarsDemodulator()
        self.waterfall_display.set_demodulator(self.demodulator)

        # Antenna analysis widget
        self.antenna_analysis = LcarsAntennaAnalysis((187, 299), (640, 480))
        all_sprites.add(self.antenna_analysis, layer=2)

        # EMF mode manager — owns all EMF polling, workflow, and state
        self.emf_manager = LcarsEMFManager(
            emf_button=self.emf,
            emf_gadget=self.emf_gadget,
            antenna_analysis=self.antenna_analysis,
            waterfall_display=self.waterfall_display,
            frequency_selector=self.frequency_selector,
            spectrum_scan_display=self.spectrum_scan_display,
            demodulator=self.demodulator,
            process_manager=self.process_manager,
            text_display=self.microscope_file_list,
            text_display_callback=lambda lines: self.microscope_file_list.set_lines(lines)
        )

        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()
        
        # hide all widgets
        self._hide_all_gadgets()

    def update(self, screenSurface, fpsClock):
        if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
            hour_formatted = int(int(format(datetime.now().strftime("%H"))) / 24 * 10)
            self.stardate.setText("STAR DATE {}".format(datetime.now().strftime("%y%m%d.")) + str(hour_formatted))
            self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)
        
        if self.spectral_gadget.visible and (self.spectro.scanning or self.spectro.analyzing):
            self.spectral_gadget.image = self.spectro.micro_image
        
        self.emf_manager.update(screenSurface)
        
        self.myScreen = screenSurface
    
    def _kill_all_sdr_processes(self):
        """Kill ALL SDR processes by name, even if not tracked by ProcessManager"""
        print("ProcessManager: Performing aggressive SDR process cleanup...")
        self.process_manager.kill_all()

        sdr_commands = ['rtl_fm', 'rtl_scan_2.py', 'rtl_scan_live.py', 'rtl_power', 'rtl_sdr']
        for cmd in sdr_commands:
            try:
                subprocess.run(['killall', '-9', cmd],
                             stderr=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             timeout=1)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                pass
        print("ProcessManager: Aggressive cleanup complete")

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
        self._kill_all_sdr_processes()
        
        self.emf_manager.hide()
        self.spectral_gadget.visible = False
        self.dashboard.visible = False
        self.topo_map.visible = False
        self.geological_map.visible = False
        self.satellite_tracker.visible = False
        self.weather.visible = False
        self.dashboard_ref.visible = False
        self.microscope_widget.visible = False
        
    def _switch_to_mode(self, gadget_name):
        """Switch to a specific gadget mode"""
        self._stop_all_cameras()
        self._hide_all_gadgets()
        
        # Show the requested gadget
        if gadget_name == 'emf':
            self.emf_gadget.visible = True
        elif gadget_name == 'microscope':
            self.microscope_widget.visible = True
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
            
            # Check if click is on TextDisplay while in microscope mode
            if self.microscope_widget.visible:
                if self.microscope_file_list.rect.collidepoint(event.pos):
                    # Calculate which line was clicked
                    y_rel = event.pos[1] - self.microscope_file_list.rect.top
                    line_height = self.microscope_file_list.font_size + 2  # Font size + spacing
                    clicked_line = int(y_rel / line_height)
                    
                    lines = self.microscope_file_list.lines
                    if 0 <= clicked_line < len(lines):
                        line_text = lines[clicked_line]
                        # Try to select this group (works in both live and review modes)
                        if self.microscope_widget.select_group_by_name(line_text):
                            self._update_microscope_display()
                            print("Selected group from click: {}".format(line_text.strip()))
            
            # EMF mode: waterfall, spectrum, frequency selector clicks
            self.emf_manager.handle_click(event)
            
            # Check if click is on microscope file list
            if self.microscope_file_list.visible and self.microscope_file_list.rect.collidepoint(event.pos):
                pass

        if event.type == pygame.MOUSEBUTTONUP:
            # Check if file list selection changed after click
            if self.microscope_file_list.visible and self.microscope_file_list.selected_index is not None:
                # In microscope mode - load selected image
                if self.microscope_widget.visible:
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

                # In EMF antenna-characterization mode - relay band selection
                elif self.antenna_analysis.visible and self.antenna_analysis.scan_complete:
                    self.emf_manager.handle_text_display_selection(
                        self.microscope_file_list.selected_index)

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
            self.microscope_widget.image = review_surf
            print("Reviewing file: {} (mtime: {})".format(
                sorted_files[self.micro.reviewing], 
                os.path.getmtime(sorted_files[self.micro.reviewing])
            ))
    def _update_microscope_display(self):
        """Update text display with microscope status and groups"""
        # Get group browser text
        lines = self.microscope_widget.get_group_browser_text()
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
    
    def _update_microscope_display(self):
        """Update text display with microscope status and groups"""
        # Get group browser text
        lines = self.microscope_widget.get_group_browser_text()
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
            
            
        if self.microscope_widget.visible:
            # In review mode, switch to live view
            if self.microscope_widget.reviewing:
                self.microscope_widget.start_live_view()
                self._update_microscope_display()
                print("Microscope: Switched to live view")
            # Already in live mode, do nothing (or could toggle off if desired)
            return
            
        if self.spectral_gadget.visible:
            if not self.spectro.scanning:
                self.spectro.cam.start()
            self.spectro.analyzing = False
            self.spectro.scanning = True
            
        # EMF mode: antenna analysis, frequency selection, spectrum scanning
        if self.emf_manager.handle_scan():
            return
            
                
    def recordHandler(self, item, event, clock):
        """RECORD: Save screenshot, analyze, or demodulate FM"""
        
        # Geospatial mode: Save waypoint (future)
        if self.topo_map.visible or self.geological_map.visible:
            print("RECORD: Waypoint saved (not implemented yet)")
            # TODO: Save current map center as waypoint
            return
        
        # Microscope: Save screenshot
        if self.microscope_widget.visible and self.microscope_widget.scanning:
            self.microscope_widget.capture_image(self.myScreen)
            self._update_microscope_display()
            
        # Spectral: Start analysis
        if self.spectro.scanning and self.spectral_gadget.visible:
            self.spectro.scanning = False
            self.spectro.analyzing = True
            self.spectro.analyze_complete = False
            print("Analyzing spectral data...")
        
        # EMF/Waterfall: Toggle FM demodulation
        self.emf_manager.handle_record()        
        
            
    def analyzeHandler(self, item, event, clock):
        """ANALYZE: Start/stop live waterfall scan OR review microscope images OR zoom out on map OR jump to waterfall from satellite"""
        
        # Microscope: Toggle between live view and review mode
        if self.microscope_widget.visible:
            if self.microscope_widget.scanning:
                # Switch from live view to review mode
                self.microscope_widget.enter_review_mode()
            else:
                # Switch from review mode back to live view
                self.microscope_widget.start_live_view()
            self._update_microscope_display()
            return
        
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
                    
                    # Start live waterfall at satellite frequency
                    self.emf_manager.start_waterfall_at(target_freq)
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
        if self.microscope_widget.visible:
            if self.microscope_widget.scanning:
                # Switch from live view to review mode
                self.microscope_widget.enter_review_mode()
            else:
                # Switch from review mode back to live view
                self.microscope_widget.start_live_view()
            self._update_microscope_display()
            return
            
        # EMF: Toggle live waterfall scan
        self.emf_manager.handle_analyze()
            
       
    # Navigation handlers - NOW WITH FILTER WIDTH CONTROL (not bandwidth)
    def navHandlerUp(self, item, event, clock):
        """Navigation Up: Pan north (map) OR increase filter width (waterfall) OR increase sweep range (EMF)"""
        # Map pan: Pan north
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(0, self.topo_pan_speed)
            return
        
        # Waterfall filter width / EMF sweep range
        if self.emf_manager.handle_nav_up():
            return
        
        # Microscope navigation (go to first image)
        if self.microscope_widget.visible:
            # Cycle through groups (for filtering in review mode)
            # Or cycle save group (in live mode)
            if self.microscope_widget.scanning:
                self.microscope_widget.cycle_save_group(-1)  # UP = previous group
            else:
                # Cycle through group filters
                self._cycle_microscope_group_filter(-1)
            self._update_microscope_display()
            return
            
    def navHandlerDown(self, item, event, clock):
        """Navigation Down: Pan south (map) OR decrease filter width (waterfall) OR decrease sweep range (EMF)"""
        # Map pan: Pan south
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(0, -self.topo_pan_speed)
            return
        
        # Waterfall filter width / EMF sweep range
        if self.emf_manager.handle_nav_down():
            return
        
        # Microscope navigation
        if self.microscope_widget.visible:
            if self.microscope_widget.scanning:
                self.microscope_widget.cycle_save_group(1)  # DOWN = next group
            else:
                self._cycle_microscope_group_filter(1)
            self._update_microscope_display()
            return
                       
    def navHandlerLeft(self, item, event, clock):
        # Map pan: Pan west
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(self.topo_pan_speed, 0)
            return
        
        # Waterfall frequency adjust
        if self.emf_manager.handle_nav_left():
            return
        
        # Microscope navigation
        if self.microscope_widget.visible and self.microscope_widget.reviewing:
            self.microscope_widget.navigate_images(-1)
            self._update_microscope_display()
            return
            
    def navHandlerRight(self, item, event, clock):
        # Map pan: Pan east
        if self.topo_map.visible or self.dashboard.visible or self.geological_map.visible:
            current_widget = self.geospatial_modes[self.current_geospatial_mode]['widget']
            if current_widget and hasattr(current_widget, 'pan'):
                current_widget.pan(-self.topo_pan_speed, 0)
            return
        
        # Waterfall frequency adjust
        if self.emf_manager.handle_nav_right():
            return
        
        # Microscope navigation
        if self.microscope_widget.visible and self.microscope_widget.reviewing:
            self.microscope_widget.navigate_images(1)
            self._update_microscope_display()
            return
            
    def _cycle_microscope_group_filter(self, direction):
        """Cycle through group filters in review mode"""
        if self.microscope_widget.reviewing:
            self.microscope_widget.cycle_group_filter(direction) 
    
    def _handleMicroscopeNavigation(self, review_index=None, increment=None):
        """Handle microscope image navigation with file list sync"""
        
        if self.microscope_widget.visible:
            self.microscope_widget.visible = False
            self.microscope_widget.visible = True
            
        if not self.microscope_widget.visible:
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
        
        # Start live view
        self.microscope_widget.visible = True
        self.microscope_widget.start_live_view()
        
        # Update text display with groups
        self._update_microscope_display()

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
        self.emf_manager.activate()
        
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
        self.emf_manager.hide()
        self._hide_all_gadgets()
        self.emf_gadget.emf_scanning = False
        
    def logoutHandler(self, item, event, clock):
        # Kill all SDR processes before logout (aggressive cleanup)
        self._kill_all_sdr_processes()
        
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())
