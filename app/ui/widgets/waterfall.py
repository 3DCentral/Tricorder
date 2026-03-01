"""Waterfall display widget with filter width control for fine-tuning frequency selection

CHANGES FROM ORIGINAL:
- Removed bandwidth adjustment (up/down arrows)
- Added filter width control (up/down arrows)
- Filter width affects the visual bandwidth indicator
- Filter width is independent of SDR sample rate
- Band name indicator: shows the current band name in the PSD area header
  (sourced from the central bands.py registry)
"""
import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
from ui.widgets.process_manager import get_process_manager

# Selection indicator color (purple for better visibility over waterfall data)
SELECTION_COLOR = (204, 153, 204)  # LCARS purple


SNAP_CONFIG = {
    # Temporal averaging
    'max_frames_to_average': 150,  # Cap at 150 frames (5 sec @ 30 Hz)
    
    # Signal detection
    'noise_threshold_db': 12,      # Signal must be 12dB above noise floor
    'min_signal_width_bins': 3,    # Ignore spikes < 3 bins wide (~few kHz)
    
    # Signal width classification
    'wide_signal_threshold_khz': 20,  # Use centroid for signals > 20 kHz
    
    # Fallback
    'fallback_rounding_hz': 5000,  # Round to 5 kHz if no signal found
    
    # Visual feedback colors
    'color_manual': (204, 153, 204),      # Purple - exact click
    'color_peak': (100, 255, 100),        # Green - locked onto peak
    'color_centroid': (100, 200, 255),    # Blue - locked onto wide signal
    'color_rounded': (255, 255, 100),     # Yellow - rounded (no signal)
}

