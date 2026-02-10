#!/usr/bin/env python3
"""
pager_display.py - LCARS Pager Decoder Display Widget

Displays POCSAG/FLEX pager decoding with:
- Left side: SCOPE oscilloscope output (audio waveform)
- Right side: Scrolling decoded messages

Designed to fit in bottom half of screen below waterfall.
"""

import pygame
import subprocess
import threading
import queue
from ui.widgets.lcars_widgets import LcarsWidget
from ui import colours


class LcarsPagerDisplay(LcarsWidget):
    """
    LCARS-styled pager decoder display with SCOPE and message output.
    
    Layout:
    +------------------+------------------+
    |  SCOPE           |  MESSAGES        |
    |  (oscilloscope)  |  (scrolling)     |
    +------------------+------------------+
    """
    
    def __init__(self, pos, size=(640, 240)):
        """
        Initialize pager display widget
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) - typically (640, 240) for bottom half
        """
        self.size = size
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.rect.topleft = pos
        
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        
        # Split display
        self.scope_width = size[0] // 2  # Left half
        self.msg_width = size[0] // 2    # Right half
        self.height = size[1]
        
        # SCOPE data (waveform points)
        self.scope_data = []
        self.max_scope_points = 100
        
        # Message data (decoded pager messages)
        self.messages = []
        self.max_messages = 10  # Keep last 10 messages
        
        # Message queue for thread-safe updates
        self.message_queue = queue.Queue()
        
        # Colors
        self.scope_color = (0, 255, 0)      # Green oscilloscope
        self.grid_color = (30, 60, 30)       # Dark green grid
        self.message_color = (255, 255, 0)   # Yellow text
        self.border_color = (255, 165, 0)    # Orange border
        
        # Fonts
        try:
            self.font_large = pygame.font.Font("assets/swiss911.ttf", 24)
            self.font_medium = pygame.font.Font("assets/swiss911.ttf", 20)
            self.font_small = pygame.font.Font("assets/swiss911.ttf", 18)
        except:
            self.font_large = pygame.font.SysFont('monospace', 24, bold=True)
            self.font_medium = pygame.font.SysFont('monospace', 20)
            self.font_small = pygame.font.SysFont('monospace', 18)
        
        self.visible = False
        self._render()
    
    def add_scope_data(self, value):
        """
        Add a data point to the oscilloscope display
        
        Args:
            value: Audio amplitude value (-1.0 to 1.0)
        """
        self.scope_data.append(value)
        
        # Keep only recent points
        if len(self.scope_data) > self.max_scope_points:
            self.scope_data.pop(0)
    
    def add_message(self, message_text):
        """
        Add a decoded pager message to the display
        
        Args:
            message_text: Decoded message string
        """
        self.message_queue.put(message_text)
    
    def _process_message_queue(self):
        """Process any pending messages from the queue (thread-safe)"""
        while not self.message_queue.empty():
            try:
                msg = self.message_queue.get_nowait()
                self.messages.append(msg)
                
                # Keep only recent messages
                if len(self.messages) > self.max_messages:
                    self.messages.pop(0)
            except queue.Empty:
                break
    
    def clear(self):
        """Clear all SCOPE data and messages"""
        self.scope_data = []
        self.messages = []
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                break
    
    def _draw_scope(self, surface):
        """Draw the oscilloscope display on left side"""
        # Scope area
        scope_rect = pygame.Rect(0, 0, self.scope_width, self.height)
        
        # Draw background
        pygame.draw.rect(surface, (0, 0, 0), scope_rect)
        
        # Draw grid
        grid_spacing_x = self.scope_width // 10
        grid_spacing_y = self.height // 8
        
        # Vertical grid lines
        for x in range(0, self.scope_width, grid_spacing_x):
            pygame.draw.line(surface, self.grid_color, 
                           (x, 0), (x, self.height), 1)
        
        # Horizontal grid lines
        for y in range(0, self.height, grid_spacing_y):
            pygame.draw.line(surface, self.grid_color,
                           (0, y), (self.scope_width, y), 1)
        
        # Draw center line (0V reference)
        center_y = self.height // 2
        pygame.draw.line(surface, (0, 100, 0),
                        (0, center_y), (self.scope_width, center_y), 2)
        
        # Draw waveform
        if len(self.scope_data) > 1:
            points = []
            for i, value in enumerate(self.scope_data):
                x = int((i / self.max_scope_points) * self.scope_width)
                # Map value from [-1, 1] to [height, 0]
                y = int(center_y - (value * (self.height // 2 - 10)))
                y = max(5, min(self.height - 5, y))  # Clamp to visible area
                points.append((x, y))
            
            if len(points) > 1:
                pygame.draw.lines(surface, self.scope_color, False, points, 2)
        
        # Draw label
        label = self.font_medium.render("SCOPE", True, self.scope_color)
        surface.blit(label, (10, 10))
        
        # Draw border
        pygame.draw.rect(surface, self.border_color, scope_rect, 2)
    
    def _draw_messages(self, surface):
        """Draw decoded messages on right side with text wrapping"""
        # Message area
        msg_rect = pygame.Rect(self.scope_width, 0, self.msg_width, self.height)
        
        # Draw background
        pygame.draw.rect(surface, (0, 0, 0), msg_rect)
        
        # Draw label
        label = self.font_medium.render("MESSAGES", True, self.message_color)
        surface.blit(label, (self.scope_width + 10, 10))
        
        # Draw messages (bottom-up, newest at bottom) with wrapping
        if self.messages:
            y_pos = self.height - 15  # Start from bottom
            line_height = 20
            max_chars = (self.msg_width - 20) // 9  # Characters that fit per line
            
            # Draw messages from newest to oldest (reverse order)
            for message in reversed(self.messages):
                if y_pos < 40:  # Don't overlap with label
                    break
                
                # Wrap long messages into multiple lines
                wrapped_lines = []
                remaining = message
                
                while remaining:
                    if len(remaining) <= max_chars:
                        # Last chunk fits
                        wrapped_lines.append(remaining)
                        break
                    else:
                        # Try to break at a space if possible
                        break_point = max_chars
                        space_pos = remaining.rfind(' ', 0, max_chars)
                        if space_pos > max_chars * 0.7:  # Only break at space if it's not too early
                            break_point = space_pos
                        
                        wrapped_lines.append(remaining[:break_point])
                        remaining = remaining[break_point:].lstrip()
                
                # Draw wrapped lines from bottom to top
                for line_text in reversed(wrapped_lines):
                    if y_pos < 40:  # Stop if we run out of space
                        break
                    
                    # Render message line
                    text = self.font_small.render(line_text, True, self.message_color)
                    surface.blit(text, (self.scope_width + 10, y_pos))
                    
                    y_pos -= line_height
                
                # Add small gap between messages
                y_pos -= 5
        else:
            # Show "waiting" message
            waiting = self.font_small.render("Waiting for pager traffic...", 
                                            True, (128, 128, 0))
            surface.blit(waiting, (self.scope_width + 10, self.height // 2))
        
        # Draw border
        pygame.draw.rect(surface, self.border_color, msg_rect, 2)
    
    def _render(self):
        """Render the complete pager display"""
        if not self.visible:
            return
        
        # Clear surface
        self.image.fill((0, 0, 0))
        
        # Draw both sides
        self._draw_scope(self.image)
        self._draw_messages(self.image)
        
        self.dirty = 1
    
    def update(self, screen):
        """Update and render the pager display"""
        if not self.visible:
            return
        
        # Process any queued messages
        self._process_message_queue()
        
        # Re-render
        self._render()
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle events (none for this widget)"""
        return False


class PagerOutputReader(threading.Thread):
    """
    Background thread to read multimon-ng output and extract decoded messages.
    """
    
    def __init__(self, process, pager_display):
        """
        Initialize output reader
        
        Args:
            process: subprocess.Popen object running multimon-ng
            pager_display: LcarsPagerDisplay widget to update
        """
        threading.Thread.__init__(self)
        self.process = process
        self.pager_display = pager_display
        self.running = True
        self.daemon = True  # Thread dies with main program
    
    def run(self):
        """Read and parse multimon-ng output"""
        try:
            for line in iter(self.process.stdout.readline, b''):
                if not self.running:
                    break
                
                try:
                    text = line.decode('utf-8', errors='ignore').strip()
                    
                    # Parse decoded messages
                    # POCSAG messages start with "POCSAG512:", "POCSAG1200:", etc.
                    # FLEX messages start with "FLEX:"
                    if any(text.startswith(prefix) for prefix in 
                            ['POCSAG512:', 'POCSAG1200:', 'POCSAG2400:', 'FLEX:']):
                        # Add to message display
                        self.pager_display.add_message(text)
                        print(text)  # Also print to console
                
                except Exception as e:
                    print("Error parsing pager output: {}".format(e))
        
        except Exception as e:
            print("Pager output reader error: {}".format(e))
    
    def stop(self):
        """Stop the reader thread"""
        self.running = False


class AudioWaveformReader(threading.Thread):
    """
    Background thread to read raw audio data and generate waveform for oscilloscope.
    Reads from a FIFO pipe that gets the raw audio from rtl_fm.
    """
    
    def __init__(self, fifo_path, pager_display):
        """
        Initialize audio waveform reader
        
        Args:
            fifo_path: Path to named pipe (FIFO) with raw audio data
            pager_display: LcarsPagerDisplay widget to update
        """
        threading.Thread.__init__(self)
        self.fifo_path = fifo_path
        self.pager_display = pager_display
        self.running = True
        self.daemon = True
    
    def run(self):
        """Read raw audio data and generate waveform"""
        import struct
        
        try:
            # Open the FIFO for reading
            # rtl_fm outputs signed 16-bit samples
            with open(self.fifo_path, 'rb') as fifo:
                chunk_size = 220  # Read ~100 samples at a time (220 bytes = 110 samples)
                
                while self.running:
                    try:
                        # Read chunk of audio data
                        data = fifo.read(chunk_size)
                        if not data:
                            break
                        
                        # Parse as signed 16-bit integers
                        sample_count = len(data) // 2
                        samples = struct.unpack('{}h'.format(sample_count), data)
                        
                        # Normalize to -1.0 to 1.0 range
                        # 16-bit signed range: -32768 to 32767
                        for sample in samples:
                            normalized = sample / 32768.0
                            self.pager_display.add_scope_data(normalized)
                    
                    except Exception as e:
                        if self.running:
                            print("Error reading audio data: {}".format(e))
                        break
        
        except Exception as e:
            print("Audio waveform reader error: {}".format(e))
        finally:
            # Clean up FIFO
            try:
                import os
                if os.path.exists(self.fifo_path):
                    os.unlink(self.fifo_path)
            except:
                pass
    
    def stop(self):
        """Stop the reader thread"""
        self.running = False
