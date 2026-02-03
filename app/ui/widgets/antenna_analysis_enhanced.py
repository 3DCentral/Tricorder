#!/usr/bin/env python3
"""
antenna_analysis_enhanced.py - Enhanced LCARS Antenna Analysis Widget

Additional features for antenna tuning and development:
1. Live tuning meter showing resonance quality
2. Comparison mode to overlay previous scans
3. Bandwidth/Q-factor trend tracking
4. Center frequency drift indicator
5. Clearer FWHM visualization with actual dB markers
"""

import pygame
import numpy as np
from ui.widgets.lcars_widgets import LcarsWidget
from ui import colours


class LcarsAntennaAnalysisEnhanced(LcarsWidget):
    """
    Enhanced LCARS antenna analysis widget with tuning-focused features.
    
    New features beyond the base widget:
    - Comparison mode: Overlay previous scan (in different color)
    - Tuning meter: Large numeric display of primary resonance Q-factor
    - Drift indicator: Shows frequency shift from baseline
    - Trend tracking: Mini graph showing Q-factor over time
    """

    def __init__(self, pos, size):
        self.size = size
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.rect.topleft = pos

        LcarsWidget.__init__(self, colours.BLACK, pos, None)

        # --- Live sweep data (current scan) -----------------------------
        self.frequencies  = []   # Hz
        self.noise_floors = []   # dB

        # --- Comparison data (previous scan for overlay) ----------------
        self.comparison_frequencies = []
        self.comparison_noise_floors = []
        self.comparison_resonances = []
        self.comparison_mode = False  # Toggle to show/hide comparison
        
        # --- Baseline reference (first scan after entering targeted mode) -
        self.baseline_frequencies = []
        self.baseline_noise_floors = []
        self.baseline_resonances = []
        self.has_baseline = False

        # --- Post-analysis results (set once on completion) -------------
        self.resonances = []     # list of dicts loaded from structured npy

        # --- Scan state --------------------------------------------------
        self.scan_active   = False
        self.scan_complete = False
        self.targeted_mode = False

        # --- Band selection (for targeted deep sweep) --------------------
        self.selected_band = None
        self._band_hit_regions = []

        # --- Tuning history (for trend graph) ---------------------------
        # Stores tuples of (timestamp, primary_freq, primary_q, primary_prominence)
        self.tuning_history = []
        self.max_history_points = 20  # Keep last 20 scans

        # --- Known frequency bands ---------------------------------------
        self.known_bands = [
            {'name': 'FM',      'start':  88, 'end': 108, 'color': (255, 165, 0), 'alpha': 40},
            {'name': 'Air',     'start': 118, 'end': 137, 'color': (255, 255, 0), 'alpha': 40},
            {'name': 'Wx Sat',  'start': 137, 'end': 138, 'color': (0, 255, 255), 'alpha': 50},
            {'name': '2m Ham',  'start': 144, 'end': 148, 'color': (255,   0, 255), 'alpha': 40},
            {'name': '70cm',    'start': 420, 'end': 450, 'color': (0, 100, 255), 'alpha': 40},
            {'name': 'ADS-B',   'start':1090, 'end':1090, 'color': (0, 200,   0), 'alpha': 50},
        ]

        # --- LCARS palette -----------------------------------------------
        self.color_yellow   = (255, 204, 0)
        self.color_cyan     = (0, 255, 255)
        self.color_orange   = (255, 165, 0)
        self.color_magenta  = (255,   0, 255)
        self.color_red      = (255,   0, 0)
        self.color_green    = (0, 200, 0)
        self.color_blue     = (100, 149, 237)  # Cornflower blue for comparison
        self.color_grid     = (60, 60, 30)
        self.color_white    = (255, 255, 255)

        # --- Fonts -------------------------------------------------------
        try:
            self.font_huge   = pygame.font.Font("assets/swiss911.ttf", 72)  # For tuning meter
            self.font_large  = pygame.font.Font("assets/swiss911.ttf", 28)
            self.font_medium = pygame.font.Font("assets/swiss911.ttf", 20)
            self.font_small  = pygame.font.Font("assets/swiss911.ttf", 15)
            self.font_tiny   = pygame.font.Font("assets/swiss911.ttf", 12)
        except Exception:
            self.font_huge   = pygame.font.SysFont('monospace', 72, bold=True)
            self.font_large  = pygame.font.SysFont('monospace', 28)
            self.font_medium = pygame.font.SysFont('monospace', 20)
            self.font_small  = pygame.font.SysFont('monospace', 15)
            self.font_tiny   = pygame.font.SysFont('monospace', 12)

        self._render()

    # ---------------------------------------------------------------
    # Public data interface (matches base class)
    # ---------------------------------------------------------------

    def start_scan(self):
        self.scan_active   = True
        self.scan_complete = False
        self.resonances    = []
        self.targeted_mode = False
        self._render()

    def start_targeted_scan(self):
        """Start a targeted high-density scan."""
        self.scan_active   = True
        self.scan_complete = False
        self.resonances    = []
        self.targeted_mode = True
        self._render()

    def add_data_point(self, freq_hz, noise_floor_db):
        """Append one measurement."""
        self.frequencies.append(freq_hz)
        self.noise_floors.append(noise_floor_db)
        self._render()

    def set_resonances(self, resonance_array):
        """Called once when the subprocess finishes."""
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
        """Mark scan as complete and update tuning history."""
        self.scan_active   = False
        self.scan_complete = True
        
        # Add to tuning history if we have a primary resonance
        if self.resonances and self.targeted_mode:
            primary = self.resonances[0]
            import time
            self.tuning_history.append({
                'timestamp': time.time(),
                'frequency': primary['frequency'],
                'q_factor': primary['q_factor'],
                'prominence': primary['prominence'],
                'bandwidth': primary['bandwidth']
            })
            
            # Trim history to max points
            if len(self.tuning_history) > self.max_history_points:
                self.tuning_history = self.tuning_history[-self.max_history_points:]
            
            # Set baseline if this is the first targeted scan
            if not self.has_baseline:
                self.set_baseline()
        
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
    # New: Comparison and baseline methods
    # ---------------------------------------------------------------

    def save_as_comparison(self):
        """Save current scan as comparison overlay."""
        self.comparison_frequencies = list(self.frequencies)
        self.comparison_noise_floors = list(self.noise_floors)
        self.comparison_resonances = list(self.resonances)
        print("Scan saved for comparison")

    def toggle_comparison(self):
        """Toggle comparison overlay on/off."""
        if self.comparison_frequencies:
            self.comparison_mode = not self.comparison_mode
            self._render()
            print("Comparison mode: {}".format("ON" if self.comparison_mode else "OFF"))
        else:
            print("No comparison scan available - complete a scan first")

    def clear_comparison(self):
        """Clear comparison data."""
        self.comparison_frequencies = []
        self.comparison_noise_floors = []
        self.comparison_resonances = []
        self.comparison_mode = False
        self._render()
        print("Comparison data cleared")

    def set_baseline(self):
        """Set current scan as the baseline reference for drift calculation."""
        self.baseline_frequencies = list(self.frequencies)
        self.baseline_noise_floors = list(self.noise_floors)
        self.baseline_resonances = list(self.resonances)
        self.has_baseline = True
        print("Baseline set")

    def clear_baseline(self):
        """Clear baseline reference."""
        self.baseline_frequencies = []
        self.baseline_noise_floors = []
        self.baseline_resonances = []
        self.has_baseline = False
        self._render()
        print("Baseline cleared")

    def clear_history(self):
        """Clear tuning history."""
        self.tuning_history = []
        self._render()
        print("Tuning history cleared")

    # ---------------------------------------------------------------
    # Band selection interface (matches base class)
    # ---------------------------------------------------------------

    def get_known_band_names(self):
        return [b['name'] for b in self.known_bands]

    def set_selected_band(self, index):
        if index is not None and (index < 0 or index >= len(self.known_bands)):
            index = None
        self.selected_band = index
        self._render()

    def get_selected_band(self):
        if self.selected_band is None:
            return None
        return self.known_bands[self.selected_band]

    def handle_graph_click(self, screen_x, screen_y):
        """Handle clicks on the graph."""
        if not self.scan_complete:
            return False

        lx = screen_x - self.rect.left
        ly = screen_y - self.rect.top

        if ly < 0 or ly > self.size[1]:
            return False

        for x_left, x_right, band_idx in self._band_hit_regions:
            if x_left <= lx <= x_right:
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

        self._band_hit_regions = []

        # Main graph area
        graph_rect = pygame.Rect(45, 30, width - 90, height - 80)

        # --- Draw main graph layers ----------------------------------
        self._draw_band_highlights(graph_rect)
        self._draw_grid(graph_rect)
        
        # Draw comparison data first (if enabled)
        if self.comparison_mode and self.comparison_frequencies:
            self._draw_comparison_curve(graph_rect)
            self._draw_comparison_resonances(graph_rect)
        
        # Draw current data on top
        self._draw_resonance_spans(graph_rect)
        self._draw_median_line(graph_rect)
        self._draw_noise_curve(graph_rect)
        self._draw_resonance_markers(graph_rect)
        
        # NEW: Draw FWHM markers with dB labels
        self._draw_fwhm_markers(graph_rect)
        
        self._draw_axes(graph_rect)
        self._draw_status(width)
        
        # --- NEW: Draw tuning aids -----------------------------------
        if self.targeted_mode and self.scan_complete and self.resonances:
            # Tuning meter (top-right)
            self._draw_tuning_meter(width, height)
            
            # Drift indicator (if baseline exists)
            if self.has_baseline and self.baseline_resonances:
                self._draw_drift_indicator(width, height)
            
            # Trend graph (bottom-right)
            if len(self.tuning_history) > 1:
                self._draw_trend_graph(width, height)

    # ---------------------------------------------------------------
    # Coordinate helpers (from base class)
    # ---------------------------------------------------------------

    FREQ_MIN_MHZ = 50.0
    FREQ_MAX_MHZ = 2200.0

    def _get_freq_range(self):
        """Return the (freq_min_mhz, freq_max_mhz) to use for axis scaling."""
        if self.targeted_mode and self.frequencies:
            freq_min_hz = min(self.frequencies)
            freq_max_hz = max(self.frequencies)
            span = freq_max_hz - freq_min_hz
            padding = span * 0.05
            
            freq_min_mhz = max(1.0, (freq_min_hz - padding) / 1e6)
            freq_max_mhz = (freq_max_hz + padding) / 1e6
            
            return (freq_min_mhz, freq_max_mhz)
        else:
            return (self.FREQ_MIN_MHZ, self.FREQ_MAX_MHZ)

    def _freq_to_x(self, freq_hz, rect):
        """Map frequency (Hz) to screen X within rect."""
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
        freq_mhz = freq_hz / 1e6
        
        if freq_mhz <= 0:
            freq_mhz = freq_min_mhz
        
        log_val  = np.log10(freq_mhz)
        log_min  = np.log10(freq_min_mhz)
        log_max  = np.log10(freq_max_mhz)
        t = (log_val - log_min) / (log_max - log_min)
        
        # Clamp to prevent overflow
        t = max(0.0, min(1.0, t))
        
        return int(rect.left + t * rect.width)

    def _db_to_y(self, db_val, rect, y_min, y_max):
        """Map dB value to screen Y within rect."""
        t = (db_val - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        return int(rect.bottom - t * rect.height)

    def _y_range(self):
        """Return (y_min, y_max) dB range for the current data."""
        if not self.noise_floors:
            return (-120, -60)
        lo = min(self.noise_floors)
        hi = max(self.noise_floors)
        
        # Also consider comparison data if visible
        if self.comparison_mode and self.comparison_noise_floors:
            lo = min(lo, min(self.comparison_noise_floors))
            hi = max(hi, max(self.comparison_noise_floors))
        
        pad = max(5, (hi - lo) * 0.15)
        return (lo - pad, hi + pad)

    # ---------------------------------------------------------------
    # Draw layers (from base class - keeping existing implementations)
    # ---------------------------------------------------------------
    
    def _draw_band_highlights(self, rect):
        """Translucent vertical bands for known allocations."""
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
        for idx, band in enumerate(self.known_bands):
            # Skip bands outside visible range
            if band['end'] < freq_min_mhz * 0.5 or band['start'] > freq_max_mhz * 2.0:
                continue
            
            x_start = self._freq_to_x(band['start'] * 1e6, rect)
            x_end   = self._freq_to_x(band['end']   * 1e6, rect)
            bw = max(x_end - x_start, 2)

            is_selected = (self.scan_complete and idx == self.selected_band)
            alpha = 80 if is_selected else band['alpha']

            surf = pygame.Surface((bw, rect.height), pygame.SRCALPHA)
            surf.fill((*band['color'], alpha))
            self.image.blit(surf, (x_start, rect.top))

            if is_selected:
                pygame.draw.rect(self.image, self.color_cyan,
                                 pygame.Rect(x_start, rect.top, bw, rect.height), 2)

            lbl_color = self.color_white if is_selected else band['color']
            lbl = self.font_tiny.render(band['name'], True, lbl_color)
            self.image.blit(lbl, (x_start + 2, rect.top + 2))

            self._band_hit_regions.append((x_start, x_start + bw, idx))

    def _draw_grid(self, rect):
        """Horizontal dB grid lines and vertical frequency markers."""
        y_min, y_max = self._y_range()
        freq_min_mhz, freq_max_mhz = self._get_freq_range()

        # Horizontal grid
        span = y_max - y_min
        step = 10 if span > 20 else 5
        db = np.ceil(y_min / step) * step
        while db <= y_max:
            y = self._db_to_y(db, rect, y_min, y_max)
            pygame.draw.line(self.image, self.color_grid,
                             (rect.left, y), (rect.right, y), 1)
            lbl = self.font_tiny.render("{:.0f}".format(db), True, (120, 120, 80))
            self.image.blit(lbl, (rect.left - 38, y - 6))
            db += step

        # Vertical grid
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
            for tick_mhz in [50, 100, 200, 500, 1000, 2000]:
                x = self._freq_to_x(tick_mhz * 1e6, rect)
                pygame.draw.line(self.image, self.color_grid,
                                 (x, rect.top), (x, rect.bottom), 1)

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

        dash_on, dash_off = 8, 5
        x = rect.left
        while x < rect.right:
            end_x = min(x + dash_on, rect.right)
            pygame.draw.line(self.image, self.color_red, (x, y), (end_x, y), 1)
            x += dash_on + dash_off

        lbl = self.font_tiny.render("median {:.1f} dB".format(median), True, self.color_red)
        self.image.blit(lbl, (rect.right - lbl.get_width() - 4, y - 14))

    def _draw_noise_curve(self, rect):
        """The main noise-floor trace."""
        if len(self.frequencies) < 2:
            return
        y_min, y_max = self._y_range()

        points = []
        for freq, nf in zip(self.frequencies, self.noise_floors):
            px = self._freq_to_x(freq, rect)
            py = self._db_to_y(nf, rect, y_min, y_max)
            points.append((px, py))

        # Filled area
        if len(points) >= 2:
            fill_pts = [(points[0][0], rect.bottom)] + points + [(points[-1][0], rect.bottom)]
            surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            adjusted = [(x - rect.left, y - rect.top) for x, y in fill_pts]
            pygame.draw.polygon(surf, (0, 255, 255, 35), adjusted)
            self.image.blit(surf, (rect.left, rect.top))

        # Curve line
        pygame.draw.lines(self.image, self.color_cyan, False, points, 2)

        # Data points
        for pt in points:
            pygame.draw.circle(self.image, self.color_cyan, pt, 2)

    def _draw_resonance_markers(self, rect):
        """Diamond markers at each resonance peak."""
        if not self.resonances:
            return
        y_min, y_max = self._y_range()

        for r in self.resonances:
            x = self._freq_to_x(r['frequency'], rect)
            y = self._db_to_y(r['noise_floor'], rect, y_min, y_max)

            sz = 6

            if r['is_harmonic']:
                color = self.color_orange
                freq_str = "{:.1f} MHz".format(r['frequency'] / 1e6)
                detail  = "{}x".format(r['harmonic_number'])
            else:
                color = self.color_yellow
                freq_str = "{:.1f} MHz".format(r['frequency'] / 1e6)
                detail  = "Q:{:.1f}".format(r['q_factor']) if r['q_factor'] > 0 else ""

            diamond = [
                (x, y - sz),
                (x + sz, y),
                (x, y + sz),
                (x - sz, y),
            ]
            pygame.draw.polygon(self.image, color, diamond)
            pygame.draw.polygon(self.image, self.color_white, diamond, 1)

            lbl1 = self.font_small.render(freq_str, True, color)
            lbl2 = self.font_tiny.render(detail, True, color) if detail else None

            label_h = lbl1.get_height() + (lbl2.get_height() if lbl2 else 0) + 2
            label_top = y - sz - label_h - 4

            if label_top < rect.top:
                label_top = rect.top

            self.image.blit(lbl1, (x - lbl1.get_width() // 2, label_top))
            if lbl2:
                self.image.blit(lbl2, (x - lbl2.get_width() // 2,
                                       label_top + lbl1.get_height() + 1))

    def _draw_axes(self, rect):
        """X-axis frequency labels and Y-axis title."""
        freq_min_mhz, freq_max_mhz = self._get_freq_range()
        
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
            
            tick_freqs = []
            tick = np.ceil(freq_min_mhz / step) * step
            while tick <= freq_max_mhz:
                tick_freqs.append(tick)
                tick += step
        else:
            tick_freqs = [50, 100, 200, 500, 1000, 2000]
        
        for tick_mhz in tick_freqs:
            x = self._freq_to_x(tick_mhz * 1e6, rect)
            
            if x < rect.left or x > rect.right:
                continue
            
            if tick_mhz >= 1000:
                label = "{:.1f} GHz".format(tick_mhz / 1000)
            elif tick_mhz >= 100:
                label = "{:.0f} MHz".format(tick_mhz)
            else:
                label = "{:.1f} MHz".format(tick_mhz)
            
            lbl = self.font_tiny.render(label, True, self.color_yellow)
            self.image.blit(lbl, (x - lbl.get_width() // 2, rect.bottom + 4))

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

        title = self.font_medium.render("ANTENNA CHARACTERIZATION", True, self.color_yellow)
        self.image.blit(title, (10, 6))

    # ---------------------------------------------------------------
    # NEW: Comparison mode drawing
    # ---------------------------------------------------------------

    def _draw_comparison_curve(self, rect):
        """Draw comparison scan data in blue with lower opacity."""
        if len(self.comparison_frequencies) < 2:
            return
        y_min, y_max = self._y_range()

        points = []
        for freq, nf in zip(self.comparison_frequencies, self.comparison_noise_floors):
            px = self._freq_to_x(freq, rect)
            py = self._db_to_y(nf, rect, y_min, y_max)
            points.append((px, py))

        # Draw comparison curve in blue with transparency
        if len(points) >= 2:
            pygame.draw.lines(self.image, self.color_blue, False, points, 2)

    def _draw_comparison_resonances(self, rect):
        """Draw comparison resonance markers (smaller, blue)."""
        if not self.comparison_resonances:
            return
        y_min, y_max = self._y_range()

        for r in self.comparison_resonances:
            x = self._freq_to_x(r['frequency'], rect)
            y = self._db_to_y(r['noise_floor'], rect, y_min, y_max)

            # Smaller diamond for comparison
            sz = 4
            diamond = [
                (x, y - sz),
                (x + sz, y),
                (x, y + sz),
                (x - sz, y),
            ]
            pygame.draw.polygon(self.image, self.color_blue, diamond)
            pygame.draw.polygon(self.image, self.color_white, diamond, 1)

    # ---------------------------------------------------------------
    # NEW: Enhanced tuning visualization
    # ---------------------------------------------------------------

    def _draw_fwhm_markers(self, rect):
        """Draw FWHM (3dB) markers with actual dB value labels."""
        if not self.resonances:
            return
        
        # Only draw for primary resonance in targeted mode
        if not self.targeted_mode:
            return
        
        primary = self.resonances[0]
        y_min, y_max = self._y_range()
        
        # Calculate half-max dB level
        half_max_db = primary['noise_floor'] - primary['prominence'] / 2
        
        # Draw horizontal line at half-max
        y_half = self._db_to_y(half_max_db, rect, y_min, y_max)
        pygame.draw.line(self.image, self.color_green, 
                        (rect.left, y_half), (rect.right, y_half), 1, )
        
        # Draw vertical markers at FWHM points
        x_left = self._freq_to_x(primary['left_freq'], rect)
        x_right = self._freq_to_x(primary['right_freq'], rect)
        
        # Left marker
        pygame.draw.line(self.image, self.color_green,
                        (x_left, rect.top), (x_left, rect.bottom), 2)
        
        # Right marker
        pygame.draw.line(self.image, self.color_green,
                        (x_right, rect.top), (x_right, rect.bottom), 2)
        
        # Label the half-max dB level
        lbl = self.font_tiny.render("-3dB @ {:.1f} dB".format(half_max_db), 
                                     True, self.color_green)
        self.image.blit(lbl, (rect.left + 4, y_half - 16))

    def _draw_tuning_meter(self, width, height):
        """Large numeric display of primary resonance Q-factor."""
        if not self.resonances:
            return
        
        primary = self.resonances[0]
        q_factor = primary['q_factor']
        
        # Position in top-right corner
        meter_x = width - 180
        meter_y = 40
        
        # Background box
        box_rect = pygame.Rect(meter_x - 10, meter_y - 10, 170, 110)
        pygame.draw.rect(self.image, (20, 20, 20), box_rect)
        pygame.draw.rect(self.image, self.color_yellow, box_rect, 2)
        
        # Title
        title = self.font_small.render("Q FACTOR", True, self.color_yellow)
        self.image.blit(title, (meter_x, meter_y))
        
        # Large Q value
        q_str = "{:.1f}".format(q_factor)
        q_text = self.font_huge.render(q_str, True, self.color_cyan)
        self.image.blit(q_text, (meter_x, meter_y + 25))
        
        # Interpretation hint
        if q_factor > 10:
            hint = "NARROW"
            hint_color = self.color_orange
        elif q_factor > 5:
            hint = "MODERATE"
            hint_color = self.color_yellow
        else:
            hint = "WIDE"
            hint_color = self.color_green
        
        hint_text = self.font_tiny.render(hint, True, hint_color)
        self.image.blit(hint_text, (meter_x + 50, meter_y + 95))

    def _draw_drift_indicator(self, width, height):
        """Show frequency shift from baseline."""
        if not self.resonances or not self.baseline_resonances:
            return
        
        current_freq = self.resonances[0]['frequency']
        baseline_freq = self.baseline_resonances[0]['frequency']
        drift_hz = current_freq - baseline_freq
        drift_mhz = drift_hz / 1e6
        
        # Position below tuning meter
        indicator_x = width - 180
        indicator_y = 160
        
        # Background box
        box_rect = pygame.Rect(indicator_x - 10, indicator_y - 10, 170, 70)
        pygame.draw.rect(self.image, (20, 20, 20), box_rect)
        pygame.draw.rect(self.image, self.color_yellow, box_rect, 2)
        
        # Title
        title = self.font_small.render("DRIFT", True, self.color_yellow)
        self.image.blit(title, (indicator_x, indicator_y))
        
        # Drift value with color coding
        if abs(drift_mhz) < 0.1:
            drift_color = self.color_green  # Stable
        elif abs(drift_mhz) < 0.5:
            drift_color = self.color_yellow  # Minor drift
        else:
            drift_color = self.color_orange  # Significant drift
        
        drift_str = "{:+.2f} MHz".format(drift_mhz)
        drift_text = self.font_medium.render(drift_str, True, drift_color)
        self.image.blit(drift_text, (indicator_x, indicator_y + 25))
        
        # Baseline reference
        ref_text = self.font_tiny.render("from {:.2f} MHz".format(baseline_freq / 1e6), 
                                         True, (150, 150, 150))
        self.image.blit(ref_text, (indicator_x, indicator_y + 50))

    def _draw_trend_graph(self, width, height):
        """Mini graph showing Q-factor trend over last N scans."""
        if len(self.tuning_history) < 2:
            return
        
        # Position in bottom-right
        graph_width = 170
        graph_height = 80
        graph_x = width - graph_width - 10
        graph_y = height - graph_height - 50
        
        # Background
        graph_rect = pygame.Rect(graph_x, graph_y, graph_width, graph_height)
        pygame.draw.rect(self.image, (20, 20, 20), graph_rect)
        pygame.draw.rect(self.image, self.color_yellow, graph_rect, 1)
        
        # Title
        title = self.font_tiny.render("Q TREND", True, self.color_yellow)
        self.image.blit(title, (graph_x + 4, graph_y + 2))
        
        # Plot area
        plot_rect = pygame.Rect(graph_x + 10, graph_y + 18, graph_width - 20, graph_height - 28)
        
        # Extract Q values
        q_values = [h['q_factor'] for h in self.tuning_history]
        q_min = min(q_values)
        q_max = max(q_values)
        q_range = q_max - q_min if q_max != q_min else 1
        
        # Plot points
        points = []
        for i, q in enumerate(q_values):
            x = plot_rect.left + int((i / (len(q_values) - 1)) * plot_rect.width)
            y_norm = (q - q_min) / q_range
            y = plot_rect.bottom - int(y_norm * plot_rect.height)
            points.append((x, y))
        
        # Draw trend line
        if len(points) >= 2:
            pygame.draw.lines(self.image, self.color_cyan, False, points, 2)
        
        # Draw points
        for pt in points:
            pygame.draw.circle(self.image, self.color_cyan, pt, 3)
        
        # Highlight current (last) point
        if points:
            pygame.draw.circle(self.image, self.color_green, points[-1], 4)
        
        # Y-axis labels
        max_lbl = self.font_tiny.render("{:.1f}".format(q_max), True, (150, 150, 150))
        min_lbl = self.font_tiny.render("{:.1f}".format(q_min), True, (150, 150, 150))
        self.image.blit(max_lbl, (graph_x + graph_width - 35, plot_rect.top - 2))
        self.image.blit(min_lbl, (graph_x + graph_width - 35, plot_rect.bottom - 10))

    def update(self, screen):
        """Update and render the widget."""
        if not self.visible:
            return
        
        screen.blit(self.image, self.rect)
        self.dirty = 0
