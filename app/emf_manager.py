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
                 demodulator, process_manager, text_display_callback):
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

        # Scan display dimensions
        self.scan_display_size = (640, 336)

        # Antenna scan state
        self.antenna_scan_active = False
        self.antenna_scan_process = None
        self._last_antenna_check = 0

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

            self._restore_scan_range()
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
        """Handle RECORD button while EMF is active. Returns True if consumed."""
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
        filter_width = None
        if self.waterfall_display.visible:
            filter_width = self.waterfall_display.get_filter_width()

        if self.demodulator.is_active():
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
            self.demodulator.start_demodulation(target_freq_hz, filter_width)
            self._update_demod_info(target_freq_hz)

            if self.waterfall_display.visible:
                print("Live waterfall paused during demodulation")

        return True

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
        if not self.antenna_analysis.visible or not self.antenna_scan_active:
            return

        current_time = pygame.time.get_ticks()

        # --- Check if subprocess finished ------------------------------------
        if self.antenna_scan_process:
            poll_result = self.antenna_scan_process.poll()
            if poll_result is not None:
                print("Antenna scan completed with code: {}".format(poll_result))
                self.antenna_scan_active = False

                # Load final data one last time to make sure we have everything
                self._load_antenna_progress()

                # Load resonances (written by the scanner after analysis)
                try:
                    res_file = "/tmp/antenna_scan_resonances.npy"
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

                # Log metadata
                try:
                    metadata_file = "/tmp/antenna_scan_metadata.json"
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
        try:
            frequencies   = np.load("/tmp/antenna_scan_frequencies.npy",    allow_pickle=False)
            noise_floors  = np.load("/tmp/antenna_scan_noise_floors.npy",   allow_pickle=False)

            # Guard against partially-written files (lengths must match)
            if len(frequencies) == 0 or len(frequencies) != len(noise_floors):
                return

            # Only redraw if we actually have new points
            if len(frequencies) == len(self.antenna_analysis.frequencies):
                return

            self.antenna_analysis.clear()
            self.antenna_analysis.start_scan()
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
        """Restore the previous scan range on the frequency selector, if available."""
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
        """Update the side text display with demodulation protocol info."""
        filter_width = None
        if self.waterfall_display.visible:
            filter_width = self.waterfall_display.get_filter_width()
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
