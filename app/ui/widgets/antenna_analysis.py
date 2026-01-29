#!/usr/bin/env python3
"""
antenna_analysis_widget.py - LCARS Antenna Analysis Widget

Displays real-time antenna characterization data during EMF scan.
Shows frequency response curves filling in as the scan progresses.
"""

import pygame
import numpy as np
from ui.widgets.lcars_widgets import LcarsWidget


class LcarsAntennaAnalysis(LcarsWidget):
    """
    LCARS-styled antenna analysis display widget
    
    Shows two real-time graphs:
    1. Normalized sensitivity (0-100%) vs frequency
    2. Raw noise floor (dB) vs frequency
    
    Data fills in progressively as the antenna scan runs.
    """
    
    def __init__(self, pos, size):
        """
        Initialize antenna analysis widget
        
        Args:
            pos: (x, y) position tuple
            size: (width, height) size tuple
        """
        self.size = size
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.rect.topleft = pos
        
        # Call parent constructor AFTER setting image
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        
        # Data storage
        self.frequencies = []  # MHz
        self.sensitivities = []  # 0-100%
        self.noise_floors = []  # dB
        
        # Scan state
        self.scan_active = False
        self.scan_complete = False
        
        # Known frequency bands for highlighting
        self.known_bands = [
            {'name': 'FM Radio', 'start': 88, 'end': 108, 'color': (255, 165, 0), 'alpha': 50},  # Orange
            {'name': 'Air Band', 'start': 118, 'end': 137, 'color': (255, 255, 0), 'alpha': 50},  # Yellow
            {'name': 'Weather', 'start': 137, 'end': 138, 'color': (0, 255, 255), 'alpha': 50},  # Cyan
            {'name': '2m Ham', 'start': 144, 'end': 148, 'color': (255, 0, 255), 'alpha': 50},  # Magenta
            {'name': '70cm', 'start': 420, 'end': 450, 'color': (0, 100, 255), 'alpha': 50},  # Blue
        ]
        
        # LCARS colors
        self.color_yellow = (255, 204, 0)
        self.color_cyan = (0, 255, 255)
        self.color_orange = (255, 165, 0)
        self.color_magenta = (255, 0, 255)
        self.color_red = (255, 0, 0)
        self.color_grid = (100, 100, 0)
        
        # Font
        try:
            self.font_large = pygame.font.Font("assets/swiss911.ttf", 28)
            self.font_medium = pygame.font.Font("assets/swiss911.ttf", 22)
            self.font_small = pygame.font.Font("assets/swiss911.ttf", 16)
        except:
            self.font_large = pygame.font.SysFont('monospace', 28)
            self.font_medium = pygame.font.SysFont('monospace', 22)
            self.font_small = pygame.font.SysFont('monospace', 16)
        
        self._render()
    
    def start_scan(self):
        """Start a new antenna scan"""
        self.scan_active = True
        self.scan_complete = False
        self.frequencies = []
        self.sensitivities = []
        self.noise_floors = []
        self._render()
    
    def add_data_point(self, frequency_mhz, sensitivity, noise_floor):
        """
        Add a new data point from the scan
        
        Args:
            frequency_mhz: Frequency in MHz
            sensitivity: Normalized sensitivity (0-100)
            noise_floor: Raw noise floor in dB
        """
        self.frequencies.append(frequency_mhz)
        self.sensitivities.append(sensitivity)
        self.noise_floors.append(noise_floor)
        self._render()
    
    def complete_scan(self):
        """Mark scan as complete"""
        self.scan_active = False
        self.scan_complete = True
        self._render()
    
    def clear(self):
        """Clear all data"""
        self.scan_active = False
        self.scan_complete = False
        self.frequencies = []
        self.sensitivities = []
        self.noise_floors = []
        self._render()
    
    def _render(self):
        """Render the antenna analysis display"""
        width, height = self.size
        
        # Clear background
        self.image.fill((0, 0, 0))
        
        # Split display into two graphs with more spacing
        graph_height = (height - 80) // 2  # More space between graphs
        
        # Top graph: Normalized Sensitivity
        top_rect = pygame.Rect(40, 30, width - 80, graph_height)
        self._render_sensitivity_graph(top_rect)
        
        # Bottom graph: Raw Noise Floor (with more spacing from top)
        bottom_rect = pygame.Rect(40, graph_height + 70, width - 80, graph_height)
        self._render_noise_floor_graph(bottom_rect)
        
        # Status indicator
        if self.scan_active:
            status_text = "SCANNING... {}/30 POINTS".format(len(self.frequencies))
            status_color = self.color_yellow
        elif self.scan_complete:
            status_text = "SCAN COMPLETE - {} POINTS".format(len(self.frequencies))
            status_color = self.color_cyan
        else:
            status_text = "READY"
            status_color = self.color_orange
        
        status_surf = self.font_small.render(status_text, True, status_color)
        self.image.blit(status_surf, (width - status_surf.get_width() - 10, 5))
    
    def _render_sensitivity_graph(self, rect):
        """Render the normalized sensitivity graph"""
        # Draw title
        title_surf = self.font_medium.render("ANTENNA SENSITIVITY (%)", True, self.color_yellow)
        title_rect = title_surf.get_rect(centerx=rect.centerx, top=rect.top - 25)
        self.image.blit(title_surf, title_rect)
        
        # Draw graph border
        pygame.draw.rect(self.image, self.color_yellow, rect, 2)
        
        # Draw grid
        self._draw_grid(rect, num_h_lines=5, num_v_lines=4)
        
        # Draw frequency band highlights
        self._draw_band_highlights(rect, log_scale=True)
        
        # Draw data
        if len(self.frequencies) >= 2:
            self._draw_curve(rect, self.frequencies, self.sensitivities, 
                           self.color_yellow, y_min=0, y_max=100, log_scale=True, fill=True)
        
        # Draw axes labels
        self._draw_axes_labels(rect, y_label="Sensitivity (%)", y_min=0, y_max=100)
    
    def _render_noise_floor_graph(self, rect):
        """Render the raw noise floor graph"""
        # Draw graph border
        pygame.draw.rect(self.image, self.color_cyan, rect, 2)
        
        # Draw grid
        self._draw_grid(rect, num_h_lines=5, num_v_lines=4, color=self.color_grid)
        
        # Draw frequency band highlights
        self._draw_band_highlights(rect, log_scale=True)
        
        # Draw data
        if len(self.frequencies) >= 2 and self.noise_floors:
            # Auto-scale Y axis based on data
            y_min = min(self.noise_floors) - 5
            y_max = max(self.noise_floors) + 5
            
            self._draw_curve(rect, self.frequencies, self.noise_floors,
                           self.color_cyan, y_min=y_min, y_max=y_max, log_scale=True, fill=False)
            
            # Draw median line
            if self.noise_floors:
                median_nf = np.median(self.noise_floors)
                median_y = self._map_y_to_screen(median_nf, rect, y_min, y_max)
                pygame.draw.line(self.image, self.color_red, 
                               (rect.left, median_y), (rect.right, median_y), 1)
                
                # Label median
                median_text = "Median: {:.1f} dB".format(median_nf)
                median_surf = self.font_small.render(median_text, True, self.color_red)
                self.image.blit(median_surf, (rect.right - median_surf.get_width() - 5, median_y - 15))
        
        # Draw Y-axis labels
        if self.noise_floors:
            y_min = min(self.noise_floors) - 5
            y_max = max(self.noise_floors) + 5
            
            # Y-axis label (rotated)
            y_label_surf = self.font_medium.render("Power (dB)", True, self.color_yellow)
            y_label_rot = pygame.transform.rotate(y_label_surf, 90)
            self.image.blit(y_label_rot, (rect.left - 35, rect.centery - y_label_rot.get_height() // 2))
            
            # Y-axis values (larger font)
            y_max_surf = self.font_small.render("{:.0f}".format(y_max), True, self.color_yellow)
            self.image.blit(y_max_surf, (rect.left - 30, rect.top - 5))
            
            y_min_surf = self.font_small.render("{:.0f}".format(y_min), True, self.color_yellow)
            self.image.blit(y_min_surf, (rect.left - 30, rect.bottom - 10))
        
        # Draw X-axis labels with LARGER font (medium instead of small)
        # X-axis label
        x_label = "Frequency (MHz)"
        x_label_surf = self.font_medium.render(x_label, True, self.color_yellow)
        self.image.blit(x_label_surf, (rect.centerx - x_label_surf.get_width() // 2, rect.bottom + 5))
        
        # X-axis tick marks - match frequency_selector for consistency
        # Major frequencies: 50MHz, 100MHz, 200MHz, 500MHz, 1GHz, 2GHz
        major_freqs = [50, 100, 200, 500, 1000, 2000]  # in MHz
        
        for tick_mhz in major_freqs:
            if tick_mhz < 50 or tick_mhz > 2200:
                continue
            
            x_pos = self._map_freq_to_screen_log(tick_mhz, rect, 50, 2200)
            
            # Format label
            if tick_mhz >= 1000:
                label = "{:.1f}".format(tick_mhz / 1000)  # Show as GHz
            else:
                label = str(tick_mhz)
            
            # Use MEDIUM font for much larger labels
            tick_surf = self.font_medium.render(label, True, self.color_yellow)
            self.image.blit(tick_surf, (x_pos - tick_surf.get_width() // 2, rect.bottom + 30))
        
        # Draw title at BOTTOM of graph
        title_surf = self.font_medium.render("NOISE FLOOR (dB)", True, self.color_cyan)
        title_rect = title_surf.get_rect(centerx=rect.centerx, top=rect.bottom + 60)
        self.image.blit(title_surf, title_rect)
    
    def _draw_grid(self, rect, num_h_lines=5, num_v_lines=4, color=None):
        """Draw grid lines"""
        if color is None:
            color = self.color_grid
        
        # Horizontal lines
        for i in range(num_h_lines + 1):
            y = rect.top + (rect.height * i) // num_h_lines
            pygame.draw.line(self.image, color, (rect.left, y), (rect.right, y), 1)
        
        # Vertical lines (logarithmic spacing)
        for i in range(num_v_lines + 1):
            # Logarithmic position
            log_pos = i / num_v_lines
            x = rect.left + int(rect.width * log_pos)
            pygame.draw.line(self.image, color, (x, rect.top), (x, rect.bottom), 1)
    
    def _draw_band_highlights(self, rect, log_scale=True):
        """Draw colored bands for known frequency ranges"""
        if not self.frequencies:
            return
        
        freq_min = 50  # MHz
        freq_max = 2200  # MHz
        
        for band in self.known_bands:
            if band['start'] < freq_min or band['end'] > freq_max:
                continue
            
            if log_scale:
                # Logarithmic scaling
                x_start = self._map_freq_to_screen_log(band['start'], rect, freq_min, freq_max)
                x_end = self._map_freq_to_screen_log(band['end'], rect, freq_min, freq_max)
            else:
                x_start = self._map_x_to_screen(band['start'], rect, freq_min, freq_max)
                x_end = self._map_x_to_screen(band['end'], rect, freq_min, freq_max)
            
            # Draw semi-transparent band
            band_surface = pygame.Surface((x_end - x_start, rect.height))
            band_surface.set_alpha(band['alpha'])
            band_surface.fill(band['color'])
            self.image.blit(band_surface, (x_start, rect.top))
    
    def _draw_curve(self, rect, x_data, y_data, color, y_min, y_max, log_scale=True, fill=False):
        """Draw a data curve"""
        if len(x_data) < 2:
            return
        
        freq_min = 50  # MHz
        freq_max = 2200  # MHz
        
        points = []
        for freq, value in zip(x_data, y_data):
            if log_scale:
                screen_x = self._map_freq_to_screen_log(freq / 1e6, rect, freq_min, freq_max)
            else:
                screen_x = self._map_x_to_screen(freq / 1e6, rect, freq_min, freq_max)
            
            screen_y = self._map_y_to_screen(value, rect, y_min, y_max)
            points.append((screen_x, screen_y))
        
        # Draw filled area under curve
        if fill and len(points) >= 2:
            # Create polygon for fill - coordinates are already in screen space
            fill_points = [(points[0][0], rect.bottom)] + points + [(points[-1][0], rect.bottom)]
            # Draw directly on main surface with alpha color
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            # Adjust fill points to be relative to the rect
            adjusted_fill_points = [(x - rect.left, y - rect.top) for x, y in fill_points]
            pygame.draw.polygon(s, (*color, 80), adjusted_fill_points)
            self.image.blit(s, rect.topleft)
        
        # Draw line
        if len(points) >= 2:
            pygame.draw.lines(self.image, color, False, points, 2)
        
        # Draw points
        for point in points:
            pygame.draw.circle(self.image, color, point, 3)
    
    def _map_freq_to_screen_log(self, freq_mhz, rect, freq_min, freq_max):
        """Map frequency to screen X coordinate (logarithmic scale)"""
        if freq_mhz <= 0:
            freq_mhz = freq_min
        
        log_freq = np.log10(freq_mhz)
        log_min = np.log10(freq_min)
        log_max = np.log10(freq_max)
        
        normalized = (log_freq - log_min) / (log_max - log_min)
        return int(rect.left + normalized * rect.width)
    
    def _map_x_to_screen(self, x, rect, x_min, x_max):
        """Map X value to screen coordinate (linear scale)"""
        normalized = (x - x_min) / (x_max - x_min)
        return int(rect.left + normalized * rect.width)
    
    def _map_y_to_screen(self, y, rect, y_min, y_max):
        """Map Y value to screen coordinate (inverted for screen coordinates)"""
        normalized = (y - y_min) / (y_max - y_min)
        return int(rect.bottom - normalized * rect.height)
    
    def _draw_axes_labels(self, rect, y_label, y_min, y_max):
        """Draw axis labels with larger fonts"""
        # Y-axis label (rotated)
        y_label_surf = self.font_medium.render(y_label, True, self.color_yellow)
        y_label_rot = pygame.transform.rotate(y_label_surf, 90)
        self.image.blit(y_label_rot, (rect.left - 35, rect.centery - y_label_rot.get_height() // 2))
        
        # Y-axis values (larger font)
        y_max_surf = self.font_small.render("{:.0f}".format(y_max), True, self.color_yellow)
        self.image.blit(y_max_surf, (rect.left - 30, rect.top - 5))
        
        y_min_surf = self.font_small.render("{:.0f}".format(y_min), True, self.color_yellow)
        self.image.blit(y_min_surf, (rect.left - 30, rect.bottom - 10))
        
        # X-axis label
        x_label = "Frequency (MHz)"
        x_label_surf = self.font_small.render(x_label, True, self.color_yellow)
        self.image.blit(x_label_surf, (rect.centerx - x_label_surf.get_width() // 2, rect.bottom + 5))
        
        # X-axis tick marks - match frequency_selector for consistency
        # Major frequencies: 50MHz, 100MHz, 200MHz, 500MHz, 1GHz, 2GHz
        major_freqs = [50, 100, 200, 500, 1000, 2000]  # in MHz
        
        for tick_mhz in major_freqs:
            if tick_mhz < 50 or tick_mhz > 2200:
                continue
            
            x_pos = self._map_freq_to_screen_log(tick_mhz, rect, 50, 2200)
            
            # Format label
            if tick_mhz >= 1000:
                label = "{:.1f}".format(tick_mhz / 1000)  # Show as GHz
            else:
                label = str(tick_mhz)
            
            tick_surf = self.font_small.render(label, True, self.color_yellow)
            self.image.blit(tick_surf, (x_pos - tick_surf.get_width() // 2, rect.bottom + 5))


# Import for colors
from ui import colours
