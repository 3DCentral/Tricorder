import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget


class LcarsWaterfall(LcarsWidget):
    """
    Waterfall display widget for live SDR spectrum visualization
    Shows a scrolling 2D spectrogram with PSD overlay
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
        
        # Waterfall data
        self.waterfall_data = None
        self.psd_data = None
        self.frequencies = None
        
        # Display parameters
        self.psd_height = 100  # Height reserved for PSD plot at top
        self.waterfall_height = self.display_height - self.psd_height
        
        # Color map for waterfall (blue -> green -> yellow -> red)
        self.colormap = self._generate_colormap()
        
        # Frequency selection
        self.selected_frequency = None
        self.selected_x = None
        
        # Demodulator reference (for bandwidth visualization)
        self.demodulator = None
        
        # NEW: Process management for live scanning
        self.scan_process = None
        self.scan_active = False
        
        # NEW: Bandwidth control
        self.bandwidth_options = [
            200000,   # 200 kHz - Very narrow (single channel)
            500000,   # 500 kHz
            1000000,  # 1 MHz
            1200000,  # 1.2 MHz
            2400000,  # 2.4 MHz - Default RTL-SDR bandwidth
            3200000,  # 3.2 MHz - Maximum for stable operation
        ]
        self.bandwidth_index = 4  # Start at 2.4 MHz (index 4)
        self.current_bandwidth = 2400000  # 2.4 MHz default
        self.center_frequency = None
    
    def stop_scan(self):
        """Stop live waterfall scan"""
        if self.scan_active and self.scan_process:
            self.scan_process.terminate()
            self.scan_process.wait()
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
        
        # Start subprocess
        self.scan_process = subprocess.Popen(
            ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_live.py', 
             str(int(center_freq)), str(int(sample_rate))],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.scan_active = True
        
        print("Live scan started at {:.3f} MHz with {:.1f} MHz bandwidth".format(
            center_freq / 1e6, sample_rate / 1e6))
    
    def adjust_bandwidth(self, direction):
        """Increase (1) or decrease (-1) bandwidth and restart scan
        
        Args:
            direction: 1 for increase, -1 for decrease
        """
        if not self.scan_active:
            return
        
        # Adjust bandwidth index
        self.bandwidth_index += direction
        self.bandwidth_index = max(0, min(len(self.bandwidth_options) - 1, self.bandwidth_index))
        
        # Update bandwidth
        self.current_bandwidth = self.bandwidth_options[self.bandwidth_index]
        
        # Use stored center frequency
        center_freq = self.center_frequency if self.center_frequency else self.selected_frequency
        if not center_freq:
            print("No center frequency set")
            return
        
        # Print status
        print("\n" + "="*60)
        print("WATERFALL BANDWIDTH ADJUSTMENT")
        print("="*60)
        print("New bandwidth: {:.1f} MHz ({:.0f} kHz)".format(
            self.current_bandwidth / 1e6,
            self.current_bandwidth / 1000))
        print("Center frequency: {:.3f} MHz".format(center_freq / 1e6))
        print("Frequency range: {:.3f} - {:.3f} MHz".format(
            (center_freq - self.current_bandwidth/2) / 1e6,
            (center_freq + self.current_bandwidth/2) / 1e6))
        print("="*60 + "\n")
        
        # Restart with new bandwidth
        self.start_scan(center_freq, self.current_bandwidth)
    
    def adjust_frequency(self, direction):
        """Tune frequency up (1) or down (-1) and restart scan
        
        Args:
            direction: 1 for increase, -1 for decrease
        """
        if not self.scan_active:
            return
        
        # Get current center frequency
        center_freq = self.center_frequency if self.center_frequency else self.selected_frequency
        if not center_freq:
            print("No center frequency set")
            return
        
        # Step size is 10% of bandwidth
        freq_step = self.current_bandwidth * 0.1
        center_freq += (direction * freq_step)
        
        # Clamp to SDR range (24 MHz to 1.766 GHz for RTL-SDR)
        center_freq = max(24e6, min(1766e6, center_freq))
        
        # Print status
        print("\n" + "="*60)
        print("WATERFALL FREQUENCY ADJUSTMENT")
        print("="*60)
        print("New center frequency: {:.3f} MHz".format(center_freq / 1e6))
        print("Bandwidth: {:.1f} MHz".format(self.current_bandwidth / 1e6))
        print("Frequency range: {:.3f} - {:.3f} MHz".format(
            (center_freq - self.current_bandwidth/2) / 1e6,
            (center_freq + self.current_bandwidth/2) / 1e6))
        print("="*60 + "\n")
        
        # Restart with new frequency
        self.start_scan(center_freq, self.current_bandwidth)
        
    def _generate_colormap(self, num_colors=256):
        """Generate a color map for waterfall display"""
        colormap = []
        
        # Create gradient: dark blue -> blue -> cyan -> green -> yellow -> red
        for i in range(num_colors):
            ratio = i / float(num_colors - 1)
            
            if ratio < 0.2:
                # Dark blue to blue
                r = 0
                g = 0
                b = int(255 * (ratio / 0.2))
            elif ratio < 0.4:
                # Blue to cyan
                r = 0
                g = int(255 * ((ratio - 0.2) / 0.2))
                b = 255
            elif ratio < 0.6:
                # Cyan to green
                r = 0
                g = 255
                b = int(255 * (1 - (ratio - 0.4) / 0.2))
            elif ratio < 0.8:
                # Green to yellow
                r = int(255 * ((ratio - 0.6) / 0.2))
                g = 255
                b = 0
            else:
                # Yellow to red
                r = 255
                g = int(255 * (1 - (ratio - 0.8) / 0.2))
                b = 0
            
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
    
    def get_frequency_from_x(self, x_pos):
        """Convert X pixel position to frequency
        
        Args:
            x_pos: X position relative to widget (0 to display_width)
            
        Returns:
            Frequency in Hz, or None if no frequency data available
        """
        if self.frequencies is None or len(self.frequencies) == 0:
            return None
        
        # Calculate ratio along the display
        ratio = float(x_pos) / self.display_width
        ratio = max(0.0, min(1.0, ratio))  # Clamp to 0-1
        
        # Map to frequency range
        freq_min = self.frequencies[0]
        freq_max = self.frequencies[-1]
        frequency = freq_min + ratio * (freq_max - freq_min)
        
        return frequency
    
    def set_selected_frequency(self, frequency):
        """Set the selected target frequency
        
        Args:
            frequency: Frequency in Hz
        """
        if self.frequencies is None:
            return
            
        self.selected_frequency = frequency
        
        # Calculate X position for drawing
        freq_min = self.frequencies[0]
        freq_max = self.frequencies[-1]
        ratio = (frequency - freq_min) / (freq_max - freq_min)
        self.selected_x = int(ratio * self.display_width)
    
    def set_demodulator(self, demodulator):
        """Set reference to demodulator for bandwidth visualization
        
        Args:
            demodulator: LcarsDemodulator instance
        """
        self.demodulator = demodulator
    
    def _normalize_to_color_range(self, data, vmin=-70, vmax=40):
        """
        Normalize dB values to 0-255 range for color mapping
        
        Args:
            data: Array of dB values
            vmin: Minimum dB value (maps to 0/blue) - adjusted to actual signal range
            vmax: Maximum dB value (maps to 255/red) - adjusted to actual signal range
        """
        # Clip to range
        normalized = np.clip(data, vmin, vmax)
        # Scale to 0-255
        normalized = ((normalized - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        return normalized
    
    def _draw_waterfall(self, surface):
        """Draw the waterfall spectrogram (newest data at bottom, scrolling down)"""
        if self.waterfall_data is None:
            return
        
        # Get dimensions
        num_lines, num_bins = self.waterfall_data.shape
        
        # Normalize data to color indices
        normalized = self._normalize_to_color_range(self.waterfall_data)
        
        # Create waterfall image
        waterfall_surface = pygame.Surface((num_bins, num_lines))
        
        # Draw each line normally (no flip)
        for line_idx in range(num_lines):
            for bin_idx in range(num_bins):
                color_idx = normalized[line_idx, bin_idx]
                color = self.colormap[color_idx]
                waterfall_surface.set_at((bin_idx, line_idx), color)
        
        # Scale to fit display
        scaled_waterfall = pygame.transform.scale(
            waterfall_surface, 
            (self.display_width, self.waterfall_height)
        )
        
        # Blit to main surface (below PSD area)
        surface.blit(scaled_waterfall, (0, self.psd_height))
    
    def _draw_psd(self, surface):
        """Draw the PSD overlay at the top"""
        if self.psd_data is None:
            return
        
        # Normalize PSD for display
        psd_min = np.min(self.psd_data)
        psd_max = np.max(self.psd_data)
        psd_range = psd_max - psd_min
        
        if psd_range == 0:
            return
        
        # Scale PSD to fit in psd_height
        psd_scaled = ((self.psd_data - psd_min) / psd_range * (self.psd_height - 20)).astype(int)
        
        # Create points for line plot
        num_points = len(self.psd_data)
        points = []
        for i in range(num_points):
            x = int(i * self.display_width / num_points)
            y = int(self.psd_height - 10 - psd_scaled[i])  # Flip Y axis and add margin
            points.append((x, y))
        
        # Draw background for PSD area
        psd_bg = pygame.Surface((self.display_width, self.psd_height))
        psd_bg.fill((0, 0, 0))
        psd_bg.set_alpha(200)
        surface.blit(psd_bg, (0, 0))
        
        # Draw grid lines
        for i in range(5):
            y = int(i * self.psd_height / 4)
            pygame.draw.line(surface, (40, 40, 40), (0, y), (self.display_width, y), 1)
        
        # Draw PSD line
        if len(points) > 1:
            pygame.draw.lines(surface, (255, 255, 0), False, points, 2)
    
    def _draw_frequency_labels(self, surface):
        """Draw frequency labels at bottom"""
        if self.frequencies is None:
            return
        
        font = pygame.font.Font("assets/swiss911.ttf", 24)  # Increased from 12 to 24
        
        # Draw min, center, max frequencies
        freq_min = self.frequencies[0] / 1e6  # Convert to MHz
        freq_max = self.frequencies[-1] / 1e6
        freq_center = (freq_min + freq_max) / 2
        
        # Min frequency (left)
        text = font.render("{:.2f} MHz".format(freq_min), True, (255, 153, 0))
        surface.blit(text, (5, self.display_height - 30))
        
        # Center frequency (middle)
        text = font.render("{:.2f} MHz".format(freq_center), True, (255, 153, 0))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height - 15))
        surface.blit(text, text_rect)
        
        # Max frequency (right)
        text = font.render("{:.2f} MHz".format(freq_max), True, (255, 153, 0))
        text_rect = text.get_rect(right=self.display_width - 5, top=self.display_height - 30)
        surface.blit(text, text_rect)
    
    def _draw_frequency_selector(self, surface):
        """Draw the frequency selection indicator with demodulation bandwidth"""
        if self.selected_x is None or self.selected_frequency is None:
            return
        
        # Get demodulation bandwidth if available
        demod_bandwidth_hz = None
        if self.demodulator and self.frequencies is not None:
            # Get the bandwidth for the selected frequency
            freq_mhz = self.selected_frequency / 1e6
            demod_params = self.demodulator.get_demodulation_params(freq_mhz)
            demod_bandwidth_hz = demod_params.get('bandwidth', None)
        
        # Draw bandwidth rectangle if we have the info
        if demod_bandwidth_hz and self.frequencies is not None:
            freq_min = self.frequencies[0]
            freq_max = self.frequencies[-1]
            freq_range = freq_max - freq_min
            
            # Calculate bandwidth in pixels
            bandwidth_ratio = demod_bandwidth_hz / freq_range
            bandwidth_pixels = int(bandwidth_ratio * self.display_width)
            
            # Calculate left and right edges of bandwidth box
            x_left = max(0, self.selected_x - bandwidth_pixels // 2)
            x_right = min(self.display_width, self.selected_x + bandwidth_pixels // 2)
            box_width = x_right - x_left
            
            # Draw semi-transparent bandwidth box
            box_height = self.display_height - self.psd_height - 40
            if box_width > 0:
                # Create semi-transparent overlay
                bandwidth_surface = pygame.Surface((box_width, box_height))
                bandwidth_surface.set_alpha(60)  # Very transparent
                bandwidth_surface.fill((255, 255, 0))  # Yellow tint
                surface.blit(bandwidth_surface, (x_left, self.psd_height))
                
                # Draw border of bandwidth box
                pygame.draw.rect(surface, (255, 255, 0), 
                               (x_left, self.psd_height, box_width, box_height), 2)
        
        # Draw vertical line at selected frequency (center of bandwidth)
        pygame.draw.line(surface, (255, 255, 0), 
                        (self.selected_x, self.psd_height), 
                        (self.selected_x, self.display_height - 40), 
                        2)
        
        # Draw crosshair at top
        crosshair_y = self.psd_height + 20
        pygame.draw.line(surface, (255, 255, 0),
                        (self.selected_x - 10, crosshair_y),
                        (self.selected_x + 10, crosshair_y), 2)
        pygame.draw.line(surface, (255, 255, 0),
                        (self.selected_x, crosshair_y - 10),
                        (self.selected_x, crosshair_y + 10), 2)
        
        # Draw frequency label with bandwidth info
        font = pygame.font.Font("assets/swiss911.ttf", 20)
        freq_mhz = self.selected_frequency / 1e6
        
        # Include bandwidth in label if available
        if demod_bandwidth_hz:
            if demod_bandwidth_hz >= 1000:
                bw_text = "{:.1f} kHz BW".format(demod_bandwidth_hz / 1000)
            else:
                bw_text = "{:.0f} Hz BW".format(demod_bandwidth_hz)
            label_text = "{:.3f} MHz ({})".format(freq_mhz, bw_text)
        else:
            label_text = "{:.3f} MHz".format(freq_mhz)
        
        text = font.render(label_text, True, (255, 255, 0))
        text_rect = text.get_rect(center=(self.selected_x, crosshair_y + 30))
        
        # Draw background for text
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
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        # Draw components
        self._draw_waterfall(self.image)
        self._draw_psd(self.image)
        self._draw_frequency_selector(self.image)
        self._draw_frequency_labels(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
