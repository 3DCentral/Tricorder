#!/usr/bin/env python3
"""
antenna_analysis.py - LCARS Antenna Analysis Widget

Single-graph display showing noise floor across the full RF spectrum with
resonance markers, bandwidth spans, and harmonic annotations rendered on top
as the scan progresses and after analysis completes.

Layout (single full-height graph):
    - Cyan curve:          noise floor (dB) -- the primary measurement
    - Red dashed line:     median noise floor reference
    - Cyan filled spans:   resonance bandwidth (FWHM) regions
    - Yellow diamonds:     resonance peaks (fundamentals)
    - Orange diamonds:     resonance peaks (tagged as harmonics)
    - Label per resonance: "123.4 MHz  Q:4.2" (fundamentals)
                           "246.8 MHz  2x"    (harmonics, shows multiplier)
    - Colored band highlights (FM, Air, 2m, 70cm, etc.) in background
"""

import pygame
import numpy as np
from ui.widgets.lcars_widgets import LcarsWidget
from ui import colours


class LcarsAntennaAnalysis(LcarsWidget):
    """
    LCARS-styled single-graph antenna analysis widget.

    Data interface (called by emf_manager polling loop):
        add_data_point(freq_hz, noise_floor_db)   - called per-point during sweep
        set_resonances(resonance_array)           - called once when scan completes
        complete_scan()                           - marks scan finished
        clear()                                   - reset everything

    Band-selection interface (for targeted deep sweep):
        set_selected_band(index)                  - select a known_band by index (or None)
        get_selected_band()                       - returns the selected known_band dict, or None
        get_known_band_names()                    - returns list of band name strings (for TextDisplay)
        handle_graph_click(screen_x, screen_y)    - hit-test a click against band highlights;
                                                    returns True if a band was toggled
    """

    def __init__(self, pos, size):
        self.size = size
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.rect.topleft = pos

        LcarsWidget.__init__(self, colours.BLACK, pos, None)

        # --- Live sweep data (grows as points arrive) -----------------------
        self.frequencies  = []   # Hz
        self.noise_floors = []   # dB

        # --- Post-analysis results (set once on completion) -----------------
        self.resonances = []     # list of dicts loaded from structured npy

        # --- Scan state ------------------------------------------------------
        self.scan_active   = False
        self.scan_complete = False
        self.targeted_mode = False  # True when showing a high-density targeted scan

        # --- Band selection (for targeted deep sweep) ------------------------
        # Index into self.known_bands, or None.  Only meaningful after scan_complete.
        self.selected_band = None
        # Hit-test map: rebuilt every _render().  List of (x_left, x_right, band_index).
        # Coordinates are widget-local (relative to self.rect).
        self._band_hit_regions = []

        # --- Known frequency bands for background highlighting --------------
        # All in MHz for the log-scale mapper
        self.known_bands = [
            {'name': 'FM',      'start':  88, 'end': 108, 'color': (255, 165, 0), 'alpha': 40},
            {'name': 'Air',     'start': 118, 'end': 137, 'color': (255, 255, 0), 'alpha': 40},
            {'name': 'Wx Sat',  'start': 137, 'end': 138, 'color': (0, 255, 255), 'alpha': 50},
            {'name': '2m Ham',  'start': 144, 'end': 148, 'color': (255,   0, 255), 'alpha': 40},
            {'name': '70cm',    'start': 420, 'end': 450, 'color': (0, 100, 255), 'alpha': 40},
            {'name': 'ADS-B',   'start':1090, 'end':1090, 'color': (0, 200,   0), 'alpha': 50},
        ]

        # --- LCARS palette ---------------------------------------------------
        self.color_yellow   = (255, 204, 0)
        self.color_cyan     = (0, 255, 255)
        self.color_orange   = (255, 165, 0)
        self.color_magenta  = (255,   0, 255)
        self.color_red      = (255,   0, 0)
        self.color_green    = (0, 200, 0)
        self.color_grid     = (60, 60, 30)
        self.color_white    = (255, 255, 255)

        # --- Fonts -----------------------------------------------------------
        try:
            self.font_large  = pygame.font.Font("assets/swiss911.ttf", 28)
            self.font_medium = pygame.font.Font("assets/swiss911.ttf", 20)
            self.font_small  = pygame.font.Font("assets/swiss911.ttf", 15)
            self.font_tiny   = pygame.font.Font("assets/swiss911.ttf", 12)
        except Exception:
            self.font_large  = pygame.font.SysFont('monospace', 28)
            self.font_medium = pygame.font.SysFont('monospace', 20)
            self.font_small  = pygame.font.SysFont('monospace', 15)
            self.font_tiny   = pygame.font.SysFont('monospace', 12)

        self._render()

    # ---------------------------------------------------------------
    # Public data interface
    # ---------------------------------------------------------------

    def start_scan(self):
        self.scan_active   = True
        self.scan_complete = False
        self.resonances    = []
        self.targeted_mode = False  # Wide scan: use full spectrum range
        self._render()

    def start_targeted_scan(self):
        """Start a targeted high-density scan. Like start_scan but sets targeted_mode flag."""
        self.scan_active   = True
        self.scan_complete = False
        self.resonances    = []
        self.targeted_mode = True
        self._render()

    def add_data_point(self, freq_hz, noise_floor_db):
        """Append one measurement.  Called from the polling loop."""
        self.frequencies.append(freq_hz)
        self.noise_floors.append(noise_floor_db)
        self._render()

    def set_resonances(self, resonance_array):
        """
        Called once when the subprocess finishes and the resonances npy is
        available.  resonance_array is the structured numpy array written by
        rtl_antenna_scan.py (or an empty array if none were found).
        """
        self.resonances = []
        for r in resonance_array:
            self.resonances.append({
                'frequency':        float(r['frequency']),
                'noise_floor':      float(r['noise_floor']),
                'prominence':       float(r['prominence']),
                'bandwidth':        float(r['bandwidth']),
                'q_factor':         float(r['q_factor']),
                'left_freq':        float(r['left_freq']),
                'right_freq':       float(r['right_freq']),
                'is_harmonic':      bool(r['is_harmonic']),
                'harmonic_number':  int(r['harmonic_number']),
                'fundamental_freq': float(r['fundamental_freq']),
            })
        self._render()

    def complete_scan(self):
        self.scan_active   = False
        self.scan_complete = True
        self._render()

    def clear(self):
        self.scan_active   = False
        self.scan_complete = False
        self.frequencies   = []
        self.noise_floors  = []
        self.resonances    = []
        self.selected_band = None
        self.targeted_mode = False
        self._render()

    # ---------------------------------------------------------------
    # Band selection interface
    # ---------------------------------------------------------------

    def get_known_band_names(self):
        """Return the list of known band name strings, in order.
        Used by emf_manager to populate the TextDisplay."""
        return [b['name'] for b in self.known_bands]

    def set_selected_band(self, index):
        """Select a known_band by index into self.known_bands, or None to deselect.
        Called by emf_manager when the user picks a line in the TextDisplay."""
        if index is not None and (index < 0 or index >= len(self.known_bands)):
            index = None
        self.selected_band = index
        self._render()

    def get_selected_band(self):
        """Return the currently selected known_band dict (with 'name', 'start', 'end'
        in MHz), or None if nothing is selected."""
        if self.selected_band is None:
            return None
        return self.known_bands[self.selected_band]

    def handle_graph_click(self, screen_x, screen_y):
        """Hit-test a mouse click against the band highlight regions on the graph.

        screen_x / screen_y are in screen (pygame window) coordinates — the same
        values that come straight out of event.pos.

        Returns True if the click landed on a band and selection was toggled,
        False if it missed (so the caller knows whether to consume the event).
        Only active after scan_complete; clicks are ignored while scanning.
        """
        if not self.scan_complete:
            return False

        # Convert screen coords → widget-local coords
        lx = screen_x - self.rect.left
        ly = screen_y - self.rect.top

        # ly doesn't matter — bands span the full graph height — but we do need
        # to confirm the click is vertically within the widget at all.
        if ly < 0 or ly > self.size[1]:
            return False

        for x_left, x_right, band_idx in self._band_hit_regions:
            if x_left <= lx <= x_right:
                # Toggle: clicking the already-selected band deselects it
                if self.selected_band == band_idx:
                    self.selected_band = None
                else:
                    self.selected_band = band_idx
                self._render()
                return True

        return False

    # ---------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------

    def _render(self):
        width, height = self.size
        self.image.fill((0, 0, 0))

        # Rebuild hit-test map each frame (band pixel positions may shift on resize)
        self._band_hit_regions = []

        # Title bar area: 30 px at top
        # Graph area: everything below that, with 45 px margins left/right
        # and 40 px at bottom for x-axis labels
        graph_rect = pygame.Rect(45, 30, width - 90, height - 80)

        # --- Layers (back to front) -----------------------------------------
        self._draw_band_highlights(graph_rect)
        self._draw_grid(graph_rect)
        self._draw_resonance_spans(graph_rect)   # filled BW regions
        self._draw_median_line(graph_rect)
        self._draw_noise_curve(graph_rect)
        self._draw_resonance_markers(graph_rect) # diamonds + labels
        self._draw_axes(graph_rect)
        self._draw_status(width)

    # ---------------------------------------------------------------
    # Coordinate helpers
    # ---------------------------------------------------------------
    # Frequency axis is logarithmic 50 MHz .. 2200 MHz for wide scans,
    # or dynamically fitted to the actual data range for targeted scans.

    FREQ_MIN_MHZ = 50.0     # Wide scan default
    FREQ_MAX_MHZ = 2200.0   # Wide scan default

    def _get_freq_range(self):
        """Return the (freq_min_mhz, freq_max_mhz) to use for axis scaling.
        
        In targeted mode, use the actual data bounds with 5% padding.
        In wide mode, use the hardcoded defaults.
        """
        if self.targeted_mode and self.frequencies:
            # Use actual data range with padding
            freq_min_hz = min(self.frequencies)
            freq_max_hz = max(self.frequencies)
            span = freq_max_hz - freq_min_hz
            padding = span * 0.05  # 5% padding on each side
            
            freq_min_mhz = max(1.0, (freq_min_hz - padding) / 1e6)  # Don't go below 1 MHz
            freq_max_mhz = (freq_max_hz + padding) / 1e6
            
            return (freq_min_mhz, freq_max_mhz)
        else:
            # Wide scan: use full RTL-SDR range
            return (self.FREQ_MIN_MHZ, self.FREQ_MAX_MHZ)

    def _freq_to_x(self, freq_hz, rect):
        """Map frequency (Hz) to screen X within rect."""
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
        freq_mhz = freq_hz / 1e6
        
        # Clamp frequency to valid range to prevent log of zero/negative
        # and to prevent overflow when frequency is way outside display range
        if freq_mhz <= 0:
            freq_mhz = freq_min_mhz
        
        # Calculate logarithmic position
        log_val  = np.log10(freq_mhz)
        log_min  = np.log10(freq_min_mhz)
        log_max  = np.log10(freq_max_mhz)
        t = (log_val - log_min) / (log_max - log_min)
        
        # Clamp t to [0, 1] to prevent overflow from infinity values
        # This happens when freq is far outside the display range
        t = max(0.0, min(1.0, t))
        
        return int(rect.left + t * rect.width)

    def _db_to_y(self, db_val, rect, y_min, y_max):
        """Map dB value to screen Y within rect (inverted: higher dB = higher on screen)."""
        t = (db_val - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        return int(rect.bottom - t * rect.height)

    def _y_range(self):
        """Return (y_min, y_max) dB range for the current data, with padding."""
        if not self.noise_floors:
            return (-120, -60)
        lo = min(self.noise_floors)
        hi = max(self.noise_floors)
        pad = max(5, (hi - lo) * 0.15)
        return (lo - pad, hi + pad)

    # ---------------------------------------------------------------
    # Draw layers
    # ---------------------------------------------------------------

    def _draw_band_highlights(self, rect):
        """Translucent vertical bands for known allocations.

        After scan_complete the bands become selectable targets for a targeted
        deep sweep.  The selected band is rendered noticeably brighter and with
        a cyan border so it reads as "active" even at a glance.  Every band's
        pixel extent is recorded into _band_hit_regions for mouse hit-testing.
        """
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
        for idx, band in enumerate(self.known_bands):
            # Skip bands completely outside the visible range (optimization for targeted mode)
            # Allow some overlap for partially visible bands
            if band['end'] < freq_min_mhz * 0.5 or band['start'] > freq_max_mhz * 2.0:
                continue
            
            x_start = self._freq_to_x(band['start'] * 1e6, rect)
            x_end   = self._freq_to_x(band['end']   * 1e6, rect)
            bw = max(x_end - x_start, 2)   # ADS-B is a single freq; min 2 px

            is_selected = (self.scan_complete and idx == self.selected_band)

            # Fill alpha: idle = original, selected = much brighter
            alpha = 80 if is_selected else band['alpha']

            surf = pygame.Surface((bw, rect.height), pygame.SRCALPHA)
            surf.fill((*band['color'], alpha))
            self.image.blit(surf, (x_start, rect.top))

            # Border on selected band — makes it pop off the graph
            if is_selected:
                pygame.draw.rect(self.image, self.color_cyan,
                                 pygame.Rect(x_start, rect.top, bw, rect.height), 2)

            # Band name label at top.  Color brightens when selected.
            lbl_color = self.color_white if is_selected else band['color']
            lbl = self.font_tiny.render(band['name'], True, lbl_color)
            self.image.blit(lbl, (x_start + 2, rect.top + 2))

            # Register hit region (widget-local x coordinates)
            self._band_hit_regions.append((x_start, x_start + bw, idx))

    def _draw_grid(self, rect):
        """Horizontal dB grid lines and vertical decade markers."""
        y_min, y_max = self._y_range()
        freq_min_mhz, freq_max_mhz = self._get_freq_range()

        # Horizontal: every 10 dB if range allows, else adaptive
        span = y_max - y_min
        step = 10 if span > 20 else 5
        db = np.ceil(y_min / step) * step
        while db <= y_max:
            y = self._db_to_y(db, rect, y_min, y_max)
            pygame.draw.line(self.image, self.color_grid,
                             (rect.left, y), (rect.right, y), 1)
            # dB label on left edge
            lbl = self.font_tiny.render("{:.0f}".format(db), True, (120, 120, 80))
            self.image.blit(lbl, (rect.left - 38, y - 6))
            db += step

        # Vertical: use same logic as _draw_axes for consistency
        if self.targeted_mode:
            span = freq_max_mhz - freq_min_mhz
            if span <= 5:
                step = 1.0 if span > 2 else 0.5
            elif span <= 20:
                step = 2.0
            elif span <= 50:
                step = 5.0
            else:
                step = 10.0
            
            tick = np.ceil(freq_min_mhz / step) * step
            while tick <= freq_max_mhz:
                x = self._freq_to_x(tick * 1e6, rect)
                if rect.left <= x <= rect.right:
                    pygame.draw.line(self.image, self.color_grid,
                                     (x, rect.top), (x, rect.bottom), 1)
                tick += step
        else:
            # Wide scan: hardcoded log-spaced grid
            for tick_mhz in [50, 100, 200, 500, 1000, 2000]:
                x = self._freq_to_x(tick_mhz * 1e6, rect)
                pygame.draw.line(self.image, self.color_grid,
                                 (x, rect.top), (x, rect.bottom), 1)

        # Border
        pygame.draw.rect(self.image, self.color_cyan, rect, 1)

    def _draw_resonance_spans(self, rect):
        """Filled translucent rectangles showing each resonance's FWHM bandwidth."""
        if not self.resonances:
            return
        y_min, y_max = self._y_range()

        for r in self.resonances:
            x_left  = self._freq_to_x(r['left_freq'],  rect)
            x_right = self._freq_to_x(r['right_freq'], rect)
            bw_px   = max(x_right - x_left, 3)

            # Color: cyan for fundamentals, orange for harmonics
            color = self.color_orange if r['is_harmonic'] else self.color_cyan

            surf = pygame.Surface((bw_px, rect.height), pygame.SRCALPHA)
            surf.fill((*color, 25))
            self.image.blit(surf, (x_left, rect.top))

    def _draw_median_line(self, rect):
        """Horizontal red dashed line at the median noise floor."""
        if not self.noise_floors:
            return
        y_min, y_max = self._y_range()
        median = float(np.median(self.noise_floors))
        y = self._db_to_y(median, rect, y_min, y_max)

        # Dashed line by drawing short segments
        dash_on, dash_off = 8, 5
        x = rect.left
        while x < rect.right:
            end_x = min(x + dash_on, rect.right)
            pygame.draw.line(self.image, self.color_red, (x, y), (end_x, y), 1)
            x += dash_on + dash_off

        # Label
        lbl = self.font_tiny.render("median {:.1f} dB".format(median), True, self.color_red)
        self.image.blit(lbl, (rect.right - lbl.get_width() - 4, y - 14))

    def _draw_noise_curve(self, rect):
        """The main noise-floor trace and optional fill underneath."""
        if len(self.frequencies) < 2:
            return
        y_min, y_max = self._y_range()

        points = []
        for freq, nf in zip(self.frequencies, self.noise_floors):
            px = self._freq_to_x(freq, rect)
            py = self._db_to_y(nf, rect, y_min, y_max)
            points.append((px, py))

        # Filled area under curve (subtle cyan)
        if len(points) >= 2:
            fill_pts = [(points[0][0], rect.bottom)] + points + [(points[-1][0], rect.bottom)]
            surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            adjusted = [(x - rect.left, y - rect.top) for x, y in fill_pts]
            pygame.draw.polygon(surf, (0, 255, 255, 35), adjusted)
            self.image.blit(surf, (rect.left, rect.top))

        # Curve line
        pygame.draw.lines(self.image, self.color_cyan, False, points, 2)

        # Data-point dots
        for pt in points:
            pygame.draw.circle(self.image, self.color_cyan, pt, 2)

    def _draw_resonance_markers(self, rect):
        """Diamond markers at each resonance peak with frequency + Q or harmonic label."""
        if not self.resonances:
            return
        y_min, y_max = self._y_range()

        for r in self.resonances:
            x = self._freq_to_x(r['frequency'], rect)
            y = self._db_to_y(r['noise_floor'], rect, y_min, y_max)

            # Diamond size
            sz = 6

            # Color and label differ for fundamentals vs harmonics
            if r['is_harmonic']:
                color = self.color_orange
                freq_str = "{:.1f} MHz".format(r['frequency'] / 1e6)
                detail  = "{}x".format(r['harmonic_number'])
            else:
                color = self.color_yellow
                freq_str = "{:.1f} MHz".format(r['frequency'] / 1e6)
                detail  = "Q:{:.1f}".format(r['q_factor']) if r['q_factor'] > 0 else ""

            # Draw diamond
            diamond = [
                (x, y - sz),
                (x + sz, y),
                (x, y + sz),
                (x - sz, y),
            ]
            pygame.draw.polygon(self.image, color, diamond)
            pygame.draw.polygon(self.image, self.color_white, diamond, 1)

            # Label: two lines, centered above the diamond
            lbl1 = self.font_small.render(freq_str, True, color)
            lbl2 = self.font_tiny.render(detail, True, color) if detail else None

            label_h = lbl1.get_height() + (lbl2.get_height() if lbl2 else 0) + 2
            label_top = y - sz - label_h - 4

            # Clamp so label doesn't go above the graph rect
            if label_top < rect.top:
                label_top = rect.top

            self.image.blit(lbl1, (x - lbl1.get_width() // 2, label_top))
            if lbl2:
                self.image.blit(lbl2, (x - lbl2.get_width() // 2,
                                       label_top + lbl1.get_height() + 1))

    def _draw_axes(self, rect):
        """X-axis frequency labels and Y-axis title."""
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
        # Generate appropriate tick marks based on the range
        if self.targeted_mode:
            # Narrow range: use linear spacing with appropriate density
            span = freq_max_mhz - freq_min_mhz
            
            if span <= 5:
                # Very narrow (e.g., 2m ham: 144-148 MHz = 4 MHz)
                # Place ticks every 0.5 or 1 MHz
                step = 1.0 if span > 2 else 0.5
            elif span <= 20:
                # Narrow (e.g., FM: 88-108 MHz = 20 MHz)
                step = 2.0
            elif span <= 50:
                # Medium (e.g., 70cm: 420-450 MHz = 30 MHz)
                step = 5.0
            else:
                # Wide but not full spectrum
                step = 10.0
            
            # Generate ticks
            tick_freqs = []
            tick = np.ceil(freq_min_mhz / step) * step
            while tick <= freq_max_mhz:
                tick_freqs.append(tick)
                tick += step
        else:
            # Wide scan: use hardcoded log-spaced ticks
            tick_freqs = [50, 100, 200, 500, 1000, 2000]
        
        # Draw ticks and labels
        for tick_mhz in tick_freqs:
            x = self._freq_to_x(tick_mhz * 1e6, rect)
            
            # Skip ticks that are outside the graph area
            if x < rect.left or x > rect.right:
                continue
            
            # Format label
            if tick_mhz >= 1000:
                label = "{:.1f} GHz".format(tick_mhz / 1000)
            elif tick_mhz >= 100:
                label = "{:.0f} MHz".format(tick_mhz)
            else:
                label = "{:.1f} MHz".format(tick_mhz)
            
            lbl = self.font_tiny.render(label, True, self.color_yellow)
            self.image.blit(lbl, (x - lbl.get_width() // 2, rect.bottom + 4))

        # Y-axis title (rotated)
        y_title = self.font_medium.render("NOISE FLOOR (dB)", True, self.color_cyan)
        y_title_rot = pygame.transform.rotate(y_title, 90)
        self.image.blit(y_title_rot, (4, rect.centery - y_title_rot.get_height() // 2))

    def _draw_status(self, width):
        """Status line at top-right."""
        if self.scan_active:
            text  = "SCANNING... {}/{} POINTS".format(len(self.frequencies), 60)
            color = self.color_yellow
        elif self.scan_complete:
            res_count = len(self.resonances)
            text  = "SCAN COMPLETE - {} POINTS | {} RESONANCE{}".format(
                len(self.frequencies), res_count, "S" if res_count != 1 else "")
            color = self.color_cyan
        else:
            text  = "READY"
            color = self.color_orange

        surf = self.font_small.render(text, True, color)
        self.image.blit(surf, (width - surf.get_width() - 10, 6))

        # Title on the left
        title = self.font_medium.render("ANTENNA CHARACTERIZATION", True, self.color_yellow)
        self.image.blit(title, (10, 6))
