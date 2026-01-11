import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget


class LcarsSpectrumScanDisplay(LcarsWidget):
    """
    Interactive spectrum scan display widget for wide-band SDR spectrum visualization
    Shows the result of a sweep scan with ability to click to select target frequency
    """
    
    def __init__(self, pos, size=(640, 336)):
        """
        Initialize spectrum scan display
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area (70% of 480 = 336)
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Spectrum image (loaded from file)
        self.spectrum_image = None
        
        # Frequency range info (set when scan completes)
        self.freq_min = None
        self.freq_max = None
        self.bandwidth = 2.4e6  # Default bandwidth for detailed scan (2.4 MHz)
        
        # Selected target frequency
        self.selected_frequency = None
        self.selected_x = None
        
        # Scanning state
        self.scan_complete = False
        
    def set_frequency_range(self, freq_min, freq_max):
        """
        Set the frequency range for the displayed spectrum
        
        Args:
            freq_min: Minimum frequency in Hz
            freq_max: Maximum frequency in Hz
        """
        self.freq_min = freq_min
        self.freq_max = freq_max
        
    def set_spectrum_image(self, image):
        """
        Set the spectrum scan image
        
        Args:
            image: pygame.Surface with the spectrum plot
        """
        self.spectrum_image = image
        
    def set_scan_complete(self, complete):
        """
        Mark the scan as complete (enables interactive selection)
        
        Args:
            complete: True if scan is complete, False otherwise
        """
        self.scan_complete = complete
        
    def get_frequency_from_x(self, x_pos):
        """
        Convert X pixel position to frequency
        
        Args:
            x_pos: X position relative to widget (0 to display_width)
            
        Returns:
            Frequency in Hz, or None if no frequency data available
        """
        if self.freq_min is None or self.freq_max is None:
            return None
        
        # Account for the plot area (92% of height, leaving 8% for labels at bottom)
        # The actual plot area goes from y=0 to y=0.92*height
        # But x-axis is still full width, so no adjustment needed for x
        
        # Calculate ratio along the display
        ratio = float(x_pos) / self.display_width
        ratio = max(0.0, min(1.0, ratio))
        
        # Linear mapping to frequency range
        frequency = self.freq_min + ratio * (self.freq_max - self.freq_min)
        
        return frequency
    
    def x_from_frequency(self, frequency):
        """
        Convert frequency to X pixel position
        
        Args:
            frequency: Frequency in Hz
            
        Returns:
            X position in pixels (0 to display_width)
        """
        if self.freq_min is None or self.freq_max is None:
            return None
        
        ratio = (frequency - self.freq_min) / (self.freq_max - self.freq_min)
        ratio = max(0.0, min(1.0, ratio))
        return int(ratio * self.display_width)
    
    def set_selected_frequency(self, frequency):
        """
        Set the selected target frequency for detailed analysis
        
        Args:
            frequency: Frequency in Hz
        """
        if self.freq_min is None or self.freq_max is None:
            return
        
        # Clamp to valid range
        frequency = max(self.freq_min, min(self.freq_max, frequency))
        
        self.selected_frequency = frequency
        self.selected_x = self.x_from_frequency(frequency)
    
    def clear_selection(self):
        """Clear the frequency selection"""
        self.selected_frequency = None
        self.selected_x = None
    
    def _format_frequency(self, freq_hz):
        """
        Format frequency for display
        
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
    
    def _draw_spectrum(self, surface):
        """Draw the spectrum image"""
        if self.spectrum_image is None:
            # Draw placeholder
            font = pygame.font.Font("assets/swiss911.ttf", 20)
            text = font.render("SCANNING...", True, (255, 255, 0))
            text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2))
            surface.blit(text, text_rect)
            return
        
        # Scale spectrum image to fit display
        scaled_image = pygame.transform.scale(self.spectrum_image, (self.display_width, self.display_height))
        surface.blit(scaled_image, (0, 0))
    
    def _draw_selection_indicator(self, surface):
        """Draw the bandwidth selection indicator"""
        if self.selected_x is None or self.selected_frequency is None:
            return
        
        if self.bandwidth is None:
            return
        
        # Calculate bandwidth width in pixels
        freq_range = self.freq_max - self.freq_min
        if freq_range <= 0:
            return
        
        bandwidth_pixels = int((self.bandwidth / freq_range) * self.display_width)
        
        # Calculate start and end X positions for bandwidth box
        x_start = max(0, self.selected_x - bandwidth_pixels // 2)
        x_end = min(self.display_width, self.selected_x + bandwidth_pixels // 2)
        
        # Draw semi-transparent bandwidth box
        box_height = self.display_height - 40
        box_surface = pygame.Surface((x_end - x_start, box_height))
        box_surface.set_alpha(80)
        box_surface.fill((255, 255, 0))
        surface.blit(box_surface, (x_start, 0))
        
        # Draw border of bandwidth box
        pygame.draw.rect(surface, (255, 255, 0), 
                        (x_start, 0, x_end - x_start, box_height), 2)
        
        # Draw center line
        pygame.draw.line(surface, (255, 255, 0),
                        (self.selected_x, 0),
                        (self.selected_x, self.display_height - 40),
                        2)
        
        # Draw crosshair at top
        crosshair_y = 20
        pygame.draw.line(surface, (255, 255, 0),
                        (self.selected_x, crosshair_y - 10),
                        (self.selected_x, crosshair_y + 10), 3)
        
        # Draw frequency label with bandwidth info
        font = pygame.font.Font("assets/swiss911.ttf", 18)
        freq_label = "{} ± {:.1f} MHz".format(
            self._format_frequency(self.selected_frequency),
            self.bandwidth / 2e6
        )
        text = font.render(freq_label, True, (255, 255, 0))
        text_rect = text.get_rect(center=(self.selected_x, crosshair_y + 35))
        
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
        """Update and render the spectrum scan display"""
        if not self.visible:
            return
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        # Draw components
        self._draw_spectrum(self.image)
        self._draw_selection_indicator(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse click to select target frequency"""
        if not self.visible:
            self.focussed = False
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.focussed = True
                
                # Only allow selection if scan is complete
                if self.scan_complete:
                    # Convert to widget-relative coordinates
                    x_rel = event.pos[0] - self.rect.left
                    
                    # Get frequency from click position
                    frequency = self.get_frequency_from_x(x_rel)
                    if frequency:
                        self.set_selected_frequency(frequency)
                        print("Selected new target frequency: {} (bandwidth: {:.1f} MHz)".format(
                            self._format_frequency(frequency),
                            self.bandwidth / 1e6
                        ))
                        return True
        
        if event.type == pygame.MOUSEBUTTONUP:
            self.focussed = False
        
        return False 
