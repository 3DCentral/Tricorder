import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget


class LcarsFrequencySelector(LcarsWidget):
    """
    Frequency selector widget with logarithmic scale
    Allows selection of target frequency from 50 MHz to 2.2 GHz (RTL-SDR range)
    """
    
    def __init__(self, pos, size=(640, 144)):
        """
        Initialize frequency selector
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Frequency range (in Hz) - RTL-SDR typical range
        self.freq_min = 50e6  # 50 MHz
        self.freq_max = 2.2e9  # 2.2 GHz
        
        # Selected frequency
        self.selected_frequency = None
        self.selected_x = None
        
        # Scanning range (will be highlighted when scanning)
        self.scanning_range = None  # (start_freq, end_freq) in Hz
        
    def freq_to_x(self, frequency):
        """Convert frequency to X pixel position using log scale
        
        Args:
            frequency: Frequency in Hz
            
        Returns:
            X position in pixels (0 to display_width)
        """
        if frequency <= 0:
            return 0
        
        # Logarithmic mapping
        log_min = np.log10(self.freq_min)
        log_max = np.log10(self.freq_max)
        log_freq = np.log10(frequency)
        
        # Map to 0-1 range
        ratio = (log_freq - log_min) / (log_max - log_min)
        ratio = max(0.0, min(1.0, ratio))
        
        return int(ratio * self.display_width)
    
    def x_to_freq(self, x_pos):
        """Convert X pixel position to frequency using log scale
        
        Args:
            x_pos: X position in pixels
            
        Returns:
            Frequency in Hz
        """
        # Convert to 0-1 ratio
        ratio = float(x_pos) / self.display_width
        ratio = max(0.0, min(1.0, ratio))
        
        # Logarithmic inverse mapping
        log_min = np.log10(self.freq_min)
        log_max = np.log10(self.freq_max)
        log_freq = log_min + ratio * (log_max - log_min)
        
        return 10 ** log_freq
    
    def set_selected_frequency(self, frequency):
        """Set the selected target frequency
        
        Args:
            frequency: Frequency in Hz
        """
        self.selected_frequency = frequency
        self.selected_x = self.freq_to_x(frequency)
    
    def set_scanning_range(self, start_freq, end_freq):
        """Set the range currently being scanned (for highlighting)
        
        Args:
            start_freq: Start frequency in Hz
            end_freq: End frequency in Hz
        """
        self.scanning_range = (start_freq, end_freq)
    
    def clear_scanning_range(self):
        """Clear the scanning range highlight"""
        self.scanning_range = None
    
    def _format_frequency(self, freq_hz):
        """Format frequency for display
        
        Args:
            freq_hz: Frequency in Hz
            
        Returns:
            Formatted string (e.g., "99.5 MHz", "1.2 GHz")
        """
        if freq_hz >= 1e9:
            return "{:.2f} GHz".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            return "{:.1f} MHz".format(freq_hz / 1e6)
        elif freq_hz >= 1e3:
            return "{:.1f} kHz".format(freq_hz / 1e3)
        else:
            return "{:.0f} Hz".format(freq_hz)
    
    def _draw_scale(self, surface):
        """Draw the logarithmic frequency scale"""
        # Draw base line
        y_base = self.display_height - 40
        pygame.draw.line(surface, (255, 255, 0), 
                        (0, y_base), 
                        (self.display_width, y_base), 
                        3)
        
        # Draw major tick marks and labels
        # Frequencies to mark: 50MHz, 100MHz, 500MHz, 1GHz, 2GHz
        major_freqs = [
            50e6, 100e6, 200e6, 500e6,
            1e9, 2e9
        ]
        
        font_small = pygame.font.Font("assets/swiss911.ttf", 20)
        
        for freq in major_freqs:
            if freq < self.freq_min or freq > self.freq_max:
                continue
                
            x = self.freq_to_x(freq)
            
            # Draw tick mark
            pygame.draw.line(surface, (255, 255, 0),
                           (x, y_base - 20),
                           (x, y_base + 20),
                           2)
            
            # Draw label
            label = self._format_frequency(freq)
            text = font_small.render(label, True, (255, 255, 0))
            text_rect = text.get_rect(center=(x, y_base + 25))
            surface.blit(text, text_rect)
        
        # Draw minor tick marks for intermediate frequencies
        minor_freqs = []
        # Add minor ticks between major ones
        for decade_start in [50e6, 100e6, 500e6, 1e9]:
            if decade_start >= 1e9:
                # For GHz range, add 0.2, 0.5, etc.
                for i in [2, 3, 4, 5, 6, 7, 8, 9]:
                    minor_freqs.append(decade_start * i / 10)
            else:
                # For MHz range
                for i in [2, 3, 4, 5, 6, 7, 8, 9]:
                    if decade_start < 100e6:
                        minor_freqs.append(decade_start * i)
                    else:
                        minor_freqs.append(decade_start + i * 100e6)
        
        for freq in minor_freqs:
            if freq < self.freq_min or freq > self.freq_max:
                continue
            
            x = self.freq_to_x(freq)
            pygame.draw.line(surface, (255, 255, 0),
                           (x, y_base - 10),
                           (x, y_base + 10),
                           1)
    
    def _draw_selection_marker(self, surface):
        """Draw triangle marker at selected frequency"""
        if self.selected_x is None:
            return
        
        y_base = self.display_height - 40
        
        # Draw triangle pointing down at selected frequency
        triangle_points = [
            (self.selected_x, y_base - 20),  # Top point
            (self.selected_x - 8, y_base - 35),  # Left
            (self.selected_x + 8, y_base - 35)   # Right
        ]
        pygame.draw.polygon(surface, (255, 255, 0), triangle_points)
        
        # Draw selected frequency label
        if self.selected_frequency:
            font = pygame.font.Font("assets/swiss911.ttf", 18)
            label = self._format_frequency(self.selected_frequency)
            text = font.render(label, True, (255, 255, 0))
            text_rect = text.get_rect(center=(self.selected_x, y_base - 50))
            
            # Background for text
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
    
    def _draw_scanning_highlight(self, surface):
        """Draw highlight showing the range currently being scanned"""
        if self.scanning_range is None:
            return
        
        start_freq, end_freq = self.scanning_range
        x_start = self.freq_to_x(start_freq)
        x_end = self.freq_to_x(end_freq)
        
        y_base = self.display_height - 40
        
        # Draw semi-transparent highlight
        width = x_end - x_start
        if width > 0:
            highlight_rect = pygame.Rect(x_start, y_base - 15, width, 30)
            highlight_surface = pygame.Surface((width, 30))
            highlight_surface.set_alpha(100) 
            highlight_surface.fill((255, 153, 0))  # Orange
            surface.blit(highlight_surface, (x_start, y_base - 15))
    
    
    def update(self, screen):
        """Update and render the frequency selector"""
        if not self.visible:
            return
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        # Draw components
        self._draw_scale(self.image)
        self._draw_scanning_highlight(self.image)
        self._draw_selection_marker(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse click to select frequency"""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                # Convert to widget-relative coordinates
                x_rel = event.pos[0] - self.rect.left
                
                # Get frequency from click position
                frequency = self.x_to_freq(x_rel)
                self.set_selected_frequency(frequency)
                
                print("Selected target frequency: {}".format(self._format_frequency(frequency)))
                return True
        
        return False
