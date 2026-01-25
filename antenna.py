#!/usr/bin/env python3
"""
rtl_antenna_gui.py - Pygame GUI for RTL-SDR Antenna Analysis

A simple graphical interface for the antenna analyzer with real-time
visualization of the frequency sweep and results.

Usage:
    python rtl_antenna_gui.py

Features:
    - Real-time frequency sweep visualization
    - Interactive control panel
    - Live progress updates
    - Resonance detection with visual markers
    - Export results and plots

Controls:
    - Click "START SCAN" to begin analysis
    - Adjust parameters with buttons
    - Click "EXPORT" to save results
    - Press ESC to quit

Author: Claude
Date: 2026-01-22
"""

import pygame
import sys
import os
import threading
import time
import numpy as np
from collections import deque

# Import the analyzer
from rtl_antenna_analysis import AntennaAnalyzer


# Color scheme (LCARS-inspired)
COLOR_BG = (0, 0, 0)  # Black background
COLOR_ORANGE = (255, 153, 0)  # LCARS orange
COLOR_BLUE = (153, 153, 255)  # LCARS blue
COLOR_YELLOW = (255, 255, 0)  # Yellow
COLOR_RED = (255, 102, 102)  # Red
COLOR_GREEN = (102, 255, 102)  # Green
COLOR_WHITE = (255, 255, 255)  # White
COLOR_GRAY = (100, 100, 100)  # Gray
COLOR_PANEL = (20, 20, 40)  # Dark panel


class Button:
    """Simple button widget"""
    
    def __init__(self, x, y, width, height, text, color, text_color=COLOR_BG):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.hover = False
        self.enabled = True
        
    def draw(self, surface, font):
        """Draw the button"""
        # Determine color based on state
        if not self.enabled:
            color = COLOR_GRAY
        elif self.hover:
            # Brighten on hover
            color = tuple(min(255, c + 30) for c in self.color)
        else:
            color = self.color
        
        # Draw button background
        pygame.draw.rect(surface, color, self.rect)
        
        # Draw border
        pygame.draw.rect(surface, COLOR_WHITE, self.rect, 2)
        
        # Draw text
        text_surface = font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)
    
    def handle_event(self, event):
        """Handle mouse events"""
        if not self.enabled:
            return False
        
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.hover:
                return True
        
        return False


