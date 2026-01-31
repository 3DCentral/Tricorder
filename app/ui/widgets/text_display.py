import pygame
from pygame.font import Font
from ui.widgets.sprite import LcarsWidget
from ui import colours


class LcarsTextDisplay(LcarsWidget):
    """
    Scrollable text display widget for console output, file lists, and other text-based content
    
    Features:
    - Scrollable text lines
    - Highlighted/selected line
    - Auto-scroll to selection
    - Customizable colors and font size
    """
    
    def __init__(self, pos, size=(640, 480), font_size=20, bg_color=(0, 0, 0)):
        """
        Initialize text display
        
        Args:
            pos: (x, y) position on screen
            size: (width, height) of display area
            font_size: Font size for text (default 16)
            bg_color: Background color RGB tuple (default black)
        """
        self.display_width = size[0]
        self.display_height = size[1]
        self.bg_color = bg_color
        
        self.image = pygame.Surface(size)
        self.image.fill(self.bg_color)
        
        LcarsWidget.__init__(self, None, pos, size)
        
        # Text settings
        self.font_size = font_size
        self.font = Font("assets/swiss911.ttf", self.font_size)
        self.line_height = self.font_size + 4  # Add some padding
        
        # Text content
        self.lines = []  # List of text lines to display
        self.selected_index = None  # Index of selected/highlighted line
        
        # Scroll position
        self.scroll_offset = 0  # Number of lines scrolled from top
        self.max_visible_lines = int(self.display_height / self.line_height)
        
        # Colors
        self.text_color = (255, 255, 0)  # Yellow
        self.selected_color = (255, 255, 255)  # White
        self.selected_bg_color = (100, 100, 150)  # Blue-ish highlight
        self.border_color = (255, 255, 0)  # Bright yellow border
        
    def set_lines(self, lines):
        """
        Set the text lines to display
        
        Args:
            lines: List of strings, one per line
        """
        self.lines = lines if lines else []
        self._clamp_scroll()
        
    def add_line(self, line):
        """
        Add a single line to the end of the display
        
        Args:
            line: String to add
        """
        self.lines.append(line)
        
    def clear(self):
        """Clear all lines"""
        self.lines = []
        self.selected_index = None
        self.scroll_offset = 0
        
    def set_selected_index(self, index):
        """
        Set the selected/highlighted line index
        
        Args:
            index: Index of line to select (0-based), or None for no selection
        """
        if index is None:
            self.selected_index = None
            return
            
        if 0 <= index < len(self.lines):
            self.selected_index = index
            self._scroll_to_selection()
        
    def scroll_to_top(self):
        """Scroll to the top of the list"""
        self.scroll_offset = 0
        
    def scroll_to_bottom(self):
        """Scroll to the bottom of the list"""
        if len(self.lines) > self.max_visible_lines:
            self.scroll_offset = len(self.lines) - self.max_visible_lines
        else:
            self.scroll_offset = 0
            
    def scroll_up(self, lines=1):
        """Scroll up by specified number of lines"""
        self.scroll_offset = max(0, self.scroll_offset - lines)
        
    def scroll_down(self, lines=1):
        """Scroll down by specified number of lines"""
        max_scroll = max(0, len(self.lines) - self.max_visible_lines)
        self.scroll_offset = min(max_scroll, self.scroll_offset + lines)
        
    def _scroll_to_selection(self):
        """Auto-scroll to keep selected line visible"""
        if self.selected_index is None:
            return
            
        # If selected line is above visible area, scroll up
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
            
        # If selected line is below visible area, scroll down
        elif self.selected_index >= self.scroll_offset + self.max_visible_lines:
            self.scroll_offset = self.selected_index - self.max_visible_lines + 1
            
        self._clamp_scroll()
        
    def _clamp_scroll(self):
        """Ensure scroll offset is within valid range"""
        max_scroll = max(0, len(self.lines) - self.max_visible_lines)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
        
    def _draw_border(self, surface):
        """Draw border around the text display"""
        pygame.draw.rect(surface, self.border_color, 
                        (0, 0, self.display_width, self.display_height), 5)
        
    def _draw_text_lines(self, surface):
        """Draw the visible text lines"""
        if not self.lines:
            # Draw "No data" message
            font_large = Font("assets/swiss911.ttf", 20)
            text = font_large.render("NO DATA", True, (100, 100, 100))
            text_rect = text.get_rect(center=(self.display_width // 2, self.display_height // 2))
            surface.blit(text, text_rect)
            return
            
        # Calculate visible range
        start_line = self.scroll_offset
        end_line = min(len(self.lines), start_line + self.max_visible_lines)
        
        # Draw each visible line
        y_pos = 5  # Small top margin
        for i in range(start_line, end_line):
            line_text = self.lines[i]
            
            # Determine if this line is selected
            is_selected = (i == self.selected_index)
            
            # Draw selection highlight background
            if is_selected:
                highlight_rect = pygame.Rect(2, y_pos - 2, 
                                            self.display_width - 4, 
                                            self.line_height)
                pygame.draw.rect(surface, self.selected_bg_color, highlight_rect)
            
            # Choose text color
            text_color = self.selected_color if is_selected else self.text_color
            
            # Truncate line if too long
            max_chars = int((self.display_width - 20) / (self.font_size * 0.6))
            if len(line_text) > max_chars:
                line_text = line_text[:max_chars - 3] + "..."
            
            # Render text
            text_surface = self.font.render(line_text, True, text_color)
            surface.blit(text_surface, (10, y_pos))
            
            y_pos += self.line_height
            
    def _draw_scrollbar(self, surface):
        """Draw scrollbar indicator if content is scrollable"""
        if len(self.lines) <= self.max_visible_lines:
            return  # No scrollbar needed
            
        # Scrollbar dimensions
        bar_width = 8
        bar_x = self.display_width - bar_width - 4
        bar_y = 4
        bar_height = self.display_height - 8
        
        # Draw scrollbar track
        pygame.draw.rect(surface, (50, 50, 50), 
                        (bar_x, bar_y, bar_width, bar_height))
        
        # Calculate thumb size and position
        thumb_ratio = self.max_visible_lines / len(self.lines)
        thumb_height = max(20, int(bar_height * thumb_ratio))
        
        scroll_ratio = self.scroll_offset / max(1, len(self.lines) - self.max_visible_lines)
        thumb_y = bar_y + int((bar_height - thumb_height) * scroll_ratio)
        
        # Draw scrollbar thumb
        pygame.draw.rect(surface, self.border_color,
                        (bar_x, thumb_y, bar_width, thumb_height))
        
    def _draw_info_bar(self, surface):
        """Draw info bar at bottom showing line count and position"""
        if not self.lines:
            return
            
        info_height = 20
        info_y = self.display_height - info_height - 2
        
        # Draw info background
        pygame.draw.rect(surface, (20, 20, 20),
                        (2, info_y, self.display_width - 4, info_height))
        
        # Format info text
        if self.selected_index is not None:
            info_text = "Line {}/{} | Total: {}".format(
                self.selected_index + 1, 
                len(self.lines),
                len(self.lines)
            )
        else:
            info_text = "Lines: {} | Scroll: {}-{}".format(
                len(self.lines),
                self.scroll_offset + 1,
                min(self.scroll_offset + self.max_visible_lines, len(self.lines))
            )
        
        # Render info text
        info_font = Font("assets/swiss911.ttf", 14)
        text_surface = info_font.render(info_text, True, (150, 150, 150))
        surface.blit(text_surface, (10, info_y + 3))
        
    def update(self, screen):
        """Update and render the text display"""
        if not self.visible:
            return
        
        # Clear surface
        self.image.fill(self.bg_color)
        
        # Draw components
        self._draw_text_lines(self.image)
        self._draw_scrollbar(self.image)
        self._draw_info_bar(self.image)
        self._draw_border(self.image)
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
    
    def handleEvent(self, event, clock):
        """Handle mouse events for scrolling and selection"""
        if not self.visible:
            return False
        
        # Mouse wheel scrolling
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                # Mouse wheel up (button 4)
                if event.button == 4:
                    self.scroll_up(3)
                    return True
                # Mouse wheel down (button 5)
                elif event.button == 5:
                    self.scroll_down(3)
                    return True
                # Left click - select line
                elif event.button == 1:
                    # Convert to widget-relative coordinates
                    y_rel = event.pos[1] - self.rect.top
                    
                    # Calculate which line was clicked
                    line_index = int((y_rel - 5) / self.line_height) + self.scroll_offset
                    
                    if 0 <= line_index < len(self.lines):
                        self.set_selected_index(line_index)
                        return True
        
        return False
    
    def get_selected_line(self):
        """
        Get the currently selected line text
        
        Returns:
            String of selected line, or None if no selection
        """
        if self.selected_index is not None and 0 <= self.selected_index < len(self.lines):
            return self.lines[self.selected_index]
        return None