class LcarsWaterfall(LcarsWidget):
    """
    Waterfall display widget for live SDR spectrum visualization
    Shows a scrolling 2D spectrogram with PSD overlay
    
    NEW: Filter width control for precise frequency tuning
    NEW: Band name indicator in PSD header area
    """
    
    def __init__(self, pos, size=(640, 480)):
        """
        Initialize waterfall display
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))  # Black background
        
        LcarsWidget.__init__(self, None, pos, size)
        self.process_manager = get_process_manager()
        
        # Waterfall data
        self.waterfall_data = None
        self.psd_data = None
        self.frequencies = None
        
        # Display parameters
        self.psd_height = 100  # Height reserved for PSD plot at top
        self.waterfall_height = self.display_height - self.psd_height
        
        # Color map for waterfall (blue -> green -> yellow -> red)
        self.colormap = self._generate_colormap()
        
        # OPTIMIZATION: Pre-generate colormap as numpy array for fast indexing
        self.colormap_array = np.array(self.colormap, dtype=np.uint8)
        
        # Frequency selection
        self.selected_frequency = None
        self.selected_x = None
        
        # Demodulator reference (for bandwidth visualization)
        self.demodulator = None
        
        # Process management for live scanning
        self.scan_process = None
        self.scan_active = False
        
        # SDR bandwidth (sample rate) - controls what frequencies we see
        self.current_bandwidth = 2400000  # 2.4 MHz default
        self.center_frequency = None
        
        # Filter width control (for demodulation/listening bandwidth)
        # This is separate from SDR bandwidth and controls how wide a frequency
        # range we're trying to tune in to
        self.filter_width_options = [
            5000,      # 5 kHz - Very narrow (NBFM, single channel)
            8000,      # 8 kHz - Narrow
            12000,     # 12 kHz - NBFM standard
            16000,     # 16 kHz - Wider NBFM (DEFAULT - good balance)
            25000,     # 25 kHz - Wide NBFM
            40000,     # 40 kHz - Very wide
            75000,     # 75 kHz - Extra wide
            100000,    # 100 kHz - Wideband
            150000,    # 150 kHz - Very wideband
            200000,    # 200 kHz - WBFM (FM broadcast)
            300000,    # 300 kHz - Ultra wide
            500000,    # 500 kHz - Maximum
        ]
        self.filter_width_index = 3  # Start at 16 kHz (index 3) - better default
        self.filter_width = 16000  # 16 kHz default (wider NBFM for clearer audio)
        
        # OPTIMIZATION: Cache rendered waterfall surface to avoid re-rendering when paused
        self.cached_waterfall_surface = None
        self.data_hash = None  # Track if data has changed
        
        # Signal snapping state
        self.selection_snap_type = None  # 'peak', 'centroid', 'rounded', or None

        # Pre-load font for band label (avoid per-frame font construction)
        try:
            self._font_band_label = pygame.font.Font("assets/swiss911.ttf", 15)
        except Exception:
            self._font_band_label = pygame.font.SysFont('monospace', 15)
    
    def stop_scan(self):
        """Stop the waterfall scan"""
        if self.scan_active:
            self.process_manager.kill_process('waterfall_live')
            self.scan_process = None
            
        self.scan_active = False

    
    def start_scan(self, center_freq, sample_rate=None):
        """Start live waterfall scan at given frequency
        
        Args:
            center_freq: Center frequency in Hz
            sample_rate: Sample rate (bandwidth) in Hz, or None to use current_bandwidth
        """
        import subprocess
        import time
        
        if sample_rate is None:
            sample_rate = self.current_bandwidth
        
        # Stop any existing scan
        self.stop_scan()
        
        # Give SDR time to close
        time.sleep(0.3)
        
        # Store parameters
        self.center_frequency = center_freq
        self.current_bandwidth = sample_rate
        
        # Invalidate cache when starting new scan
        self.cached_waterfall_surface = None
        self.data_hash = None
        
        # Start subprocess
        self.scan_process = self.process_manager.start_process(
            'waterfall_live',
            ['python3', '/home/tricorder/rpi_lcars-master/rtl_scan_live.py', 
             str(int(center_freq)), str(int(sample_rate))],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.scan_active = True
        
        print("Live scan started at {:.3f} MHz with {:.1f} MHz SDR bandwidth".format(
            center_freq / 1e6, sample_rate / 1e6))
        print("Filter width: {:.1f} kHz".format(self.filter_width / 1000))
    
    def adjust_filter_width(self, direction):
        """Increase (1) or decrease (-1) filter width for fine-tuning
        
        This adjusts the listening/demodulation bandwidth without changing
        what frequencies are visible in the waterfall (SDR bandwidth stays same)
        
        Args:
            direction: 1 for increase, -1 for decrease
        """
        self.filter_width_index += direction
        self.filter_width_index = max(0, min(len(self.filter_width_options) - 1, 
                                             self.filter_width_index))
        
        self.filter_width = self.filter_width_options[self.filter_width_index]
        
        print("\n" + "="*60)
        print("FILTER WIDTH ADJUSTMENT")
        print("="*60)
        print("New filter width: {:.1f} kHz".format(self.filter_width / 1000))
        
        if self.selected_frequency:
            print("Selected frequency: {:.3f} MHz".format(self.selected_frequency / 1e6))
            print("Filter range: {:.3f} - {:.3f} MHz".format(
                (self.selected_frequency - self.filter_width/2) / 1e6,
                (self.selected_frequency + self.filter_width/2) / 1e6))
        
        print("\nNOTE: Filter width controls demodulation bandwidth")
        print("      SDR bandwidth ({:.1f} MHz) unchanged".format(
            self.current_bandwidth / 1e6))
        print("="*60 + "\n")
    
    def adjust_frequency(self, direction):
        """Tune frequency up (1) or down (-1) and restart scan
        
        Args:
            direction: 1 for increase, -1 for decrease
        """
        if not self.scan_active:
            return
        
        center_freq = self.center_frequency if self.center_frequency else self.selected_frequency
        if not center_freq:
            print("No center frequency set")
            return
        
        freq_step = self.current_bandwidth * 0.1
        center_freq += (direction * freq_step)
        
        # Clamp to SDR range
        center_freq = max(24e6, min(1766e6, center_freq))
        
        print("\n" + "="*60)
        print("FREQUENCY ADJUSTMENT")
        print("="*60)
        print("New center frequency: {:.3f} MHz".format(center_freq / 1e6))
        print("SDR bandwidth: {:.1f} MHz".format(self.current_bandwidth / 1e6))
        print("Frequency range: {:.3f} - {:.3f} MHz".format(
            (center_freq - self.current_bandwidth/2) / 1e6,
            (center_freq + self.current_bandwidth/2) / 1e6))
        print("="*60 + "\n")
        
        self.start_scan(center_freq, self.current_bandwidth)
    
    def get_filter_width(self):
        """Get current filter width in Hz"""
        return self.filter_width
    
    def _generate_colormap(self, num_colors=256):
        """Generate a color map for waterfall display"""
        colormap = []
        
        for i in range(num_colors):
            ratio = i / float(num_colors - 1)
            
            if ratio < 0.2:
                r = 0; g = 0; b = int(255 * (ratio / 0.2))
            elif ratio < 0.4:
                r = 0; g = int(255 * ((ratio - 0.2) / 0.2)); b = 255
            elif ratio < 0.6:
                r = 0; g = 255; b = int(255 * (1 - (ratio - 0.4) / 0.2))
            elif ratio < 0.8:
                r = int(255 * ((ratio - 0.6) / 0.2)); g = 255; b = 0
            else:
                r = 255; g = int(255 * (1 - (ratio - 0.8) / 0.2)); b = 0
            
            colormap.append((r, g, b))
        
        return colormap
    
    def set_data(self, waterfall_data, psd_data, frequencies):
        """
        Update waterfall data
        
        Args:
            waterfall_data: 2D numpy array (lines, frequencies) - newest line at index 0
            psd_data: 1D numpy array of current PSD
            frequencies: 1D numpy array of frequency values
        """
        self.waterfall_data = waterfall_data
        self.psd_data = psd_data
        self.frequencies = frequencies
        
        new_hash = hash(waterfall_data.tobytes()) if waterfall_data is not None else None
        if new_hash != self.data_hash:
            self.cached_waterfall_surface = None
            self.data_hash = new_hash
    
    def get_frequency_from_x(self, x_pos):
        """Convert X pixel position to frequency"""
        if self.frequencies is None or len(self.frequencies) == 0:
            return None
        
        ratio = float(x_pos) / self.display_width
        ratio = max(0.0, min(1.0, ratio))
        
        freq_min = self.frequencies[0]
        freq_max = self.frequencies[-1]
        frequency = freq_min + ratio * (freq_max - freq_min)
        
        return frequency
    
    def set_selected_frequency(self, frequency, apply_snapping=True):
        """Set the selected target frequency with optional signal-aware snapping"""
        if self.frequencies is None:
            return
        
        if apply_snapping and self.waterfall_data is not None:
            snapped_freq, snap_type = self._find_signal_at_frequency(frequency)
            
            if snap_type:
                self.selection_snap_type = snap_type
                frequency = snapped_freq
                
                if abs(snapped_freq - frequency) > 1000:
                    print("  Snapped from {:.4f} MHz to {:.3f} MHz ({})".format(
                        frequency / 1e6, snapped_freq / 1e6, snap_type))
            else:
                self.selection_snap_type = None
        else:
            self.selection_snap_type = None
        
        self.selected_frequency = frequency
        
        freq_min = self.frequencies[0]
        freq_max = self.frequencies[-1]
        ratio = (frequency - freq_min) / (freq_max - freq_min)
        self.selected_x = int(ratio * self.display_width)
    
    def set_demodulator(self, demodulator):
        """Set reference to demodulator for bandwidth visualization"""
        self.demodulator = demodulator
    
    def _normalize_to_color_range(self, data, vmin=-90, vmax=40):
        """Normalize dB values to 0-255 range for color mapping"""
        normalized = np.clip(data, vmin, vmax)
        normalized = ((normalized - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        return normalized
    
    def _draw_waterfall(self, surface):
        """Draw the waterfall spectrogram using OPTIMIZED numpy operations"""
        if self.waterfall_data is None:
            return
        
        if self.cached_waterfall_surface is not None and not self.scan_active:
            surface.blit(self.cached_waterfall_surface, (0, self.psd_height))
            return
        
        num_lines, num_bins = self.waterfall_data.shape
        
        normalized = self._normalize_to_color_range(self.waterfall_data)
        colored_data = self.colormap_array[normalized]
        
        waterfall_surface = pygame.surfarray.make_surface(
            np.transpose(colored_data, (1, 0, 2))
        )
        
        scaled_waterfall = pygame.transform.scale(
            waterfall_surface, 
            (self.display_width, self.waterfall_height)
        )
        
        if not self.scan_active:
            self.cached_waterfall_surface = scaled_waterfall
        
        surface.blit(scaled_waterfall, (0, self.psd_height))
    
    def _draw_psd(self, surface):
        """Draw the PSD overlay at the top"""
        if self.psd_data is None:
            return
        
        psd_min = np.min(self.psd_data)
        psd_max = np.max(self.psd_data)
        psd_range = psd_max - psd_min
        
        if psd_range == 0:
            return
        
        psd_scaled = ((self.psd_data - psd_min) / psd_range * (self.psd_height - 20)).astype(int)
        
        num_points = len(self.psd_data)
        points = []
        for i in range(num_points):
            x = int(i * self.display_width / num_points)
            y = int(self.psd_height - 10 - psd_scaled[i])
            points.append((x, y))
        
        psd_bg = pygame.Surface((self.display_width, self.psd_height))
        psd_bg.fill((0, 0, 0))
        psd_bg.set_alpha(200)
        surface.blit(psd_bg, (0, 0))
        
        for i in range(5):
            y = int(i * self.psd_height / 4)
            pygame.draw.line(surface, (40, 40, 40), (0, y), (self.display_width, y), 1)
        
        if len(points) > 1:
            pygame.draw.lines(surface, (255, 255, 0), False, points, 2)

    def _get_visible_bands(self):
        """
        Return a list of band dicts that overlap the current visible frequency
        window.  Handles three cases:

        1. Normal: one band covers (most of) the window.
        2. Border: the window straddles two (or more) adjacent bands.
        3. Point allocation: a band whose start == end (e.g. ADS-B at 1090 MHz)
           is included if it falls inside the window.

        Uses self.frequencies[] if available, otherwise falls back to
        center_frequency ± current_bandwidth/2.

        Returns:
            list of band dicts (may be empty), ordered by start frequency.
        """
        from bands import BANDS

        if self.frequencies is not None and len(self.frequencies) >= 2:
            freq_min_hz = self.frequencies[0]
            freq_max_hz = self.frequencies[-1]
        elif self.center_frequency is not None:
            freq_min_hz = self.center_frequency - self.current_bandwidth / 2
            freq_max_hz = self.center_frequency + self.current_bandwidth / 2
        else:
            return []

        freq_min_mhz = freq_min_hz / 1e6
        freq_max_mhz = freq_max_hz / 1e6

        visible = []
        for band in BANDS:
            # Point allocation: include if it falls inside the window
            if band['start'] == band['end']:
                if freq_min_mhz <= band['start'] <= freq_max_mhz:
                    visible.append(band)
            else:
                # Overlap test: band and window must share at least one point
                if band['start'] <= freq_max_mhz and band['end'] >= freq_min_mhz:
                    visible.append(band)

        return visible

    def _draw_band_header(self, surface):
        """
        Draw a yellow band-name row at the very top of the display (y=0),
        above the PSD graph.

        - Single band visible  → "FM Broadcast Radio"
        - Two bands visible    → "FM Broadcast Radio  |  Aviation Band"
        - Point allocation     → "ADS-B Aircraft Tracking  (1090 MHz)"
        - No band              → nothing drawn
        """
        bands = self._get_visible_bands()
        if not bands:
            return

        parts = []
        for band in bands:
            if band['start'] == band['end']:
                # Point allocation — show the exact frequency
                parts.append("{} ({:.0f} MHz)".format(
                    band['full_name'], band['start']))
            else:
                parts.append(band['full_name'])

        label = "  |  ".join(parts)

        text = self._font_band_label.render(label, True, (255, 255, 0))
        # Centre horizontally, sit right at y=2
        text_rect = text.get_rect(centerx=self.display_width // 2, top=2)

        # Thin black backing for legibility over the graph background
        padding = 3
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + padding * 2,
            text_rect.height + padding * 2,
        )
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surf.set_alpha(160)
        bg_surf.fill((0, 0, 0))
        surface.blit(bg_surf, bg_rect)
        surface.blit(text, text_rect)

    def _draw_frequency_labels(self, surface):
        """Draw frequency labels at bottom"""
        if self.frequencies is None:
            return
        
        font = pygame.font.Font("assets/swiss911.ttf", 24)
        
        freq_min = self.frequencies[0] / 1e6
        freq_max = self.frequencies[-1] / 1e6
        freq_center = (freq_min + freq_max) / 2
        
        text = font.render("{:.2f} MHz".format(freq_min), True, (255, 153, 0))
        surface.blit(text, (5, self.display_height - 30))
        
        text = font.render("{:.2f} MHz".format(freq_center), True, (255, 153, 0))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height - 15))
        surface.blit(text, text_rect)
        
        text = font.render("{:.2f} MHz".format(freq_max), True, (255, 153, 0))
        text_rect = text.get_rect(right=self.display_width - 5, top=self.display_height - 30)
        surface.blit(text, text_rect)
    
    def _draw_frequency_selector(self, surface):
        """Draw the frequency selection indicator with signal-aware color"""
        if self.selected_x is None or self.selected_frequency is None:
            return
        
        if self.selection_snap_type == 'peak':
            color = SNAP_CONFIG['color_peak']
        elif self.selection_snap_type == 'centroid':
            color = SNAP_CONFIG['color_centroid']
        elif self.selection_snap_type == 'rounded':
            color = SNAP_CONFIG['color_rounded']
        else:
            color = SNAP_CONFIG['color_manual']
        
        filter_bandwidth_hz = self.filter_width
        
        if filter_bandwidth_hz and self.frequencies is not None:
            freq_min = self.frequencies[0]
            freq_max = self.frequencies[-1]
            freq_range = freq_max - freq_min
            
            bandwidth_ratio = filter_bandwidth_hz / freq_range
            bandwidth_pixels = int(bandwidth_ratio * self.display_width)
            
            x_left = max(0, self.selected_x - bandwidth_pixels // 2)
            x_right = min(self.display_width, self.selected_x + bandwidth_pixels // 2)
            box_width = x_right - x_left
            
            box_height = self.display_height - self.psd_height - 40
            if box_width > 0:
                bandwidth_surface = pygame.Surface((box_width, box_height))
                bandwidth_surface.set_alpha(60)
                bandwidth_surface.fill(color)
                surface.blit(bandwidth_surface, (x_left, self.psd_height))
                
                pygame.draw.rect(surface, color, 
                               (x_left, self.psd_height, box_width, box_height), 2)
        
        pygame.draw.line(surface, color, 
                        (self.selected_x, 0),
                        (self.selected_x, self.display_height - 40), 
                        3)
        
        crosshair_y = self.psd_height + 20
        pygame.draw.line(surface, color,
                        (self.selected_x - 10, crosshair_y),
                        (self.selected_x + 10, crosshair_y), 2)
        pygame.draw.line(surface, color,
                        (self.selected_x, crosshair_y - 10),
                        (self.selected_x, crosshair_y + 10), 2)
        
        font = pygame.font.Font("assets/swiss911.ttf", 20)
        freq_mhz = self.selected_frequency / 1e6
        
        if filter_bandwidth_hz >= 1000:
            bw_text = "{:.1f} kHz".format(filter_bandwidth_hz / 1000)
        else:
            bw_text = "{:.0f} Hz".format(filter_bandwidth_hz)
        
        if self.selection_snap_type == 'peak':
            snap_indicator = " ."
        elif self.selection_snap_type == 'centroid':
            snap_indicator = " O"
        elif self.selection_snap_type == 'rounded':
            snap_indicator = " ~"
        else:
            snap_indicator = ""
        
        # Also append band short name next to the frequency label
        from bands import get_band_for_freq_hz
        band = get_band_for_freq_hz(self.selected_frequency)
        band_tag = "  [{}]".format(band['name']) if band else ""

        label_text = "{:.3f} MHz ({}){}{} ".format(
            freq_mhz, bw_text, snap_indicator, band_tag)
        
        text = font.render(label_text, True, color)
        text_rect = text.get_rect(center=(self.selected_x, crosshair_y + 30))
        
        padding = 5
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + padding * 2,
            text_rect.height + padding * 2
        )
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surface.set_alpha(200)
        bg_surface.fill((0, 0, 0))
        surface.blit(bg_surface, bg_rect)
        surface.blit(text, text_rect)

    
    def update(self, screen):
        """Update and render the waterfall display"""
        if not self.visible:
            return
        
        needs_redraw = self.scan_active or self.cached_waterfall_surface is None
        
        if needs_redraw:
            self.image.fill((0, 0, 0))
            
            self._draw_waterfall(self.image)
            self._draw_psd(self.image)
            self._draw_band_header(self.image)      # band name(s) above PSD
            self._draw_frequency_selector(self.image)
            self._draw_frequency_labels(self.image)
        
        screen.blit(self.image, self.rect)
        self.dirty = 0
        
    def _compute_noise_floor(self, psd_data):
        """Compute noise floor across entire spectrum"""
        return np.median(psd_data)

    def _find_local_peaks(self, signal_1d, threshold_db):
        """Find local maxima in 1D signal that exceed threshold"""
        peaks = []
        
        for i in range(1, len(signal_1d) - 1):
            if (signal_1d[i] > threshold_db and 
                signal_1d[i] > signal_1d[i-1] and 
                signal_1d[i] > signal_1d[i+1]):
                peaks.append(i)
        
        peaks.sort(key=lambda idx: signal_1d[idx], reverse=True)
        return peaks

    def _measure_signal_width(self, signal_1d, peak_idx, db_drop=3.0):
        """Measure signal width at -3dB points"""
        peak_value = signal_1d[peak_idx]
        threshold = peak_value - db_drop
        
        left_idx = peak_idx
        while left_idx > 0 and signal_1d[left_idx] > threshold:
            left_idx -= 1
        
        right_idx = peak_idx
        while right_idx < len(signal_1d) - 1 and signal_1d[right_idx] > threshold:
            right_idx += 1
        
        return right_idx - left_idx

    def _compute_signal_centroid(self, signal_1d, frequencies_1d, threshold_db):
        """Compute center of mass of signal energy"""
        power_linear = 10 ** (signal_1d / 10.0)
        
        mask = signal_1d > threshold_db
        if not np.any(mask):
            return None
        
        numerator = np.sum(frequencies_1d[mask] * power_linear[mask])
        denominator = np.sum(power_linear[mask])
        
        if denominator == 0:
            return None
        
        return numerator / denominator

    def _find_signal_at_frequency(self, clicked_freq):
        """
        Find actual signal near clicked frequency using waterfall data
        
        Returns:
            tuple: (snapped_freq_hz, snap_type)
        """
        if self.waterfall_data is None or self.frequencies is None:
            return clicked_freq, None
        
        window_width = self.filter_width / 2
        search_min = max(self.frequencies[0], clicked_freq - window_width)
        search_max = min(self.frequencies[-1], clicked_freq + window_width)
        
        freq_mask = (self.frequencies >= search_min) & (self.frequencies <= search_max)
        freq_indices = np.where(freq_mask)[0]
        
        if len(freq_indices) < 3:
            rounded_freq = round(clicked_freq / SNAP_CONFIG['fallback_rounding_hz']) * SNAP_CONFIG['fallback_rounding_hz']
            return rounded_freq, 'rounded'
        
        search_freqs = self.frequencies[freq_indices]
        
        num_frames = min(len(self.waterfall_data), SNAP_CONFIG['max_frames_to_average'])
        waterfall_window = self.waterfall_data[:num_frames, freq_indices]
        
        max_psd = np.max(waterfall_window, axis=0)
        
        if len(max_psd) >= 3:
            smoothed_psd = np.convolve(max_psd, np.ones(3)/3, mode='same')
            averaged_psd = smoothed_psd
        else:
            averaged_psd = max_psd
        
        noise_floor = self._compute_noise_floor(self.waterfall_data[:num_frames])
        peak_threshold = noise_floor + SNAP_CONFIG['noise_threshold_db']
        
        peaks = self._find_local_peaks(averaged_psd, peak_threshold)
        
        if not peaks:
            rounded_freq = round(clicked_freq / SNAP_CONFIG['fallback_rounding_hz']) * SNAP_CONFIG['fallback_rounding_hz']
            return rounded_freq, 'rounded'
        
        valid_peaks = []
        for peak_idx in peaks:
            width = self._measure_signal_width(averaged_psd, peak_idx, db_drop=3.0)
            if width >= SNAP_CONFIG['min_signal_width_bins']:
                valid_peaks.append((peak_idx, width))
        
        if not valid_peaks:
            rounded_freq = round(clicked_freq / SNAP_CONFIG['fallback_rounding_hz']) * SNAP_CONFIG['fallback_rounding_hz']
            return rounded_freq, 'rounded'
        
        clicked_idx = np.argmin(np.abs(search_freqs - clicked_freq))
        closest_peak = min(valid_peaks, key=lambda p: abs(p[0] - clicked_idx))
        peak_idx, signal_width = closest_peak
        
        freq_bin_width = search_freqs[1] - search_freqs[0] if len(search_freqs) > 1 else 1000
        signal_width_hz = signal_width * freq_bin_width
        
        if signal_width_hz > SNAP_CONFIG['wide_signal_threshold_khz'] * 1000:
            centroid_freq = self._compute_signal_centroid(
                averaged_psd, search_freqs, peak_threshold
            )
            
            if centroid_freq:
                print("Signal lock: CENTROID at {:.3f} MHz (width: {:.1f} kHz)".format(
                    centroid_freq / 1e6, signal_width_hz / 1000))
                return centroid_freq, 'centroid'
        
        peak_freq = search_freqs[peak_idx]
        print("Signal lock: PEAK at {:.3f} MHz (width: {:.1f} kHz, strength: {:.1f} dB)".format(
            peak_freq / 1e6, signal_width_hz / 1000, 
            averaged_psd[peak_idx] - noise_floor))
        
        return peak_freq, 'peak'
