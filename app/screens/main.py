from datetime import datetime

from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.waterfall import LcarsWaterfall
from ui.widgets.frequency_selector import LcarsFrequencySelector
from ui.widgets.spectrum_scan_display import LcarsSpectrumScanDisplay
from ui.widgets.screen import LcarsScreen
import numpy as np
from time import sleep
import subprocess
import signal
import os
import glob


class ScreenMain(LcarsScreen):
    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars_screen_i5.png"),
                        layer=0)
        all_sprites.add(LcarsText(colours.BLACK, (15, 44), "LCARS 105"),
                        layer=1)
        all_sprites.add(LcarsBlockMedium(colours.RED_BROWN, (186, 5), "SCAN", self.scanHandler),
                        layer=1)
        all_sprites.add(LcarsBlockSmall(colours.ORANGE, (357, 5), "RECORD", self.recordHandler),
                        layer=1)
        all_sprites.add(LcarsBlockLarge(colours.BEIGE, (463, 5), "ANALYZE", self.analyzeHandler),
                        layer=1)

        # date display
        self.stardate = LcarsText(colours.BLUE, (12, 888), "STAR DATE", 1.5)
        self.lastClockUpdate = 0
        all_sprites.add(self.stardate, layer=1)

        # buttons
        all_sprites.add(LcarsBlockTop(colours.PEACH, (72, 248), "ATMOSPHERIC", self.weatherHandler),
                        layer=4)
                        
        self.micro = LcarsMicro(colours.BEIGE, (76, 778), "MICROSCOPE", self.microscopeHandler)
        self.micro.scanning = False
        all_sprites.add(self.micro,
                        layer=4)
        all_sprites.add(LcarsButton(colours.RED_BROWN, (6, 1142), "LOGOUT", self.logoutHandler),
                        layer=4)
        all_sprites.add(LcarsBlockTop(colours.PURPLE, (72, 417), "GEOSPATIAL", self.gaugesHandler),
                        layer=4)
        self.emf = LcarsEMF(colours.PEACH, (72, 587), "EMF", self.emfHandler)
        all_sprites.add(self.emf,
                        layer=4)
        self.emf.scanning = False
        self.spectro = LcarsSpectro(colours.BLUE, (76, 935), "SPECTRAL", self.spectralHandler)
        self.spectro.scanning = False
        self.spectro.analyzing = False
        all_sprites.add(self.spectro,
                        layer=4)
                        
        # D pad for nagivation
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

        self.dashboard = LcarsImage("assets/geo.png", (187, 299))
        self.dashboard_ref = LcarsImage("assets/geo_ref.png", (187, 299))
        self.dashboard.visible = False
        self.dashboard_ref.visible = False
        all_sprites.add(self.dashboard, layer=2)
        all_sprites.add(self.dashboard_ref, layer=2)

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
        
        # NEW: Interactive spectrum scan display for SCAN mode (bottom 70%, below frequency selector)
        # Position: 187 + 144 = 331 from top, size: 640x336
        self.spectrum_scan_display = LcarsSpectrumScanDisplay((331, 299), (640, 336))
        self.spectrum_scan_display.visible = False
        all_sprites.add(self.spectrum_scan_display, layer=2)
        
        # Dimensions for the scan display area (70% of 480 = 336)
        self.scan_display_size = (640, 336)

        #all_sprites.add(LcarsMoveToMouse(colours.WHITE), layer=1)
        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()
        
        self.tuned_in = False
        
        # Initialize spectrum checking throttle
        self.last_spectrum_check = 0
        
        # Scanning animation state
        self.scan_animation_frame = 0
        self.last_animation_update = 0

        # Live scan state
        self.live_scan_process = None
        self.live_scan_active = False
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
                    # Process has finished
                    print("Scan process completed with code: {}".format(poll_result))
                    self.emf.scanning = False
                    self.emf_gadget.emf_scanning = False
                    # Clear scanning highlight on frequency selector
                    self.frequency_selector.clear_scanning_range()
                    # Load the final spectrum image
                    try:
                        loaded_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
                        # Scale to fit the scan display area (640x336)
                        scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                        self.emf.spectrum_image = scaled_image
                        # Update the interactive display
                        self.spectrum_scan_display.set_spectrum_image(scaled_image)
                        self.spectrum_scan_display.set_scan_complete(True)
                        print("Scan complete! Click on spectrum to select new target frequency.")
                    except:
                        pass
            
            # Update scanning animation only if still scanning
            if self.emf.scanning:
                if current_time - self.last_animation_update > 200:  # Update every 200ms
                    self.last_animation_update = current_time
                    self.scan_animation_frame = (self.scan_animation_frame + 1) % 4
                
                # Only check for new spectrum files every 500ms to reduce disk I/O
                if current_time - self.last_spectrum_check > 500:
                    self.last_spectrum_check = current_time
                    try:
                        # Find all progress files
                        progress_files = glob.glob("/home/tricorder/rpi_lcars-master/spectrum_progress_*.png")
                        
                        if progress_files:
                            # Get the most recent one
                            latest_file = max(progress_files, key=os.path.getmtime)
                            
                            # Only reload if it's a new file
                            if not hasattr(self.emf, 'last_spectrum_file') or latest_file != self.emf.last_spectrum_file:
                                # Try to load it
                                loaded_image = pygame.image.load(latest_file)
                                # Scale to fit scan display
                                scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                                self.spectrum_scan_display.set_spectrum_image(scaled_image)
                                self.emf.spectrum_image = loaded_image
                                self.emf.last_spectrum_file = latest_file
                                print("Loaded spectrum update: {}".format(latest_file))
                        else:
                            # Fallback to main spectrum.png if no progress files exist yet
                            if os.path.exists("/home/tricorder/rpi_lcars-master/spectrum.png"):
                                self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
                                
                    except (pygame.error, IOError, OSError) as e:
                        # File is still being written or other IO issue, skip this frame
                        pass
                
                # Draw scanning animation overlay
                self._draw_scanning_animation(screenSurface)
        
        # LIVE WATERFALL UPDATES
        if self.waterfall_display.visible and self.live_scan_active:
            # Check for new waterfall data every 100ms
            current_time = pygame.time.get_ticks()
            if current_time - self.last_waterfall_check > 100:
                self.last_waterfall_check = current_time
                try:
                    # Load waterfall data files
                    waterfall_data = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_waterfall.npy")
                    psd_data = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_psd.npy")
                    frequencies = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_frequencies.npy")
                    
                    # Update waterfall display
                    self.waterfall_display.set_data(waterfall_data, psd_data, frequencies)
                    
                except (IOError, OSError):
                    # Files not ready yet, skip this frame
                    pass
        
        self.myScreen = screenSurface
    
    def _draw_scanning_animation(self, screen):
        """Draw a scanning animation indicator above the spectrum display"""
        dots = [".", "..", "...", "....", ".....", "......", ".......", "........", "........."]
        scan_text = "SCANNING" + dots[self.scan_animation_frame]

        font = pygame.font.Font("assets/swiss911.ttf", 20)
        text_surface = font.render(scan_text, True, (255, 255, 0))
        text_rect = text_surface.get_rect(center=(507, 315))
        
        padding = 10
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + padding * 2,
            text_rect.height + padding * 2
        )
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surface.set_alpha(180)
        bg_surface.fill((0, 0, 0))
        screen.blit(bg_surface, bg_rect)
        screen.blit(text_surface, text_rect)
    
    def _stop_live_scan(self):
        """Stop the live waterfall scan process"""
        if self.live_scan_active and self.live_scan_process:
            print("Stopping live scan process...")
            self.live_scan_process.terminate()
            self.live_scan_process.wait()
            self.live_scan_process = None
        self.live_scan_active = False
    
    def _stop_fm_demodulation(self):
        """Stop FM demodulation if active"""
        if self.tuned_in:
            try:
                os.killpg(os.getpgid(self.fm_pid), signal.SIGTERM)
                print("Stopped FM demodulation")
            except (OSError, ProcessLookupError, AttributeError) as e:
                print("FM demodulation already stopped")
            self.tuned_in = False
    
    def _get_demodulation_params(self, freq_mhz):
        """
        Determine optimal demodulation parameters based on frequency
        
        Args:
            freq_mhz: Frequency in MHz
            
        Returns:
            Dictionary with mode, sample_rate, bandwidth, and mode_name
        """
        # Weather Radio (NOAA): 162.400 - 162.550 MHz
        # Uses narrow-band FM (NBFM) with 12.5 kHz deviation
        if 162.0 <= freq_mhz <= 163.0:
            return {
                'mode': 'fm',           # Narrow-band FM
                'sample_rate': 16000,   # 16 kHz sample rate (increased for better capture)
                'bandwidth': 16000,     # 16 kHz bandwidth
                'gain': 40,             # Specific gain for weak signals
                'squelch': 0,           # No squelch initially (hear everything)
                'mode_name': 'NBFM (Weather Radio)'
            }
        
        # Marine VHF: 156-162 MHz
        # Uses narrow-band FM with 12.5 kHz deviation
        elif 156.0 <= freq_mhz <= 162.0:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,           # Auto gain
                'squelch': 0,
                'mode_name': 'NBFM (Marine VHF)'
            }
        
        # Aviation: 118-137 MHz
        # Uses AM (Amplitude Modulation)
        elif 118.0 <= freq_mhz <= 137.0:
            return {
                'mode': 'am',
                'sample_rate': 12000,
                'bandwidth': 10000,     # 10 kHz for AM aviation
                'gain': None,
                'squelch': 0,
                'mode_name': 'AM (Aviation)'
            }
        
        # 2-meter Ham Radio: 144-148 MHz
        # Uses narrow-band FM with 12.5 kHz or 25 kHz deviation
        elif 144.0 <= freq_mhz <= 148.0:
            return {
                'mode': 'fm',
                'sample_rate': 16000,   # Slightly wider for ham
                'bandwidth': 16000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (2m Ham)'
            }
        
        # Commercial FM Broadcast: 88-108 MHz
        # Uses wide-band FM with 75 kHz deviation
        elif 88.0 <= freq_mhz <= 108.0:
            return {
                'mode': 'wbfm',         # Wide-band FM
                'sample_rate': 200000,  # 200 kHz sample rate
                'bandwidth': 200000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'WBFM (FM Broadcast)'
            }
        
        # PMR446 / FRS / GMRS: 446-467 MHz
        # Uses narrow-band FM
        elif 446.0 <= freq_mhz <= 467.0:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (PMR/FRS/GMRS)'
            }
        
        # 70cm Ham Radio: 420-450 MHz
        # Uses narrow-band FM
        elif 420.0 <= freq_mhz <= 450.0:
            return {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (70cm Ham)'
            }
        
        # Default: Use narrow-band FM for most applications
        # This is a safe default for unknown frequencies
        else:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Default)'
            }
    
    def _stop_all_cameras(self):
        """Stop all camera scanning"""
        if self.micro.scanning:
            self.micro.cam.stop()
            self.micro.scanning = False
        if self.spectro.scanning:
            self.spectro.cam.stop()
            self.spectro.scanning = False
    
    def _hide_all_gadgets(self):
        """Hide all gadget displays"""
        self.emf_gadget.visible = False
        self.microscope_gadget.visible = False
        self.spectral_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        self.waterfall_display.visible = False
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
    
    def _switch_to_mode(self, gadget_name):
        """Switch to a specific gadget mode
        
        Args:
            gadget_name: One of 'emf', 'microscope', 'spectral', 'dashboard', 'weather'
        """
        self._stop_all_cameras()
        self._stop_live_scan()
        self._stop_fm_demodulation()  # Stop FM when switching modes
        self._hide_all_gadgets()
        
        # Show the requested gadget
        if gadget_name == 'emf':
            self.emf_gadget.visible = True
        elif gadget_name == 'microscope':
            self.microscope_gadget.visible = True
        elif gadget_name == 'spectral':
            self.spectral_gadget.visible = True
        elif gadget_name == 'dashboard':
            self.dashboard.visible = True
        elif gadget_name == 'weather':
            self.weather.visible = True
        
        # Reset scanning flags
        self.emf_gadget.emf_scanning = False

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.beep1.play()
            
            # Check if click is on waterfall display
            if self.waterfall_display.visible and self.waterfall_display.rect.collidepoint(event.pos):
                # Convert screen coordinates to widget-relative coordinates
                x_rel = event.pos[0] - self.waterfall_display.rect.left
                y_rel = event.pos[1] - self.waterfall_display.rect.top
                
                # Get frequency from X position
                frequency = self.waterfall_display.get_frequency_from_x(x_rel)
                if frequency:
                    self.waterfall_display.set_selected_frequency(frequency)
                    self.emf_gadget.target_frequency = frequency / 1e6  # Convert to MHz
                    print("Selected frequency: {:.3f} MHz".format(frequency / 1e6))

        if event.type == pygame.MOUSEBUTTONUP:
            return False
            
    def scanHandler(self, item, event, clock):
        """SCAN: Start wide spectrum survey with frequency selection"""
        
        if self.dashboard.visible:
            self.dashboard.visible = False
            self.dashboard_ref.visible = True
            
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
            # If we have a completed scan, show it; otherwise hide it
            if self.spectrum_scan_display.scan_complete:
                self.spectrum_scan_display.visible = True
                print("Scan results restored - Click on spectrum/selector to choose new target, then ANALYZE or SCAN")
                return
            else:
                self.spectrum_scan_display.visible = False
            
        # EMF mode: Show frequency selector and handle scanning
        if self.emf_gadget.visible or self.frequency_selector.visible or self.spectrum_scan_display.visible:
            # If showing completed scan, reset to start new scan
            if self.spectrum_scan_display.visible and self.spectrum_scan_display.scan_complete:
                # Get the selected frequency from the spectrum display (if any)
                if self.spectrum_scan_display.selected_frequency:
                    self.frequency_selector.set_selected_frequency(self.spectrum_scan_display.selected_frequency)
                
                # Reset spectrum display but keep both widgets visible
                self.spectrum_scan_display.set_scan_complete(False)
                self.spectrum_scan_display.clear_selection()
                self.emf_gadget.visible = False
                self.frequency_selector.visible = True
                self.spectrum_scan_display.visible = True
                print("Select a new target frequency (frequency selector or spectrum), then click SCAN again")
                return
            
            # First time: Show frequency selector
            if self.emf_gadget.visible:
                self.emf_gadget.visible = False
                self.frequency_selector.visible = True
                self.spectrum_scan_display.visible = False
                print("Select a target frequency on the scale above, then click SCAN again")
                return
            
            # Subsequent clicks: Start scan if frequency selected
            if self.frequency_selector.visible or self.spectrum_scan_display.visible:
                # Priority: use spectrum display selection if available, otherwise frequency selector
                target_freq = None
                if self.spectrum_scan_display.visible and self.spectrum_scan_display.selected_frequency:
                    target_freq = self.spectrum_scan_display.selected_frequency
                elif hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                    target_freq = self.frequency_selector.selected_frequency
                
                if target_freq is None:
                    print("Please select a target frequency first (click on frequency selector or spectrum)")
                    return
                bandwidth = 20e6  # 20 MHz bandwidth for now
                
                start_freq = int(target_freq - bandwidth / 2)
                end_freq = int(target_freq + bandwidth / 2)
                
                # Ensure frequencies are within valid range
                start_freq = max(int(50e6), start_freq)  # RTL-SDR typically starts at ~50 MHz
                end_freq = min(int(2.2e9), end_freq)
                
                # Store frequency range for the interactive display
                self.current_scan_start_freq = start_freq
                self.current_scan_end_freq = end_freq
                
                print("Starting spectrum scan: {} to {}".format(
                    self.frequency_selector._format_frequency(start_freq),
                    self.frequency_selector._format_frequency(end_freq)
                ))
                
                self.emf.scanning = True
                self.emf_gadget.emf_scanning = True
                
                # Reset spectrum file tracking
                if hasattr(self.emf, 'last_spectrum_file'):
                    delattr(self.emf, 'last_spectrum_file')
                
                # Highlight the scanning range on the selector
                self.frequency_selector.set_scanning_range(start_freq, end_freq)
                
                # Show spectrum scan display AND keep frequency selector visible
                self.frequency_selector.visible = True
                self.spectrum_scan_display.visible = True
                self.spectrum_scan_display.set_scan_complete(False)
                self.spectrum_scan_display.clear_selection()
                
                # Set frequency range for the display
                self.spectrum_scan_display.set_frequency_range(start_freq, end_freq)
                
                # Start multi-frequency scan process
                self.emf.scan_process = subprocess.Popen(
                    ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_2.py', 
                     str(start_freq), str(end_freq)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Clear the spectrum scan display
                self.spectrum_scan_display.set_spectrum_image(None)
            
                
    def recordHandler(self, item, event, clock):
        """RECORD: Save screenshot, analyze, or demodulate FM"""
        
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
        # Priority: waterfall display > spectrum scan display
        target_freq = None
        
        if self.waterfall_display.visible:
            # Use waterfall's selected frequency
            if self.waterfall_display.selected_frequency:
                target_freq = self.waterfall_display.selected_frequency / 1e6  # Convert to MHz
            else:
                print("Please select a target frequency in the waterfall display first")
                return
                
            # Stop live scan process if running (must close SDR before demodulation)
            if self.live_scan_active:
                print("Stopping live scan to free SDR for FM demodulation...")
                self._stop_live_scan()
                # Give the SDR a moment to fully close
                import time
                time.sleep(0.5)
                
        elif self.spectrum_scan_display.visible and self.spectrum_scan_display.scan_complete:
            # Use spectrum scan display's selected frequency
            if not self.spectrum_scan_display.selected_frequency:
                print("Please select a target frequency first by clicking on the spectrum")
                return
            target_freq = self.spectrum_scan_display.selected_frequency / 1e6  # Convert to MHz
        
        # If we have a target frequency, toggle FM demodulation
        if target_freq is not None:
            if self.tuned_in:
                # Stop current demodulation
                self._stop_fm_demodulation()
                
                # If waterfall display is visible, offer to restart the scan
                if self.waterfall_display.visible and not self.live_scan_active:
                    print("Restarting live waterfall scan...")
                    # Give the SDR a moment to fully close
                    import time
                    time.sleep(0.5)
                    
                    # Restart live scan at the same frequency
                    target_freq_hz = int(target_freq * 1e6)
                    self.live_scan_process = subprocess.Popen(
                        ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_live.py', str(target_freq_hz)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    self.live_scan_active = True
                    print("Live waterfall scan restarted at {:.3f} MHz".format(target_freq))
            else:
                # Start FM demodulation with automatic parameter selection
                target_freq_mhz = target_freq
                
                # Determine demodulation parameters based on frequency
                demod_params = self._get_demodulation_params(target_freq_mhz)
                
                print("Tuning {} demodulation to {:.3f} MHz...".format(
                    demod_params['mode_name'], target_freq_mhz))
                print("  Mode: {} | Bandwidth: {} kHz | Sample rate: {} kHz".format(
                    demod_params['mode'],
                    demod_params['bandwidth'] / 1000,
                    demod_params['sample_rate'] / 1000))
                
                # Build rtl_fm command with appropriate parameters
                # Base command
                cmd_parts = [
                    'rtl_fm',
                    '-f {}e6'.format(target_freq_mhz),
                    '-M {}'.format(demod_params['mode']),
                    '-s {}'.format(int(demod_params['sample_rate'])),
                ]
                
                # Add gain if specified
                if demod_params.get('gain') is not None:
                    cmd_parts.append('-g {}'.format(demod_params['gain']))
                    print("  Gain: {} dB".format(demod_params['gain']))
                else:
                    print("  Gain: Auto")
                
                # Add squelch if specified
                if demod_params.get('squelch', 0) > 0:
                    cmd_parts.append('-l {}'.format(demod_params['squelch']))
                    print("  Squelch: {}".format(demod_params['squelch']))
                
                # Add frequency correction (adjust if needed for your hardware)
                cmd_parts.append('-p 0')  # PPM correction (0 = no correction)
                
                # Resample and pipe to audio
                cmd_parts.extend([
                    '-r 48000',  # Resample to 48kHz
                    '-',
                    '|',
                    'play -t raw -r 48k -es -b 16 -c 1 -V1 -'
                ])
                
                # Build full command
                cmd = ' '.join(cmd_parts) + ' 2>&1'  # Capture stderr too
                
                print("  Full command: {}".format(cmd))
                
                try:
                    process = subprocess.Popen(['bash', '-c', cmd], 
                                             preexec_fn=os.setsid,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)
                    self.fm_pid = process.pid
                    self.tuned_in = True
                    print("Demodulation started (PID: {})".format(self.fm_pid))
                    
                    # If waterfall was running, inform user
                    if self.waterfall_display.visible:
                        print("Live waterfall paused during demodulation")
                        print("Click RECORD again to stop and restart waterfall")
                except Exception as e:
                    print("Failed to start demodulation: {}".format(e))
                    self.tuned_in = False        
        
            
    def analyzeHandler(self, item, event, clock):
        """ANALYZE: Start/stop live waterfall scan"""
        
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
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            review_surf = pygame.Surface((640, 480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]), (-299, -187))
            self.microscope_gadget.image = review_surf
            self.micro.reviewing += 1
            print("Reviewing: {}".format(sorted_files[self.micro.reviewing - 1]))
            
        # EMF: Toggle live waterfall scan
        if self.emf_gadget.visible or self.frequency_selector.visible or self.waterfall_display.visible or self.spectrum_scan_display.visible:
            # Determine target frequency
            target_freq = None
            
            # Priority: spectrum scan display selection > frequency selector selection > default
            if self.spectrum_scan_display.visible and self.spectrum_scan_display.selected_frequency:
                target_freq = self.spectrum_scan_display.selected_frequency
            elif hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                target_freq = self.frequency_selector.selected_frequency
            else:
                print("Please select a target frequency first")
                return
            
            # Hide frequency selector and spectrum scan display, keep only waterfall or hide all
            self.frequency_selector.visible = False
            self.spectrum_scan_display.visible = False
            self.emf_gadget.visible = False
            
            if not self.live_scan_active:
                # Start live scan
                target_freq_mhz = target_freq / 1e6
                print("Starting live waterfall at {:.3f} MHz...".format(target_freq_mhz))
                self.live_scan_process = subprocess.Popen(
                    ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_live.py', str(int(target_freq))],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.live_scan_active = True
                self.waterfall_display.visible = True
                self.waterfall_display.set_selected_frequency(target_freq)
            else:
                # Stop live scan but keep waterfall visible (frozen)
                print("Stopping live scan - waterfall frozen")
                self._stop_live_scan()
                
                # Also stop FM demodulation if active (can't have both)
                self._stop_fm_demodulation()
            
       
    # Navigation handlers - consolidated
    def navHandlerUp(self, item, event, clock):
        self._handleMicroscopeNavigation(review_index=0)
            
    def navHandlerDown(self, item, event, clock):
        self._handleMicroscopeNavigation(review_index=-1)
                       
    def navHandlerLeft(self, item, event, clock):
        self._handleMicroscopeNavigation(increment=-1)
        if self.emf_gadget.emf_scanning:
            self.emf_gadget.target_frequency -= 1
                          
    def navHandlerRight(self, item, event, clock):
        self._handleMicroscopeNavigation(increment=1)
        if self.emf_gadget.emf_scanning:
            self.emf_gadget.target_frequency += 1
    
    def _handleMicroscopeNavigation(self, review_index=None, increment=None):
        """Handle microscope image navigation
        
        Args:
            review_index: If set, jump to specific index (0=first, -1=last)
            increment: If set, move by this amount (1=next, -1=previous)
        """
        
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
            
        if not self.microscope_gadget.visible:
            return
             
        # Stop live scanning if active
        if self.micro.scanning:
            self.micro.cam.stop()
        self.micro.scanning = False
        
        # Get sorted list of microscope images
        files = glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")
        if not files:
            return
            
        sorted_files = sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)
        
        # Update review index
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
        
        # Load and display the image
        review_surf = pygame.Surface((640, 480))
        review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]), (-299, -187))
        self.microscope_gadget.image = review_surf
        print("Reviewing file: {} (mtime: {})".format(
            sorted_files[self.micro.reviewing], 
            os.path.getmtime(sorted_files[self.micro.reviewing])
        ))
            
    # TO DO: put these into an array and iterate over them instead
    def gaugesHandler(self, item, event, clock):
        """Switch to GEOSPATIAL dashboard view"""
        self._switch_to_mode('dashboard')

    def microscopeHandler(self, item, event, clock):
        """Switch to MICROSCOPE view and start scanning"""
        self._switch_to_mode('microscope')
        if not self.micro.scanning:
            self.micro.cam.start()
        self.micro.scanning = True
        self.micro.reviewing = 0

    def weatherHandler(self, item, event, clock):
        """Switch to ATMOSPHERIC weather view"""
        self._switch_to_mode('weather')

    def emfHandler(self, item, event, clock):
        """Switch to EMF spectrum analyzer view"""
        self._switch_to_mode('emf')
        # Make sure frequency selector and spectrum scan display are hidden
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        
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
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())