class AntennaAnalyzerGUI:
    """GUI for antenna analyzer"""
    
    def __init__(self, width=1280, height=800):
        """Initialize GUI"""
        pygame.init()
        
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("RTL-SDR Antenna Analyzer")
        
        # Fonts
        self.font_large = pygame.font.Font(None, 36)
        self.font_medium = pygame.font.Font(None, 24)
        self.font_small = pygame.font.Font(None, 18)
        
        # Layout
        self.graph_rect = pygame.Rect(50, 100, 900, 400)
        self.info_rect = pygame.Rect(980, 100, 280, 680)
        self.control_rect = pygame.Rect(50, 520, 900, 260)
        
        # Buttons
        self.buttons = []
        self._create_buttons()
        
        # Analysis state
        self.analyzer = None
        self.scanning = False
        self.scan_thread = None
        
        # Data for visualization
        self.frequencies = []
        self.noise_floors = []
        self.current_freq = 0
        self.scan_progress = 0.0
        
        # Scan parameters (in MHz)
        self.start_freq = 24
        self.end_freq = 1700
        self.step_freq = 10
        
        # Results
        self.resonances = []
        self.scan_complete = False
        
        # Status messages
        self.status_messages = deque(maxlen=10)
        self.add_status("Ready. Click START SCAN to begin.")
        
        # Clock for frame rate
        self.clock = pygame.time.Clock()
        self.running = True
    
    def _create_buttons(self):
        """Create UI buttons"""
        button_y = 540
        button_height = 50
        button_spacing = 10
        
        # Scan control buttons
        self.btn_start = Button(70, button_y, 200, button_height, 
                               "START SCAN", COLOR_GREEN, COLOR_BG)
        self.buttons.append(self.btn_start)
        
        self.btn_stop = Button(290, button_y, 200, button_height,
                              "STOP", COLOR_RED, COLOR_WHITE)
        self.btn_stop.enabled = False
        self.buttons.append(self.btn_stop)
        
        self.btn_export = Button(510, button_y, 200, button_height,
                                "EXPORT", COLOR_BLUE, COLOR_WHITE)
        self.btn_export.enabled = False
        self.buttons.append(self.btn_export)
        
        # Parameter adjustment buttons
        param_y = button_y + button_height + 20
        
        # Start frequency
        self.btn_start_dec = Button(70, param_y, 80, 40, "-10 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_start_dec)
        
        self.btn_start_inc = Button(160, param_y, 80, 40, "+10 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_start_inc)
        
        # End frequency
        self.btn_end_dec = Button(280, param_y, 80, 40, "-10 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_end_dec)
        
        self.btn_end_inc = Button(370, param_y, 80, 40, "+10 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_end_inc)
        
        # Step size
        self.btn_step_dec = Button(490, param_y, 80, 40, "-1 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_step_dec)
        
        self.btn_step_inc = Button(580, param_y, 80, 40, "+1 MHz", COLOR_ORANGE)
        self.buttons.append(self.btn_step_inc)
        
        # Preset buttons
        preset_y = param_y + 50
        
        self.btn_preset_full = Button(70, preset_y, 150, 40, 
                                      "Full Range", COLOR_BLUE)
        self.buttons.append(self.btn_preset_full)
        
        self.btn_preset_fm = Button(240, preset_y, 150, 40,
                                   "FM (88-108)", COLOR_BLUE)
        self.buttons.append(self.btn_preset_fm)
        
        self.btn_preset_vhf = Button(410, preset_y, 150, 40,
                                    "VHF (140-170)", COLOR_BLUE)
        self.buttons.append(self.btn_preset_vhf)
        
        self.btn_preset_uhf = Button(580, preset_y, 150, 40,
                                    "UHF (400-500)", COLOR_BLUE)
        self.buttons.append(self.btn_preset_uhf)
    
    def add_status(self, message):
        """Add a status message"""
        timestamp = time.strftime("%H:%M:%S")
        self.status_messages.append("[{}] {}".format(timestamp, message))
    
    def start_scan(self):
        """Start antenna scan in background thread"""
        if self.scanning:
            return
        
        # Reset data
        self.frequencies = []
        self.noise_floors = []
        self.resonances = []
        self.scan_complete = False
        self.scan_progress = 0.0
        
        # Create analyzer
        self.analyzer = AntennaAnalyzer(
            start_freq_mhz=self.start_freq,
            end_freq_mhz=self.end_freq,
            step_mhz=self.step_freq,
            num_samples=8192,
            gain='auto'
        )
        
        # Update button states
        self.btn_start.enabled = False
        self.btn_stop.enabled = True
        self.btn_export.enabled = False
        
        # Disable parameter buttons during scan
        self.btn_start_dec.enabled = False
        self.btn_start_inc.enabled = False
        self.btn_end_dec.enabled = False
        self.btn_end_inc.enabled = False
        self.btn_step_dec.enabled = False
        self.btn_step_inc.enabled = False
        self.btn_preset_full.enabled = False
        self.btn_preset_fm.enabled = False
        self.btn_preset_vhf.enabled = False
        self.btn_preset_uhf.enabled = False
        
        self.scanning = True
        self.add_status("Starting scan...")
        
        # Start scan thread
        self.scan_thread = threading.Thread(target=self._scan_worker)
        self.scan_thread.daemon = True
        self.scan_thread.start()
    
    def stop_scan(self):
        """Stop ongoing scan"""
        if not self.scanning:
            return
        
        self.scanning = False
        self.add_status("Stopping scan...")
        
        # Close SDR
        if self.analyzer and hasattr(self.analyzer, 'sdr'):
            try:
                self.analyzer.sdr.close()
            except:
                pass
        
        # Wait for thread to finish
        if self.scan_thread:
            self.scan_thread.join(timeout=2.0)
        
        # Update button states
        self.btn_start.enabled = True
        self.btn_stop.enabled = False
        
        # Re-enable parameter buttons
        self.btn_start_dec.enabled = True
        self.btn_start_inc.enabled = True
        self.btn_end_dec.enabled = True
        self.btn_end_inc.enabled = True
        self.btn_step_dec.enabled = True
        self.btn_step_inc.enabled = True
        self.btn_preset_full.enabled = True
        self.btn_preset_fm.enabled = True
        self.btn_preset_vhf.enabled = True
        self.btn_preset_uhf.enabled = True
        
        self.add_status("Scan stopped.")
    
    def _scan_worker(self):
        """Background thread for scanning"""
        try:
            # Setup SDR
            self.analyzer.setup_sdr()
            self.add_status("SDR initialized.")
            
            # Calculate number of steps
            num_steps = int((self.analyzer.end_freq - self.analyzer.start_freq) / 
                          self.analyzer.step) + 1
            
            self.add_status("Scanning {} frequencies...".format(num_steps))
            
            # Perform sweep
            step_count = 0
            for freq in np.arange(self.analyzer.start_freq, 
                                 self.analyzer.end_freq + self.analyzer.step, 
                                 self.analyzer.step):
                
                if not self.scanning:
                    break
                
                # Set center frequency
                self.analyzer.sdr.center_freq = int(freq)
                time.sleep(0.05)  # Allow SDR to settle
                
                # Read samples
                samples = self.analyzer.sdr.read_samples(self.analyzer.num_samples)
                
                # Compute noise floor
                noise_floor = self.analyzer.compute_noise_floor(samples)
                
                # Store data
                self.frequencies.append(freq)
                self.noise_floors.append(noise_floor)
                
                # Update progress
                self.current_freq = freq
                step_count += 1
                self.scan_progress = step_count / num_steps
                
            if self.scanning:
                # Scan completed successfully
                self.add_status("Scan complete! Analyzing results...")
                
                # Convert to numpy arrays
                self.analyzer.frequencies = np.array(self.frequencies)
                self.analyzer.noise_floors = np.array(self.noise_floors)
                
                # Smooth data
                smoothed = self.analyzer.smooth_data(window_size=5)
                
                # Find resonances
                self.analyzer.find_resonances(smoothed, prominence=2.0, min_distance=10)
                self.resonances = self.analyzer.resonances
                
                # Check harmonics
                self.analyzer.check_harmonics()
                
                self.scan_complete = True
                self.btn_export.enabled = True
                
                if self.resonances:
                    self.add_status("Found {} resonance(s).".format(len(self.resonances)))
                    primary = self.resonances[0]
                    self.add_status("Primary: {:.2f} MHz".format(
                        primary['frequency'] / 1e6))
                else:
                    self.add_status("No clear resonances detected.")
            
        except Exception as e:
            self.add_status("ERROR: {}".format(str(e)))
            import traceback
            traceback.print_exc()
        
        finally:
            # Clean up
            if self.analyzer and hasattr(self.analyzer, 'sdr'):
                try:
                    self.analyzer.sdr.close()
                except:
                    pass
            
            self.scanning = False
            self.btn_start.enabled = True
            self.btn_stop.enabled = False
            
            # Re-enable parameter buttons
            self.btn_start_dec.enabled = True
            self.btn_start_inc.enabled = True
            self.btn_end_dec.enabled = True
            self.btn_end_inc.enabled = True
            self.btn_step_dec.enabled = True
            self.btn_step_inc.enabled = True
            self.btn_preset_full.enabled = True
            self.btn_preset_fm.enabled = True
            self.btn_preset_vhf.enabled = True
            self.btn_preset_uhf.enabled = True
    
    def export_results(self):
        """Export analysis results"""
        if not self.scan_complete or not self.analyzer:
            self.add_status("No scan data to export.")
            return
        
        # Generate timestamp for filenames
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = "antenna_analysis_{}.txt".format(timestamp)
        plot_file = "antenna_response_{}.png".format(timestamp)
        
        self.add_status("Exporting results...")
        
        try:
            # Generate report
            self.analyzer.generate_report(report_file)
            
            # Generate plot
            self.analyzer.plot_results(plot_file)
            
            self.add_status("Exported: {}".format(report_file))
            self.add_status("Exported: {}".format(plot_file))
            
        except Exception as e:
            self.add_status("Export failed: {}".format(str(e)))
    
    def draw_graph(self):
        """Draw the frequency response graph"""
        # Draw graph background
        pygame.draw.rect(self.screen, COLOR_PANEL, self.graph_rect)
        pygame.draw.rect(self.screen, COLOR_GRAY, self.graph_rect, 2)
        
        # Draw title
        title = self.font_medium.render("Antenna Frequency Response", True, COLOR_ORANGE)
        title_rect = title.get_rect(centerx=self.graph_rect.centerx, 
                                    top=self.graph_rect.top - 30)
        self.screen.blit(title, title_rect)
        
        if not self.frequencies:
            # No data yet
            no_data = self.font_small.render("No data - start a scan", True, COLOR_GRAY)
            no_data_rect = no_data.get_rect(center=self.graph_rect.center)
            self.screen.blit(no_data, no_data_rect)
            return
        
        # Convert frequencies to plot coordinates
        freq_array = np.array(self.frequencies)
        noise_array = np.array(self.noise_floors)
        
        # Determine plot range
        freq_min = self.start_freq * 1e6
        freq_max = self.end_freq * 1e6
        
        if len(noise_array) > 0:
            noise_min = np.min(noise_array) - 5
            noise_max = np.max(noise_array) + 5
        else:
            noise_min = -100
            noise_max = -50
        
        # Graph dimensions (with margins)
        graph_x = self.graph_rect.x + 60
        graph_y = self.graph_rect.y + 20
        graph_w = self.graph_rect.width - 80
        graph_h = self.graph_rect.height - 60
        
        # Draw axes
        pygame.draw.line(self.screen, COLOR_WHITE, 
                        (graph_x, graph_y + graph_h),
                        (graph_x + graph_w, graph_y + graph_h), 2)  # X-axis
        pygame.draw.line(self.screen, COLOR_WHITE,
                        (graph_x, graph_y),
                        (graph_x, graph_y + graph_h), 2)  # Y-axis
        
        # Draw grid
        for i in range(5):
            # Horizontal grid lines
            y = graph_y + int(i * graph_h / 4)
            pygame.draw.line(self.screen, COLOR_GRAY,
                           (graph_x, y),
                           (graph_x + graph_w, y), 1)
            
            # Y-axis labels
            noise_val = noise_max - (i * (noise_max - noise_min) / 4)
            label = self.font_small.render("{:.0f} dB".format(noise_val), 
                                          True, COLOR_BLUE)
            self.screen.blit(label, (graph_x - 55, y - 8))
        
        # X-axis labels
        for i in range(6):
            x = graph_x + int(i * graph_w / 5)
            
            # Vertical grid lines
            pygame.draw.line(self.screen, COLOR_GRAY,
                           (x, graph_y),
                           (x, graph_y + graph_h), 1)
            
            # Labels
            freq_val = freq_min + (i * (freq_max - freq_min) / 5)
            label = self.font_small.render("{:.0f}".format(freq_val / 1e6), 
                                          True, COLOR_BLUE)
            label_rect = label.get_rect(centerx=x, top=graph_y + graph_h + 5)
            self.screen.blit(label, label_rect)
        
        # X-axis title
        xlabel = self.font_small.render("Frequency (MHz)", True, COLOR_BLUE)
        xlabel_rect = xlabel.get_rect(centerx=graph_x + graph_w // 2,
                                      top=graph_y + graph_h + 25)
        self.screen.blit(xlabel, xlabel_rect)
        
        # Y-axis title
        ylabel = self.font_small.render("Noise Floor (dB)", True, COLOR_BLUE)
        ylabel = pygame.transform.rotate(ylabel, 90)
        ylabel_rect = ylabel.get_rect(centery=graph_y + graph_h // 2,
                                      right=graph_x - 60)
        self.screen.blit(ylabel, ylabel_rect)
        
        # Plot data
        if len(freq_array) > 1:
            points = []
            for freq, noise in zip(freq_array, noise_array):
                # Convert to plot coordinates
                x = graph_x + int((freq - freq_min) / (freq_max - freq_min) * graph_w)
                y = graph_y + graph_h - int((noise - noise_min) / (noise_max - noise_min) * graph_h)
                points.append((x, y))
            
            # Draw line
            if len(points) > 1:
                pygame.draw.lines(self.screen, COLOR_YELLOW, False, points, 2)
        
        # Draw resonance markers
        for res in self.resonances:
            freq = res['frequency']
            noise = res['noise_floor']
            
            # Convert to plot coordinates
            x = graph_x + int((freq - freq_min) / (freq_max - freq_min) * graph_w)
            y = graph_y + graph_h - int((noise - noise_min) / (noise_max - noise_min) * graph_h)
            
            # Draw vertical line
            pygame.draw.line(self.screen, COLOR_RED,
                           (x, graph_y),
                           (x, graph_y + graph_h), 2)
            
            # Draw marker
            pygame.draw.circle(self.screen, COLOR_RED, (x, y), 5)
            
            # Draw label
            label = self.font_small.render("#{} {:.1f}MHz".format(
                res['index'], freq / 1e6), True, COLOR_RED)
            label_rect = label.get_rect(centerx=x, bottom=y - 10)
            
            # Background for label
            bg_rect = label_rect.inflate(4, 2)
            pygame.draw.rect(self.screen, COLOR_BG, bg_rect)
            
            self.screen.blit(label, label_rect)
        
        # Draw scan progress indicator
        if self.scanning:
            progress_x = graph_x + int(self.scan_progress * graph_w)
            pygame.draw.line(self.screen, COLOR_GREEN,
                           (progress_x, graph_y),
                           (progress_x, graph_y + graph_h), 3)
    
    def draw_info_panel(self):
        """Draw the information panel"""
        # Draw panel background
        pygame.draw.rect(self.screen, COLOR_PANEL, self.info_rect)
        pygame.draw.rect(self.screen, COLOR_GRAY, self.info_rect, 2)
        
        # Title
        title = self.font_medium.render("ANALYSIS INFO", True, COLOR_ORANGE)
        title_rect = title.get_rect(centerx=self.info_rect.centerx,
                                    top=self.info_rect.top + 10)
        self.screen.blit(title, title_rect)
        
        # Content
        y = self.info_rect.top + 50
        line_height = 20
        
        # Parameters
        info_lines = [
            ("PARAMETERS", COLOR_BLUE),
            ("Start: {:.0f} MHz".format(self.start_freq), COLOR_WHITE),
            ("End: {:.0f} MHz".format(self.end_freq), COLOR_WHITE),
            ("Step: {:.0f} MHz".format(self.step_freq), COLOR_WHITE),
            ("", COLOR_WHITE),
        ]
        
        # Progress
        if self.scanning:
            info_lines.extend([
                ("STATUS", COLOR_BLUE),
                ("Scanning...", COLOR_GREEN),
                ("Progress: {:.1f}%".format(self.scan_progress * 100), COLOR_WHITE),
                ("Current: {:.1f} MHz".format(self.current_freq / 1e6), COLOR_WHITE),
                ("", COLOR_WHITE),
            ])
        elif self.scan_complete:
            info_lines.extend([
                ("STATUS", COLOR_BLUE),
                ("Scan complete!", COLOR_GREEN),
                ("", COLOR_WHITE),
            ])
        else:
            info_lines.extend([
                ("STATUS", COLOR_BLUE),
                ("Ready", COLOR_WHITE),
                ("", COLOR_WHITE),
            ])
        
        # Results
        if self.resonances:
            info_lines.append(("RESONANCES", COLOR_BLUE))
            for i, res in enumerate(self.resonances[:5]):  # Show first 5
                info_lines.append(("#{}: {:.2f} MHz".format(
                    res['index'], res['frequency'] / 1e6), COLOR_YELLOW))
                info_lines.append(("  BW: {:.2f} MHz".format(
                    res['bandwidth'] / 1e6), COLOR_WHITE))
                info_lines.append(("  Q: {:.1f}".format(
                    res['q_factor']), COLOR_WHITE))
            
            if len(self.resonances) > 5:
                info_lines.append(("... and {} more".format(
                    len(self.resonances) - 5), COLOR_GRAY))
        
        # Draw lines
        for line_text, color in info_lines:
            text = self.font_small.render(line_text, True, color)
            self.screen.blit(text, (self.info_rect.x + 10, y))
            y += line_height
        
        # Status log at bottom
        y = self.info_rect.bottom - 220
        pygame.draw.line(self.screen, COLOR_GRAY,
                        (self.info_rect.x + 10, y),
                        (self.info_rect.right - 10, y), 1)
        
        y += 10
        log_title = self.font_small.render("STATUS LOG", True, COLOR_BLUE)
        self.screen.blit(log_title, (self.info_rect.x + 10, y))
        y += 25
        
        # Show last messages
        for msg in list(self.status_messages)[-8:]:
            text = self.font_small.render(msg[:35], True, COLOR_WHITE)
            self.screen.blit(text, (self.info_rect.x + 5, y))
            y += 18
    
    def draw_control_panel(self):
        """Draw the control panel"""
        # Draw panel background
        pygame.draw.rect(self.screen, COLOR_PANEL, self.control_rect)
        pygame.draw.rect(self.screen, COLOR_GRAY, self.control_rect, 2)
        
        # Title
        title = self.font_medium.render("CONTROLS", True, COLOR_ORANGE)
        self.screen.blit(title, (self.control_rect.x + 10, 
                                self.control_rect.y - 30))
        
        # Draw all buttons
        for button in self.buttons:
            button.draw(self.screen, self.font_small)
        
        # Labels for parameter buttons
        labels_y = self.control_rect.y + 15
        
        label1 = self.font_small.render("Start Freq", True, COLOR_BLUE)
        self.screen.blit(label1, (90, labels_y))
        
        label2 = self.font_small.render("End Freq", True, COLOR_BLUE)
        self.screen.blit(label2, (300, labels_y))
        
        label3 = self.font_small.render("Step Size", True, COLOR_BLUE)
        self.screen.blit(label3, (510, labels_y))
        
        preset_label = self.font_small.render("Presets:", True, COLOR_BLUE)
        preset_y = labels_y + 110
        self.screen.blit(preset_label, (70, preset_y - 25))
    
    def handle_button_click(self, button):
        """Handle button clicks"""
        if button == self.btn_start:
            self.start_scan()
        
        elif button == self.btn_stop:
            self.stop_scan()
        
        elif button == self.btn_export:
            self.export_results()
        
        # Parameter adjustments
        elif button == self.btn_start_dec:
            self.start_freq = max(24, self.start_freq - 10)
            self.add_status("Start: {:.0f} MHz".format(self.start_freq))
        
        elif button == self.btn_start_inc:
            self.start_freq = min(self.end_freq - 10, self.start_freq + 10)
            self.add_status("Start: {:.0f} MHz".format(self.start_freq))
        
        elif button == self.btn_end_dec:
            self.end_freq = max(self.start_freq + 10, self.end_freq - 10)
            self.add_status("End: {:.0f} MHz".format(self.end_freq))
        
        elif button == self.btn_end_inc:
            self.end_freq = min(1700, self.end_freq + 10)
            self.add_status("End: {:.0f} MHz".format(self.end_freq))
        
        elif button == self.btn_step_dec:
            self.step_freq = max(1, self.step_freq - 1)
            self.add_status("Step: {:.0f} MHz".format(self.step_freq))
        
        elif button == self.btn_step_inc:
            self.step_freq = min(50, self.step_freq + 1)
            self.add_status("Step: {:.0f} MHz".format(self.step_freq))
        
        # Presets
        elif button == self.btn_preset_full:
            self.start_freq = 24
            self.end_freq = 1700
            self.step_freq = 10
            self.add_status("Preset: Full Range")
        
        elif button == self.btn_preset_fm:
            self.start_freq = 88
            self.end_freq = 108
            self.step_freq = 1
            self.add_status("Preset: FM Broadcast")
        
        elif button == self.btn_preset_vhf:
            self.start_freq = 140
            self.end_freq = 170
            self.step_freq = 1
            self.add_status("Preset: VHF")
        
        elif button == self.btn_preset_uhf:
            self.start_freq = 400
            self.end_freq = 500
            self.step_freq = 2
            self.add_status("Preset: UHF")
    
    def run(self):
        """Main event loop"""
        while self.running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                
                # Handle button events
                for button in self.buttons:
                    if button.handle_event(event):
                        self.handle_button_click(button)
            
            # Clear screen
            self.screen.fill(COLOR_BG)
            
            # Draw header
            header = self.font_large.render("RTL-SDR ANTENNA ANALYZER", 
                                           True, COLOR_ORANGE)
            header_rect = header.get_rect(centerx=self.width // 2, top=20)
            self.screen.blit(header, header_rect)
            
            # Draw components
            self.draw_graph()
            self.draw_info_panel()
            self.draw_control_panel()
            
            # Update display
            pygame.display.flip()
            
            # Control frame rate
            self.clock.tick(30)
        
        # Clean up
        if self.scanning:
            self.stop_scan()
        
        pygame.quit()


def main():
    """Main entry point"""
    print("="*70)
    print("RTL-SDR Antenna Analyzer GUI")
    print("="*70)
    print()
    print("Starting graphical interface...")
    print()
    print("Controls:")
    print("  - Click START SCAN to begin analysis")
    print("  - Adjust frequency range with +/- buttons")
    print("  - Use presets for common bands")
    print("  - Click EXPORT to save results")
    print("  - Press ESC to quit")
    print()
    
    # Create and run GUI
    gui = AntennaAnalyzerGUI(width=1280, height=800)
    gui.run()


if __name__ == "__main__":
    main()
