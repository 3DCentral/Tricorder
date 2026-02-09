import pygame
import numpy as np
import subprocess
import os
import glob
import json
from time import sleep


class LcarsEMFManager:
    """
    Manages the entire EMF mode: antenna analysis, spectrum scanning,
    live waterfall, and FM demodulation.
    
    Owns all EMF-related state, polling, and workflow logic that previously
    lived in main.py. Main only needs to call the public interface methods.
    """

    def __init__(self, emf_button, emf_gadget, antenna_analysis,
                 waterfall_display, frequency_selector, spectrum_scan_display,
                 demodulator, process_manager, text_display_callback,
                 text_display=None):
        """
        Args:
            emf_button: The LcarsEMF sidebar button (has .scanning flag)
            emf_gadget: Static EMF background image widget
            antenna_analysis: LcarsAntennaAnalysis widget
            waterfall_display: LcarsWaterfall widget
            frequency_selector: LcarsFrequencySelector widget
            spectrum_scan_display: LcarsSpectrumScanDisplay widget
            demodulator: LcarsDemodulator widget
            process_manager: Shared ProcessManager instance
            text_display_callback: Function(lines) to update the side text display
            text_display: The LcarsTextDisplay widget itself (for set_selected_index)
        """
        # Widget references
        self.emf_button = emf_button
        self.emf_gadget = emf_gadget
        self.antenna_analysis = antenna_analysis
        self.waterfall_display = waterfall_display
        self.frequency_selector = frequency_selector
        self.spectrum_scan_display = spectrum_scan_display
        self.demodulator = demodulator
        self.process_manager = process_manager
        self._set_text = text_display_callback
        self._text_display = text_display

        # Scan display dimensions
        self.scan_display_size = (640, 336)

        # Antenna scan state
        self.antenna_scan_active = False
        self.antenna_scan_process = None
        self._last_antenna_check = 0
        self.targeted_scan = False  # True when running a high-density band-specific scan

        # Spectrum scan state
        self._last_spectrum_check = 0
        self._last_spectrum_file = None
        self.current_scan_start_freq = None
        self.current_scan_end_freq = None

        # Scanning animation state
        self._scan_animation_frame = 0
        self._last_animation_update = 0

        # Waterfall polling state
        self._last_waterfall_check = 0
        
        # --- DEMODULATION MODE SELECTION ---
        # Track which demodulation mode is selected
        self.selected_demod_mode = 0  # Index into available modes
        self.demod_modes = [
            {
                'name': 'FM Audio',
                'description': 'Standard FM/AM demodulation',
                'handler': self._demod_fm_audio
            }
            # Future modes will be added here:
            # {'name': 'Pager Decode', 'description': 'POCSAG/FLEX pagers', ...},
            # {'name': 'APRS', 'description': 'GPS tracking packets', ...},
        ]

    # ---------------------------------------------------------------
    # Public interface — called by main.py
    # ---------------------------------------------------------------

    def is_active(self):
        """True if any EMF widget is currently visible."""
        return (self.emf_gadget.visible or
                self.antenna_analysis.visible or
                self.frequency_selector.visible or
                self.spectrum_scan_display.visible or
                self.waterfall_display.visible)

    def activate(self):
        """Enter EMF mode. Starts antenna characterization scan."""
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.emf_gadget.visible = False
        self.antenna_analysis.visible = True

        if not self.antenna_scan_active:
            print("Starting antenna characterization scan...")
            self.antenna_scan_active = True
            self.targeted_scan = False  # This is a wide scan
            
            # Clear any previous scan data to ensure clean state
            self.antenna_analysis.clear()
            self.antenna_analysis.start_scan()

            # Clear stale data files from previous run
            for f in glob.glob("/tmp/antenna_scan_*"):
                try:
                    os.remove(f)
                except OSError:
                    pass

            self.antenna_scan_process = self.process_manager.start_process(
                'antenna_scanner',
                ['python3', '/home/tricorder/rpi_lcars-master/rtl_antenna_scan.py', '40'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print("Antenna scan started - ~10 seconds")

        # Push band list if scan already finished (re-entering EMF mode),
        # otherwise show demod placeholder until the scan completes and
        # _poll_antenna_scan replaces it.
        if self.antenna_analysis.scan_complete:
            self._push_band_list()
        else:
            self._set_text(self.demodulator.get_demodulation_info(None, None))

    def hide(self):
        """Hide all EMF widgets. Called when switching away from EMF mode."""
        # Stop any running subprocesses before hiding — otherwise the SDR
        # device stays locked by a waterfall or demodulator process.
        if self.waterfall_display.scan_active:
            self.waterfall_display.stop_scan()
        if self.demodulator.is_active():
            self.demodulator.stop_demodulation()

        self.emf_gadget.visible = False
        self.antenna_analysis.visible = False
        self.waterfall_display.visible = False
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.emf_gadget.emf_scanning = False

    def update(self, screen):
        """Per-frame polling. Call once per frame from main update loop."""
        self._poll_antenna_scan()
        self._poll_spectrum_scan(screen)
        self._poll_waterfall()

    # ---------------------------------------------------------------
    # Button handlers — called by main.py's SCAN/ANALYZE/RECORD
    # ---------------------------------------------------------------

    def handle_scan(self):
        """Handle SCAN button while EMF is active. Returns True if consumed."""
        if not self.is_active():
            return False

        # Waterfall visible → back to frequency selector
        if self.waterfall_display.visible:
            # Clean up any live subprocess before hiding — otherwise the SDR
            # device stays locked and the next ANALYZE can't restart it.
            if self.waterfall_display.scan_active:
                self.waterfall_display.stop_scan()
            # Same for the demodulator: after the SCAN→ANALYZE→RECORD flow the
            # demod holds the SDR; if the user hits SCAN without toggling
            # ANALYZE off first we need to release it here.
            if self.demodulator.is_active():
                self.demodulator.stop_demodulation()

            self.waterfall_display.visible = False
            self.frequency_selector.visible = True
            if self.spectrum_scan_display.scan_complete:
                self.spectrum_scan_display.visible = True
                print("Scan results restored")
            else:
                self.spectrum_scan_display.visible = False
            return True

        # Antenna analysis visible → switch to frequency selector
        if self.antenna_analysis.visible:
            print("Switching to frequency selector mode")
            self.antenna_analysis.visible = False
            self.frequency_selector.visible = True
            self.spectrum_scan_display.visible = False

            # Stop antenna scan if still running
            if self.antenna_scan_active and self.antenna_scan_process:
                try:
                    self.antenna_scan_process.terminate()
                    self.antenna_scan_process.wait(timeout=1)
                except OSError:
                    pass
                self.antenna_scan_active = False

            # Set up frequency selector based on selected band (if any)
            self._restore_scan_range()
            
            # Update text display with band info or generic message
            if (self.antenna_analysis.scan_complete and 
                self.antenna_analysis.selected_band is not None):
                selected_band = self.antenna_analysis.get_selected_band()
                if selected_band:
                    # Show info about the pre-configured band
                    info_lines = [
                        "FREQUENCY SELECTOR",
                        "",
                        "Pre-configured for: {}".format(selected_band['name']),
                        "Range: {:.1f}-{:.1f} MHz".format(
                            selected_band['start'],
                            selected_band['end']
                        ),
                        "",
                        "Tap SCAN to analyze this band",
                        "or click to select different frequency",
                        "",
                        "Use UP/DOWN arrows to adjust sweep range"
                    ]
                    self._set_text(info_lines)
                else:
                    print("Select a target frequency on the scale above")
            else:
                print("Select a target frequency on the scale above")
            return True

        # Static EMF gadget visible → switch to frequency selector
        if self.emf_gadget.visible:
            self.emf_gadget.visible = False
            self.frequency_selector.visible = True
            self.spectrum_scan_display.visible = False

            self._restore_scan_range()
            print("Select a target frequency on the scale above")
            return True

        # Frequency selector or spectrum display visible → start scan
        if self.frequency_selector.visible or self.spectrum_scan_display.visible:
            self._start_spectrum_scan()
            return True

        return False

    def handle_analyze(self):
        """Handle ANALYZE button while EMF is active. Returns True if consumed."""
        if not self.is_active():
            return False

        # --- Antenna characterization: targeted deep sweep -------------------
        # This must come first.  When antenna_analysis is visible the rest of
        # this method (waterfall logic) is irrelevant and would bail on
        # "no selected frequency" anyway.
        if self.antenna_analysis.visible:
            if not self.antenna_analysis.scan_complete:
                print("Antenna scan still in progress — wait for it to finish")
                return True

            band = self.antenna_analysis.get_selected_band()
            if band is None:
                print("Select a band of interest first (tap on the graph or the list)")
                return True

            # Band is selected and scan is complete — launch targeted high-density sweep
            start_freq_hz = int(band['start'] * 1e6)
            end_freq_hz   = int(band['end']   * 1e6)
            
            # For narrow bands (< 10 MHz) use very high density; wider bands scale down
            bandwidth_mhz = band['end'] - band['start']
            if bandwidth_mhz <= 4:
                num_points = 200   # 2m ham (4 MHz) → 200 points = 0.02 MHz spacing
            elif bandwidth_mhz <= 10:
                num_points = 150
            elif bandwidth_mhz <= 30:
                num_points = 100
            else:
                num_points = 80    # 70cm (30 MHz) → 80 points
            
            print("Launching targeted sweep:")
            print("  Band: {}".format(band['name']))
            print("  Range: {:.3f} - {:.3f} MHz".format(band['start'], band['end']))
            print("  Points: {} (high density)".format(num_points))
            
            # Use separate output files so the wide scan isn't clobbered
            self.antenna_scan_process = self.process_manager.start_process(
                'antenna_scanner_targeted',
                ['python3', '/home/tricorder/rpi_lcars-master/rtl_antenna_scan.py',
                 '40',
                 '--freq-min', str(start_freq_hz),
                 '--freq-max', str(end_freq_hz),
                 '--num-points', str(num_points),
                 '--output-prefix', '/tmp/antenna_scan_targeted'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.antenna_scan_active = True
            self.targeted_scan = True
            
            # Enter targeted mode and set fixed frequency range for stable X-axis
            self.antenna_analysis.start_targeted_scan()
            self.antenna_analysis.set_target_range(start_freq_hz, end_freq_hz)
            
            print("Targeted scan started - will take ~{} seconds".format(num_points * 0.2))
            return True

        # --- Everything below here is the existing waterfall / demod path ----
        target_freq = self._get_selected_frequency()
        if target_freq is None:
            print("Please select a target frequency first")
            return True

        # Hide selector views, show waterfall
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.emf_gadget.visible = False

        if not self.waterfall_display.scan_active:
            print("Starting live waterfall at {:.3f} MHz...".format(target_freq / 1e6))
            self.waterfall_display.start_scan(target_freq)
            self.waterfall_display.visible = True
            self.waterfall_display.set_selected_frequency(target_freq)
            self._update_demod_info(target_freq)
        else:
            print("Stopping live scan - waterfall frozen")
            self.waterfall_display.stop_scan()
            self.demodulator.stop_demodulation()

        return True

    def handle_record(self):
        """Handle RECORD button while EMF is active. Returns True if consumed.
        
        When waterfall is active, uses the selected demodulation mode from
        the text display selector to determine what action to take.
        """
        if not self.waterfall_display.visible and not (
                self.spectrum_scan_display.visible and self.spectrum_scan_display.scan_complete):
            return False

        target_freq = None

        if self.waterfall_display.visible:
            if not self.waterfall_display.selected_frequency:
                print("Please select a target frequency first")
                return True
            target_freq = self.waterfall_display.selected_frequency / 1e6

            if self.waterfall_display.scan_active:
                print("Stopping live scan for demodulation...")
                self.waterfall_display.stop_scan()
                sleep(0.5)

        elif self.spectrum_scan_display.visible and self.spectrum_scan_display.scan_complete:
            if not self.spectrum_scan_display.selected_frequency:
                print("Please select a target frequency first")
                return True
            target_freq = self.spectrum_scan_display.selected_frequency / 1e6

        if target_freq is None:
            return False

        target_freq_hz = int(target_freq * 1e6)
        
        # Get selected demodulation mode and call its handler
        if 0 <= self.selected_demod_mode < len(self.demod_modes):
            mode = self.demod_modes[self.selected_demod_mode]
            print("Using demod mode: {}".format(mode['name']))
            mode['handler'](target_freq_hz)
        else:
            # Fallback to FM audio if index is invalid
            self._demod_fm_audio(target_freq_hz)

        return True
    
    def _demod_fm_audio(self, target_freq_hz):
        """FM/AM audio demodulation handler (default mode).
        
        This is the original RECORD behavior - toggle FM/AM demodulation.
        
        Args:
            target_freq_hz: Target frequency in Hz
        """
        filter_width = None
        if self.waterfall_display.visible:
            filter_width = self.waterfall_display.get_filter_width()

        if self.demodulator.is_active():
            # Stop demodulation
            self.demodulator.stop_demodulation()
            self._update_demod_info(target_freq_hz)

            # Restart waterfall if it was paused for demodulation
            if self.waterfall_display.visible and not self.waterfall_display.scan_active:
                print("Restarting live waterfall scan...")
                sleep(0.5)
                restart_freq = (self.waterfall_display.center_frequency
                                if self.waterfall_display.center_frequency
                                else target_freq_hz)
                self.waterfall_display.start_scan(restart_freq)
                print("Live waterfall scan restarted at {:.3f} MHz".format(restart_freq / 1e6))
        else:
            # Start demodulation
            self.demodulator.start_demodulation(target_freq_hz, filter_width)
            self._update_demod_info(target_freq_hz)

            if self.waterfall_display.visible:
                print("Live waterfall paused during demodulation")

    def handle_click(self, event):
        """Handle mouse click while EMF is active. Returns True if consumed."""
        if not self.is_active():
            return False

        # Waterfall click → select frequency
        if self.waterfall_display.visible and self.waterfall_display.rect.collidepoint(event.pos):
            x_rel = event.pos[0] - self.waterfall_display.rect.left
            frequency = self.waterfall_display.get_frequency_from_x(x_rel)
            if frequency:
                self.waterfall_display.set_selected_frequency(frequency)
                self.emf_button.target_frequency = frequency / 1e6
                print("Selected frequency: {:.3f} MHz".format(frequency / 1e6))
                self._update_demod_info(frequency)
            return True

        # Spectrum scan display click → select frequency + update preview
        if self.spectrum_scan_display.visible and self.spectrum_scan_display.rect.collidepoint(event.pos):
            if self.spectrum_scan_display.selected_frequency:
                target_freq = self.spectrum_scan_display.selected_frequency
                self._update_scan_range_preview(target_freq)
                self._update_demod_info(target_freq)
            return True

        # Frequency selector click → select frequency + update preview
        if self.frequency_selector.visible and self.frequency_selector.rect.collidepoint(event.pos):
            if hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
                target_freq = self.frequency_selector.selected_frequency
                self._update_scan_range_preview(target_freq)
                self._update_demod_info(target_freq)
            return True

        # Antenna analysis click → band selection (only after scan is complete)
        if self.antenna_analysis.visible and self.antenna_analysis.scan_complete:
            if self.antenna_analysis.rect.collidepoint(event.pos):
                if self.antenna_analysis.handle_graph_click(*event.pos):
                    # Selection changed — refresh the TextDisplay highlight
                    # to stay in sync with whatever the graph just toggled.
                    self._sync_text_display_selection()
                return True   # click was inside the widget; consume it either way

        return False

    def handle_nav_up(self):
        """Handle UP nav while EMF is active. Returns True if consumed."""
        # Waterfall: increase filter width
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self.waterfall_display.adjust_filter_width(1)
            return True

        # Frequency selector: increase sweep range
        if self.frequency_selector.visible and self.frequency_selector.selected_frequency:
            if self.frequency_selector.adjust_sweep_steps(1):
                self._sync_sweep_range_display()
            return True

        return False

    def handle_nav_down(self):
        """Handle DOWN nav while EMF is active. Returns True if consumed."""
        # Waterfall: decrease filter width
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self.waterfall_display.adjust_filter_width(-1)
            return True

        # Frequency selector: decrease sweep range
        if self.frequency_selector.visible and self.frequency_selector.selected_frequency:
            if self.frequency_selector.adjust_sweep_steps(-1):
                self._sync_sweep_range_display()
            return True

        return False

    def handle_nav_left(self):
        """Handle LEFT nav while EMF is active. Returns True if consumed."""
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self.waterfall_display.adjust_frequency(-1)
            return True
        return False

    def handle_nav_right(self):
        """Handle RIGHT nav while EMF is active. Returns True if consumed."""
        if self.waterfall_display.visible and self.waterfall_display.scan_active:
            self.waterfall_display.adjust_frequency(1)
            return True
        return False

    # Called by satellite tracker jump (from analyzeHandler)
    def start_waterfall_at(self, target_freq):
        """Jump directly to live waterfall at a given frequency (e.g. from satellite tracker)."""
        self.emf_gadget.visible = False
        self.frequency_selector.visible = False
        self.spectrum_scan_display.visible = False
        self.waterfall_display.start_scan(target_freq)
        self.waterfall_display.visible = True
        self.waterfall_display.set_selected_frequency(target_freq)
        self._update_demod_info(target_freq)
        print("Live waterfall started - use RECORD to demodulate")

    # ---------------------------------------------------------------
    # Private: per-frame polling
    # ---------------------------------------------------------------
    
    def _poll_antenna_scan(self):
        """Poll antenna scan subprocess and feed live data to the widget."""
        if not self.antenna_analysis.visible:
            return
        if not self.antenna_scan_active:
            return

        current_time = pygame.time.get_ticks()

        # --- Check if subprocess finished ------------------------------------
        if self.antenna_scan_process:
            poll_result = self.antenna_scan_process.poll()
            if poll_result is not None:
                print("Antenna scan completed with code: {}".format(poll_result))
                self.antenna_scan_active = False
                scan_was_targeted = self.targeted_scan  # Save for later checks
                
                # Reset the flag for the next scan
                self.targeted_scan = False

                # Load resonances (written by the scanner after analysis)
                prefix = "/tmp/antenna_scan_targeted" if scan_was_targeted else "/tmp/antenna_scan"
                try:
                    res_file = prefix + "_resonances.npy"
                    if os.path.exists(res_file):
                        resonances = np.load(res_file, allow_pickle=False)
                        self.antenna_analysis.set_resonances(resonances)
                        print("Loaded {} resonance(s)".format(len(resonances)))
                    else:
                        self.antenna_analysis.set_resonances(np.array([]))
                except (IOError, OSError, ValueError) as e:
                    print("Could not load resonances: {}".format(e))
                    self.antenna_analysis.set_resonances(np.array([]))

                self.antenna_analysis.complete_scan()

                # Scan is done — replace the demod placeholder in the TextDisplay
                # with the list of known bands that the user can now select.
                if not scan_was_targeted:
                    # Only show band list after wide scan completes
                    self._push_band_list()

                # Log metadata
                try:
                    metadata_file = prefix + "_metadata.json"
                    if os.path.exists(metadata_file):
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        print("Antenna scan complete: {} points, {} resonances".format(
                            metadata.get('num_points', 0),
                            metadata.get('num_resonances', 0)))
                except (IOError, OSError, json.JSONDecodeError):
                    pass
                return

        # --- Poll progress data every 200 ms ---------------------------------
        if current_time - self._last_antenna_check > 200:
            self._last_antenna_check = current_time
            self._load_antenna_progress()

    def _load_antenna_progress(self):
        """Load the latest frequency + noise_floor arrays and push to widget."""
        # Use different file paths for wide vs targeted scans
        prefix = "/tmp/antenna_scan_targeted" if self.targeted_scan else "/tmp/antenna_scan"
        
        try:
            frequencies   = np.load(prefix + "_frequencies.npy",    allow_pickle=False)
            noise_floors  = np.load(prefix + "_noise_floors.npy",   allow_pickle=False)

            # Guard against partially-written files (lengths must match)
            if len(frequencies) == 0 or len(frequencies) != len(noise_floors):
                return

            # Only redraw if we actually have new points
            if len(frequencies) == len(self.antenna_analysis.frequencies):
                return

            # CRITICAL: Preserve state during live updates
            was_targeted = self.antenna_analysis.targeted_mode
            was_complete = self.antenna_analysis.scan_complete  # BUG FIX: Preserve completion state
            selected_band = self.antenna_analysis.selected_band
            target_min = self.antenna_analysis.target_freq_min_hz
            target_max = self.antenna_analysis.target_freq_max_hz
            has_baseline = self.antenna_analysis.has_baseline
            baseline_resonances = self.antenna_analysis.baseline_resonances
            tuning_history = self.antenna_analysis.tuning_history
            resonances = self.antenna_analysis.resonances  # BUG FIX: Preserve resonances
            
            self.antenna_analysis.clear()
            
            # Restore state BEFORE calling start_*_scan
            self.antenna_analysis.selected_band = selected_band
            self.antenna_analysis.target_freq_min_hz = target_min
            self.antenna_analysis.target_freq_max_hz = target_max
            self.antenna_analysis.has_baseline = has_baseline
            self.antenna_analysis.baseline_resonances = baseline_resonances
            self.antenna_analysis.tuning_history = tuning_history
            
            # Restore targeted_mode and start appropriate scan type
            # Note: start_*_scan will set scan_complete=False and resonances=[]
            if was_targeted or self.targeted_scan:
                self.antenna_analysis.start_targeted_scan()
            else:
                self.antenna_analysis.start_scan()
            
            # BUG FIX: Restore these AFTER start_*_scan since those methods reset them
            self.antenna_analysis.scan_complete = was_complete
            self.antenna_analysis.resonances = resonances
                
            for freq, nf in zip(frequencies, noise_floors):
                self.antenna_analysis.add_data_point(float(freq), float(nf))

        except (IOError, OSError, FileNotFoundError, ValueError):
            pass

    def _poll_spectrum_scan(self, screen):
        """Poll spectrum scan subprocess, update display, draw animation."""
        if not self.spectrum_scan_display.visible or not self.emf_button.scanning:
            return

        current_time = pygame.time.get_ticks()

        # Check if subprocess finished
        if hasattr(self.emf_button, 'scan_process'):
            poll_result = self.emf_button.scan_process.poll()
            if poll_result is not None:
                print("Scan process completed with code: {}".format(poll_result))
                self.emf_button.scanning = False
                self.emf_gadget.emf_scanning = False
                try:
                    loaded_image = pygame.image.load("/tmp/spectrum.png")
                    scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                    self.emf_button.spectrum_image = scaled_image
                    self.spectrum_scan_display.set_spectrum_image(scaled_image)
                    self.spectrum_scan_display.set_scan_complete(True)
                    print("Scan complete! Click on spectrum to select new target frequency.")
                except (pygame.error, IOError, OSError):
                    pass

        # While still scanning: tick animation and poll progress images
        if self.emf_button.scanning:
            if current_time - self._last_animation_update > 200:
                self._last_animation_update = current_time
                self._scan_animation_frame = (self._scan_animation_frame + 1) % 4

            if current_time - self._last_spectrum_check > 500:
                self._last_spectrum_check = current_time
                try:
                    progress_files = glob.glob("/tmp/spectrum_progress_*.png")
                    if progress_files:
                        # Sort by filename to get latest (spectrum_progress_0001.png, etc.)
                        latest_file = sorted(progress_files)[-1]
                        if latest_file != self._last_spectrum_file:
                            loaded_image = pygame.image.load(latest_file)
                            scaled_image = pygame.transform.scale(loaded_image, self.scan_display_size)
                            self.spectrum_scan_display.set_spectrum_image(scaled_image)
                            self.emf_button.spectrum_image = loaded_image
                            self._last_spectrum_file = latest_file
                            print("Loaded spectrum update: {}".format(latest_file))
                    else:
                        if os.path.exists("/tmp/spectrum.png"):
                            self.emf_button.spectrum_image = pygame.image.load("/tmp/spectrum.png")
                except (pygame.error, IOError, OSError):
                    pass

            self._draw_scanning_animation(screen)

    def _poll_waterfall(self):
        """Poll live waterfall data from subprocess."""
        if not self.waterfall_display.scan_active:
            return

        current_time = pygame.time.get_ticks()
        if current_time - self._last_waterfall_check > 100:
            self._last_waterfall_check = current_time
            try:
                waterfall_data = np.load("/tmp/spectrum_live_waterfall.npy")
                psd_data = np.load("/tmp/spectrum_live_psd.npy")
                frequencies = np.load("/tmp/spectrum_live_frequencies.npy")
                self.waterfall_display.set_data(waterfall_data, psd_data, frequencies)
            except (IOError, OSError):
                pass

    # ---------------------------------------------------------------
    # Band-selection bridge (antenna characterization ↔ TextDisplay)
    # ---------------------------------------------------------------

    def handle_text_display_selection(self, selected_index):
        """Relay a TextDisplay line-click into appropriate action.

        Called by main.py when the user clicks a line in the TextDisplay.
        
        Behavior depends on context:
        - Antenna analysis visible: Select a band
        - Waterfall visible: Select demodulation mode
        """
        # Antenna analysis: band selection
        if self.antenna_analysis.visible and self.antenna_analysis.scan_complete:
            band_names = self.antenna_analysis.get_known_band_names()
            if 0 <= selected_index < len(band_names):
                # Toggle: if the user taps the already-selected line, deselect.
                if self.antenna_analysis.selected_band == selected_index:
                    self.antenna_analysis.set_selected_band(None)
                else:
                    self.antenna_analysis.set_selected_band(selected_index)
            else:
                self.antenna_analysis.set_selected_band(None)
            return
        
        # Waterfall: demod mode selection
        if self.waterfall_display.visible:
            # The text display shows:
            # Line 0: "DEMOD MODE SELECT"
            # Line 1: ""
            # Line 2: "Tap mode for RECORD:"
            # Line 3: ""
            # Line 4+: Mode entries (2 lines each: name + description)
            
            # Calculate which mode was clicked
            # First mode starts at line 4
            if selected_index >= 4:
                # Each mode takes 3 lines (name, description, blank)
                # But we need to map click to mode index
                mode_line_offset = selected_index - 4
                
                # Find which mode this maps to
                line_counter = 0
                for mode_idx, mode in enumerate(self.demod_modes):
                    # Each mode: name line, description line, blank line
                    if line_counter <= mode_line_offset < line_counter + 3:
                        # Clicked on this mode
                        if self.selected_demod_mode != mode_idx:
                            self.selected_demod_mode = mode_idx
                            print("Selected demod mode: {}".format(mode['name']))
                            # Refresh display to show new selection
                            freq = self._get_selected_frequency()
                            if freq:
                                self._update_demod_info(freq)
                        return
                    line_counter += 3
            return

    def _push_band_list(self):
        """Write the known-band names into the TextDisplay.

        The list is intentionally flat (one name per line, index-for-index with
        known_bands) so that the selected_index from TextDisplay can be used
        directly as the band index without any header-offset arithmetic.
        """
        self._set_text(self.antenna_analysis.get_known_band_names())

    def _sync_text_display_selection(self):
        """After a graph click changes the band selection, update the TextDisplay
        highlight to match so the two selection surfaces stay in sync."""
        if self._text_display is None:
            return
        self._text_display.set_selected_index(self.antenna_analysis.selected_band)

    # ---------------------------------------------------------------
    # Private: workflow helpers
    # ---------------------------------------------------------------

    def _get_selected_frequency(self):
        """Get the currently selected frequency from whichever widget has one."""
        if self.spectrum_scan_display.visible and self.spectrum_scan_display.selected_frequency:
            return self.spectrum_scan_display.selected_frequency
        if hasattr(self.frequency_selector, 'selected_frequency') and self.frequency_selector.selected_frequency:
            return self.frequency_selector.selected_frequency
        return None

    def _restore_scan_range(self):
        """Restore the previous scan range on the frequency selector, if available.
        
        Priority order:
        1. Selected band from antenna_analysis (if scan complete and band selected)
        2. Previous spectrum scan range (if available)
        3. No range set (user must select manually)
        """
        # Check if antenna_analysis has a selected band
        if (hasattr(self.antenna_analysis, 'scan_complete') and 
            self.antenna_analysis.scan_complete and
            self.antenna_analysis.selected_band is not None):
            
            selected_band = self.antenna_analysis.get_selected_band()
            if selected_band:
                # Convert band start/end from MHz to Hz
                start_freq = int(selected_band['start'] * 1e6)
                end_freq = int(selected_band['end'] * 1e6)
                
                # Calculate center frequency for the selected band
                center_freq = (start_freq + end_freq) // 2
                
                # Set the target frequency to band center
                self.frequency_selector.set_selected_frequency(center_freq)
                
                # Set scanning range to cover the entire band
                self.frequency_selector.set_scanning_range(start_freq, end_freq)
                
                # Store for later use
                self.current_scan_start_freq = start_freq
                self.current_scan_end_freq = end_freq
                
                print("Pre-configured for {} band: {:.1f}-{:.1f} MHz".format(
                    selected_band['name'],
                    start_freq / 1e6,
                    end_freq / 1e6
                ))
                return
        
        # Fall back to previous scan range if available
        if self.current_scan_start_freq and self.current_scan_end_freq:
            self.frequency_selector.set_scanning_range(
                self.current_scan_start_freq,
                self.current_scan_end_freq
            )

    def _start_spectrum_scan(self):
        """Validate selection and launch the spectrum scan subprocess."""
        target_freq = self._get_selected_frequency()
        if target_freq is None:
            print("Please select a target frequency first")
            return

        # Determine sweep range
        sweep_range = self.frequency_selector.get_sweep_range()
        if sweep_range:
            start_freq, end_freq = sweep_range
        else:
            bandwidth = 10e6
            start_freq = max(int(50e6), int(target_freq - bandwidth / 2))
            end_freq = min(int(2.2e9), int(target_freq + bandwidth / 2))

        self.current_scan_start_freq = start_freq
        self.current_scan_end_freq = end_freq

        print("Starting spectrum scan: {} to {} ({} sweeps)".format(
            self.frequency_selector._format_frequency(start_freq),
            self.frequency_selector._format_frequency(end_freq),
            self.frequency_selector.sweep_steps if hasattr(self.frequency_selector, 'sweep_steps') else '?'
        ))

        # Reset state for new scan
        self.emf_button.scanning = True
        self.emf_gadget.emf_scanning = True
        self._last_spectrum_file = None

        self.frequency_selector.set_scanning_range(start_freq, end_freq)
        self.frequency_selector.visible = True
        self.spectrum_scan_display.visible = True
        self.spectrum_scan_display.set_scan_complete(False)
        self.spectrum_scan_display.clear_selection()
        self.spectrum_scan_display.set_frequency_range(start_freq, end_freq)
        self.spectrum_scan_display.set_spectrum_image(None)

        self.emf_button.scan_process = self.process_manager.start_process(
            'spectrum_scanner',
            ['python3', '/home/tricorder/rpi_lcars-master/rtl_scan_2.py',
             str(start_freq), str(end_freq)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

    def _update_scan_range_preview(self, target_freq):
        """Compute and display the scan range that SCAN would use for a given frequency."""
        bandwidth = 10e6
        start_freq = max(int(50e6), int(target_freq - bandwidth / 2))
        end_freq = min(int(2.2e9), int(target_freq + bandwidth / 2))

        if self.frequency_selector.visible:
            self.frequency_selector.set_selected_frequency(target_freq)
            self.frequency_selector.set_scanning_range(start_freq, end_freq)

        self.current_scan_start_freq = start_freq
        self.current_scan_end_freq = end_freq

        print("Selected {:.3f} MHz - Will scan {:.3f} to {:.3f} MHz".format(
            target_freq / 1e6, start_freq / 1e6, end_freq / 1e6))

    def _sync_sweep_range_display(self):
        """After sweep steps change, update the displayed scanning range."""
        sweep_range = self.frequency_selector.get_sweep_range()
        if sweep_range:
            start_freq, end_freq = sweep_range
            self.frequency_selector.set_scanning_range(start_freq, end_freq)

    def _update_demod_info(self, frequency_hz):
        """Update the side text display with demodulation protocol info.
        
        When waterfall is active, show mode selector with available demodulation modes.
        User can click to select which mode RECORD will activate.
        """
        # If waterfall is visible, show mode selector
        if self.waterfall_display.visible:
            filter_width = self.waterfall_display.get_filter_width()
            
            # Build mode selector display
            lines = []
            lines.append("DEMOD MODE SELECT")
            lines.append("")
            lines.append("Tap mode for RECORD:")
            lines.append("")
            
            # List all available modes
            for i, mode in enumerate(self.demod_modes):
                # Highlight selected mode
                if i == self.selected_demod_mode:
                    lines.append("> {} <".format(mode['name']))
                else:
                    lines.append("  {}".format(mode['name']))
                lines.append("  {}".format(mode['description']))
                lines.append("")
            
            # Show current demod info at bottom
            lines.append("---")
            demod_info = self.demodulator.get_demodulation_info(frequency_hz, filter_width)
            # Skip the header, just show key details
            for line in demod_info[2:]:  # Skip "DEMOD: X MHz" and blank line
                lines.append(line)
            
            self._set_text(lines)
        else:
            # Not in waterfall mode - show standard demod info
            filter_width = None
            self._set_text(self.demodulator.get_demodulation_info(frequency_hz, filter_width))

    # ---------------------------------------------------------------
    # Private: rendering
    # ---------------------------------------------------------------

    def _draw_scanning_animation(self, screen):
        """Draw the animated dots indicator while a spectrum scan is in progress."""
        dots = [".", "..", "...", "....", ".....", "......", ".......", "........", "........."]
        scan_text = "....." + dots[self._scan_animation_frame]

        font = pygame.font.Font("assets/swiss911.ttf", 20)
        text_surface = font.render(scan_text, True, (255, 255, 0))
        text_rect = text_surface.get_rect(center=(607, 155))

        bg_rect = pygame.Rect(
            text_rect.x - 10,
            text_rect.y - 10,
            text_rect.width + 20,
            text_rect.height + 20
        )
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surface.set_alpha(180)
        bg_surface.fill((0, 0, 0))
        screen.blit(bg_surface, bg_rect)
        screen.blit(text_surface, text_rect)

    # ---------------------------------------------------------------
    # TV Band Support (NEW - for over-the-air television)
    # ---------------------------------------------------------------
    
    def get_tv_channel_frequency(self, channel_number):
        """Get frequency information for a specific TV channel.
        
        North American ATSC digital TV channels:
        - VHF Low: Channels 2-6 (54-88 MHz)
        - VHF High: Channels 7-13 (174-216 MHz)
        - UHF: Channels 14-69 (470-806 MHz)
        
        Args:
            channel_number (int): TV channel number (2-69)
            
        Returns:
            dict: {'center': freq_hz, 'lower': freq_hz, 'upper': freq_hz, 'bandwidth': 6e6}
            or None if invalid channel
        """
        # VHF Low (Ch 2-6)
        vhf_low = {
            2: 57e6, 3: 63e6, 4: 69e6, 5: 79e6, 6: 85e6
        }
        
        # VHF High (Ch 7-13)
        vhf_high = {
            7: 177e6, 8: 183e6, 9: 189e6, 10: 195e6,
            11: 201e6, 12: 207e6, 13: 213e6
        }
        
        # Check VHF bands first
        if channel_number in vhf_low:
            center = vhf_low[channel_number]
        elif channel_number in vhf_high:
            center = vhf_high[channel_number]
        # UHF (Ch 14-69)
        elif 14 <= channel_number <= 69:
            center = 470e6 + (channel_number - 14) * 6e6 + 3e6
        else:
            return None
        
        return {
            'center': center,
            'lower': center - 3e6,
            'upper': center + 3e6,
            'bandwidth': 6e6
        }
