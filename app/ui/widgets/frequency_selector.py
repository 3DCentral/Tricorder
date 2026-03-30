import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
from bands import BANDS, get_band_for_freq_hz
from bookmarks import bookmarks_in_range

# Bookmark tick marks on the scale (distinct from band tint / yellow ticks)
BOOKMARK_TICK_COLOR = (80, 160, 255)


class LcarsFrequencySelector(LcarsWidget):
    """
    Frequency selector widget with logarithmic scale.
    Allows selection of target frequency from 50 MHz to 2.2 GHz (RTL-SDR range).

    ZOOM:
    - Full view on load: 50 MHz - 2.2 GHz
    - Once a frequency is selected, UP/DOWN zoom in/out around that frequency
    - Zoom keeps the log scale; it narrows/widens freq_min/freq_max
    - Clicking always selects at the current zoomed window's coordinate
    """

    FREQ_ABS_MIN   = 50e6
    FREQ_ABS_MAX   = 2.2e9
    H_PAD_PIXELS   = 20      # horizontal padding so end labels don't hug screen edges
    ZOOM_STEP_FACTOR = 2.0   # each step halves the log-span
    MAX_ZOOM         = 8     # 2^8 = 256x maximum zoom

    def __init__(self, pos, size=(640, 144)):
        self.display_width  = size[0]
        self.display_height = size[1]
        self.image = pygame.Surface(size)
        self.image.fill((0, 0, 0))

        LcarsWidget.__init__(self, None, pos, size)

        self.freq_min = self.FREQ_ABS_MIN
        self.freq_max = self.FREQ_ABS_MAX

        self.zoom_level = 0

        self.selected_frequency = None
        self.selected_x         = None
        self.scanning_range     = None

        self.sweep_steps     = 5
        self.min_sweep_steps = 1
        self.max_sweep_steps = 10

        try:
            self._font_small = pygame.font.Font("assets/swiss911.ttf", 20)
            self._font_band  = pygame.font.Font("assets/swiss911.ttf", 11)
            self._font_band_highlight = pygame.font.Font("assets/swiss911.ttf", 22)
            self._font_sel   = pygame.font.Font("assets/swiss911.ttf", 18)
            self._font_info  = pygame.font.Font("assets/swiss911.ttf", 22)
            self._font_inst  = pygame.font.Font("assets/swiss911.ttf", 16)
        except Exception:
            self._font_small = pygame.font.SysFont('monospace', 20)
            self._font_band  = pygame.font.SysFont('monospace', 11)
            self._font_band_highlight = pygame.font.SysFont('monospace', 22)
            self._font_sel   = pygame.font.SysFont('monospace', 18)
            self._font_info  = pygame.font.SysFont('monospace', 22)
            self._font_inst  = pygame.font.SysFont('monospace', 16)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_in(self):
        """Zoom in one step around selected_frequency. Returns True if changed."""
        if self.selected_frequency is None or self.zoom_level >= self.MAX_ZOOM:
            return False
        self.zoom_level += 1
        self._apply_zoom()
        print("Zoom in -> level {} | {:.2f} - {:.2f} MHz".format(
            self.zoom_level, self.freq_min / 1e6, self.freq_max / 1e6))
        return True

    def zoom_out(self):
        """Zoom out one step. Returns True if changed."""
        if self.zoom_level <= 0:
            return False
        self.zoom_level -= 1
        self._apply_zoom()
        print("Zoom out -> level {} | {:.2f} - {:.2f} MHz".format(
            self.zoom_level, self.freq_min / 1e6, self.freq_max / 1e6))
        return True

    def reset_zoom(self):
        """Return to full view."""
        self.zoom_level = 0
        self.freq_min   = self.FREQ_ABS_MIN
        self.freq_max   = self.FREQ_ABS_MAX
        if self.selected_frequency is not None:
            self.selected_x = self.freq_to_x(self.selected_frequency)

    def _apply_zoom(self):
        """Recompute freq_min/freq_max centred on selected_frequency for current zoom_level."""
        if self.selected_frequency is None:
            return

        log_center    = np.log10(self.selected_frequency)
        log_abs_min   = np.log10(self.FREQ_ABS_MIN)
        log_abs_max   = np.log10(self.FREQ_ABS_MAX)
        log_full_span = log_abs_max - log_abs_min

        log_half_span = (log_full_span / 2.0) / (self.ZOOM_STEP_FACTOR ** self.zoom_level)

        log_min = log_center - log_half_span
        log_max = log_center + log_half_span

        # Shift window rather than clip so selection stays centred
        if log_min < log_abs_min:
            log_max += log_abs_min - log_min
            log_min  = log_abs_min
        if log_max > log_abs_max:
            log_min -= log_max - log_abs_max
            log_max  = log_abs_max

        self.freq_min   = 10 ** log_min
        self.freq_max   = 10 ** log_max
        self.selected_x = self.freq_to_x(self.selected_frequency)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def freq_to_x(self, frequency):
        if frequency <= 0:
            return 0
        log_min  = np.log10(self.freq_min)
        log_max  = np.log10(self.freq_max)
        log_freq = np.log10(max(frequency, 1))
        ratio    = (log_freq - log_min) / (log_max - log_min)
        ratio    = max(0.0, min(1.0, ratio))

        # Map to inner width so end labels don't run off the screen
        inner_w = max(1, self.display_width - 2 * self.H_PAD_PIXELS)
        return int(self.H_PAD_PIXELS + ratio * inner_w)

    def x_to_freq(self, x_pos):
        inner_w = max(1.0, float(self.display_width - 2 * self.H_PAD_PIXELS))
        ratio   = (float(x_pos) - self.H_PAD_PIXELS) / inner_w
        ratio   = max(0.0, min(1.0, ratio))

        log_min = np.log10(self.freq_min)
        log_max = np.log10(self.freq_max)
        return 10 ** (log_min + ratio * (log_max - log_min))

    # ------------------------------------------------------------------
    # Public state setters
    # ------------------------------------------------------------------

    def set_selected_frequency(self, frequency):
        self.selected_frequency = frequency
        self.selected_x = self.freq_to_x(frequency)
        sweep_range = self.get_sweep_range()
        if sweep_range:
            self.scanning_range = sweep_range

    def set_scanning_range(self, start_freq, end_freq):
        self.scanning_range = (start_freq, end_freq)

    def clear_scanning_range(self):
        self.scanning_range = None

    # ------------------------------------------------------------------
    # Sweep steps (kept for emf_manager compatibility)
    # ------------------------------------------------------------------

    def adjust_sweep_steps(self, delta):
        new = self.sweep_steps + delta
        if new < self.min_sweep_steps or new > self.max_sweep_steps:
            return False
        self.sweep_steps = new
        return True

    def get_sweep_bandwidth(self):
        return self.sweep_steps * 2.4e6

    def get_sweep_range(self):
        if self.selected_frequency is None:
            return None
        bw         = self.get_sweep_bandwidth()
        start_freq = max(int(self.FREQ_ABS_MIN), int(self.selected_frequency - bw / 2))
        end_freq   = min(int(self.FREQ_ABS_MAX), int(self.selected_frequency + bw / 2))
        return (start_freq, end_freq)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_frequency(self, freq_hz):
        """Full format with unit (for tooltips/logs)."""
        if freq_hz >= 1e9:
            return "{:.3f} GHz".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            return "{:.2f} MHz".format(freq_hz / 1e6)
        elif freq_hz >= 1e3:
            return "{:.1f} kHz".format(freq_hz / 1e3)
        else:
            return "{:.0f} Hz".format(freq_hz)

    def _format_frequency_short(self, freq_hz):
        """Numeric only, no unit — use when unit is shown once (scale/info bar)."""
        if freq_hz >= 1e9:
            return "{:.2f}".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            m = freq_hz / 1e6
            return "{:.1f}".format(m) if m < 1000 else "{:.0f}".format(m)
        elif freq_hz >= 1e3:
            return "{:.1f}".format(freq_hz / 1e3)
        else:
            return "{:.0f}".format(freq_hz)

    def _get_band_label(self, freq_hz):
        if freq_hz is None:
            return None
        band = get_band_for_freq_hz(freq_hz)
        return band['name'] if band else None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_band_highlights(self, surface):
        y_top        = 0
        y_base       = self.display_height - 40
        strip_height = y_base - y_top - 4
        strip_y      = y_top + 2

        for band in BANDS:
            if band['end'] * 1e6 < self.freq_min or band['start'] * 1e6 > self.freq_max:
                continue
            x_start = self.freq_to_x(band['start'] * 1e6)
            x_end   = self.freq_to_x(band['end']   * 1e6)
            width   = max(x_end - x_start, 1)

            fill = pygame.Surface((width, strip_height))
            fill.set_alpha(band['alpha'])
            fill.fill(band['color'])
            surface.blit(fill, (x_start, strip_y))

            lbl = self._font_band_highlight.render(band['name'], True, band['color'])
            lw  = lbl.get_width()
            if width >= lw + 8:
                lx = x_start + max(0, (width - lw) // 2)
                if lx + lw <= self.display_width:
                    ly = strip_y + (strip_height - lbl.get_height()) // 2
                    surface.blit(lbl, (lx, ly))

    def _draw_bookmark_ticks(self, surface):
        """Vertical blue ticks at bookmark frequencies visible in the current window."""
        y_base = self.display_height - 40
        y_top = 4
        tick_half = 22
        for b in bookmarks_in_range(self.freq_min, self.freq_max):
            x = self.freq_to_x(b["freq_hz"])
            pygame.draw.line(
                surface,
                BOOKMARK_TICK_COLOR,
                (x, y_top),
                (x, y_base + tick_half),
                2,
            )

    def _draw_scale(self, surface):
        y_base = self.display_height - 40
        pygame.draw.line(surface, (255, 255, 0),
                         (0, y_base), (self.display_width, y_base), 3)

        # Build candidate tick list appropriate to visible span
        span_hz   = self.freq_max - self.freq_min
        span_mhz  = span_hz / 1e6

        base = [
            50e6, 60e6, 70e6, 80e6,
            100e6, 120e6, 150e6, 200e6, 250e6, 300e6, 400e6, 500e6,
            600e6, 700e6, 800e6, 900e6,
            1e9, 1.1e9, 1.2e9, 1.3e9, 1.4e9, 1.5e9,
            1.6e9, 1.7e9, 1.8e9, 1.9e9, 2e9, 2.2e9,
        ]
        if span_mhz < 500:
            base += [f * 1e6 for f in range(50, 2201, 10)]
        if span_mhz < 100:
            base += [f * 1e6 for f in range(50, 2201, 5)]
        if span_mhz < 20:
            base += [f * 1e6 for f in range(50, 2201, 1)]
        if span_mhz < 5:
            base += [f * 1e6 + m * 100e3 for f in range(50, 2201) for m in range(10)]

        candidates = sorted(set(base))

        # Min spacing so short numeric labels don't overlap (no "MHz"/"GHz" per tick)
        min_tick_px = 50
        major = []
        last_x = -999
        for freq in candidates:
            if freq < self.freq_min or freq > self.freq_max:
                continue
            x = self.freq_to_x(freq)
            # Always include ticks at the current window edges (e.g. 50 MHz, 2.2 GHz),
            # even if they are closer than min_tick_px to the previous tick.
            is_left_edge = abs(freq - self.freq_min) <= 1e3
            is_right_edge = abs(freq - self.freq_max) <= 1e3
            if is_left_edge or is_right_edge or x - last_x >= min_tick_px:
                major.append(freq)
                last_x = x

        # Minor (unlabeled) ticks between majors — log-spaced to show log scale
        minor_freqs = []
        for i in range(len(major) - 1):
            log_lo = np.log10(major[i])
            log_hi = np.log10(major[i + 1])
            for j in range(1, 4):  # 3 minor ticks between each major pair
                log_m = log_lo + (log_hi - log_lo) * j / 4
                minor_freqs.append(10 ** log_m)

        minor_y_half = 10   # short tick: 10 px above/below baseline
        major_y_half = 20   # major tick: 20 px above/below baseline
        minor_color = (200, 200, 100)  # slightly dimmer yellow

        # Draw minor ticks first (so majors draw on top)
        for freq in minor_freqs:
            if freq < self.freq_min or freq > self.freq_max:
                continue
            x = self.freq_to_x(freq)
            pygame.draw.line(surface, minor_color,
                             (x, y_base - minor_y_half), (x, y_base + minor_y_half), 1)

        for freq in major:
            x = self.freq_to_x(freq)
            pygame.draw.line(surface, (255, 255, 0),
                             (x, y_base - major_y_half), (x, y_base + major_y_half), 2)
            label = self._format_frequency_short(freq)
            text = self._font_small.render(label, True, (255, 255, 0))
            surface.blit(text, text.get_rect(center=(x, y_base + 25)))

        # Unit labels below the tick labels so they're not obscured (stay within widget height)
        y_unit = y_base + 28
        if self.freq_max >= 1e9 and self.freq_min < 1e9:
            unit_l = self._font_band.render("MHz", True, (180, 180, 180))
            unit_r = self._font_band.render("GHz", True, (180, 180, 180))
            surface.blit(unit_l, (4, y_unit))
            surface.blit(unit_r, (self.display_width - unit_r.get_width() - 4, y_unit))
        elif self.freq_max >= 1e9:
            unit_r = self._font_band.render("GHz", True, (180, 180, 180))
            surface.blit(unit_r, (self.display_width - unit_r.get_width() - 4, y_unit))
        else:
            unit_l = self._font_band.render("MHz", True, (180, 180, 180))
            surface.blit(unit_l, (4, y_unit))

    def _draw_selection_marker(self, surface):
        if self.selected_x is None:
            return
        y_base = self.display_height - 40
        pygame.draw.polygon(surface, (255, 255, 0), [
            (self.selected_x,     y_base - 20),
            (self.selected_x - 8, y_base - 35),
            (self.selected_x + 8, y_base - 35),
        ])
        if self.selected_frequency:
            # Short form; unit is clear from scale/info bar
            sel_str = self._format_frequency_short(self.selected_frequency)
            if self.selected_frequency >= 1e9:
                sel_str += " G"
            elif self.selected_frequency >= 1e6:
                sel_str += " M"
            text    = self._font_sel.render(sel_str, True, (255, 255, 0))
            trect   = text.get_rect(center=(self.selected_x, y_base - 50))
            padding = 5
            bg      = pygame.Surface((trect.width + padding*2, trect.height + padding*2))
            bg.set_alpha(200)
            bg.fill((0, 0, 0))
            #surface.blit(bg, (trect.x - padding, trect.y - padding))
            #surface.blit(text, trect)

    def _draw_scanning_highlight(self, surface):
        if self.scanning_range is None:
            return
        start_freq, end_freq = self.scanning_range
        x_start = self.freq_to_x(start_freq)
        x_end   = self.freq_to_x(end_freq)
        y_base  = self.display_height - 40
        width   = x_end - x_start
        if width > 0:
            hl = pygame.Surface((width, 30))
            hl.set_alpha(100)
            hl.fill((255, 153, 0))
            surface.blit(hl, (x_start, y_base - 15))

    def _draw_info_bar(self, surface):
        """Single-line info bar: sweep/range (or BW) and band."""
        padding = 5

        if self.selected_frequency is None:
            text  = self._font_inst.render(
                "Tap to select a frequency", True, (255, 255, 0))
            trect = text.get_rect(topleft=(10, 0))
            bg    = pygame.Surface((trect.width + padding*2, trect.height + padding*2))
            bg.set_alpha(180)
            bg.fill((0, 0, 0))
            surface.blit(bg, (trect.x - padding, trect.y - padding))
            surface.blit(text, trect)
            return

        # -- Line 1: sweep info + band label (unit once per range) --
        band_label  = self._get_band_label(self.selected_frequency)
        band_suffix = "  |  {}".format(band_label) if band_label else ""
        sweep_range = self.get_sweep_range()
        if sweep_range:
            s, e = sweep_range
            unit = "GHz" if s >= 1e9 else "MHz"
            line1 = "Sweeps: {} | Range: {} - {} {}{}".format(
                self.sweep_steps,
                self._format_frequency_short(s), self._format_frequency_short(e),
                unit, band_suffix)
        else:
            line1 = "Sweeps: {} | BW: {:.1f} MHz{}".format(
                self.sweep_steps, self.get_sweep_bandwidth() / 1e6, band_suffix)

        t1    = self._font_info.render(line1, True, (255, 255, 0))
        r1    = t1.get_rect(topleft=(10, 0))
        bg1   = pygame.Surface((r1.width + padding*2, r1.height + padding*2))
        bg1.set_alpha(180)
        bg1.fill((0, 0, 0))
        surface.blit(bg1, (r1.x - padding, r1.y - padding))
        surface.blit(t1, r1)

    # ------------------------------------------------------------------
    # Main update / event
    # ------------------------------------------------------------------

    def update(self, screen):
        if not self.visible:
            return
        self.image.fill((0, 0, 0))
        self._draw_band_highlights(self.image)
        self._draw_scale(self.image)
        self._draw_bookmark_ticks(self.image)
        self._draw_scanning_highlight(self.image)
        self._draw_selection_marker(self.image)
        self._draw_info_bar(self.image)
        screen.blit(self.image, self.rect)
        self.dirty = 0

    def handleEvent(self, event, clock):
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                x_rel     = event.pos[0] - self.rect.left
                frequency = self.x_to_freq(x_rel)
                self.set_selected_frequency(frequency)
                print("Selected: {}".format(self._format_frequency(frequency)))
                return True
        return False
