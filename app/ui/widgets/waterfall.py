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
    
    def _normalize_to_color_range(self, data, vmin=-80, vmax=-20):
        """
        Normalize dB values to 0-255 range for color mapping
        
        Args:
            data: Array of dB values
            vmin: Minimum dB value (maps to 0)
            vmax: Maximum dB value (maps to 255)
        """
        # Clip to range
        normalized = np.clip(data, vmin, vmax)
        # Scale to 0-255
        normalized = ((normalized - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        return normalized
    
    def _draw_waterfall(self, surface):
        """Draw the waterfall spectrogram"""
        if self.waterfall_data is None:
            return
        
        # Get dimensions
        num_lines, num_bins = self.waterfall_data.shape
        
        # Normalize data to color indices
        normalized = self._normalize_to_color_range(self.waterfall_data)
        
        # Create waterfall image
        waterfall_surface = pygame.Surface((num_bins, num_lines))
        
        # Draw each line
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
        
        font = pygame.font.Font("assets/swiss911.ttf", 12)
        
        # Draw min, center, max frequencies
        freq_min = self.frequencies[0] / 1e6  # Convert to MHz
        freq_max = self.frequencies[-1] / 1e6
        freq_center = (freq_min + freq_max) / 2
        
        # Min frequency (left)
        text = font.render("{:.2f} MHz".format(freq_min), True, (255, 153, 0))
        surface.blit(text, (5, self.display_height - 20))
        
        # Center frequency (middle)
        text = font.render("{:.2f} MHz".format(freq_center), True, (255, 153, 0))
        text_rect = text.get_rect(center=(self.display_width // 2, self.display_height - 10))
        surface.blit(text, text_rect)
        
        # Max frequency (right)
        text = font.render("{:.2f} MHz".format(freq_max), True, (255, 153, 0))
        text_rect = text.get_rect(right=self.display_width - 5, top=self.display_height - 20)
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
        self._draw_frequency_labels(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
