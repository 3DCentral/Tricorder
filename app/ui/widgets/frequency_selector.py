import pygame
import numpy as np
from ui.widgets.sprite import LcarsWidget
from bands import BANDS, get_band_for_freq_hz


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
            self._font_sel   = pygame.font.Font("assets/swiss911.ttf", 18)
            self._font_info  = pygame.font.Font("assets/swiss911.ttf", 22)
            self._font_inst  = pygame.font.Font("assets/swiss911.ttf", 16)
        except Exception:
            self._font_small = pygame.font.SysFont('monospace', 20)
            self._font_band  = pygame.font.SysFont('monospace', 11)
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
        return int(max(0.0, min(1.0, ratio)) * self.display_width)

    def x_to_freq(self, x_pos):
        ratio    = max(0.0, min(1.0, float(x_pos) / self.display_width))
        log_min  = np.log10(self.freq_min)
        log_max  = np.log10(self.freq_max)
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
        if freq_hz >= 1e9:
            return "{:.3f} GHz".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            return "{:.2f} MHz".format(freq_hz / 1e6)
        elif freq_hz >= 1e3:
            return "{:.1f} kHz".format(freq_hz / 1e3)
        else:
            return "{:.0f} Hz".format(freq_hz)

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

        for band in BANDS:
            if band['end'] * 1e6 < self.freq_min or band['start'] * 1e6 > self.freq_max:
                continue
            x_start = self.freq_to_x(band['start'] * 1e6)
            x_end   = self.freq_to_x(band['end']   * 1e6)
            width   = max(x_end - x_start, 1)

            fill = pygame.Surface((width, strip_height))
            fill.set_alpha(band['alpha'])
            fill.fill(band['color'])
            surface.blit(fill, (x_start, y_top + 2))

            if width >= 18:
                lbl = self._font_band.render(band['name'], True, band['color'])
                lx  = x_start + max(0, (width - lbl.get_width()) // 2)
                if lx + lbl.get_width() <= self.display_width:
                    surface.blit(lbl, (lx, y_top + 4))

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

        # Filter to window, keep spacing >= 45 px to avoid crowding
        major = []
        last_x = -999
        for freq in candidates:
            if freq < self.freq_min or freq > self.freq_max:
                continue
            x = self.freq_to_x(freq)
            if x - last_x >= 45:
                major.append(freq)
                last_x = x

        for freq in major:
            x = self.freq_to_x(freq)
            pygame.draw.line(surface, (255, 255, 0),
                             (x, y_base - 20), (x, y_base + 20), 2)
            text = self._font_small.render(self._format_frequency(freq), True, (255, 255, 0))
            surface.blit(text, text.get_rect(center=(x, y_base + 25)))

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
            text    = self._font_sel.render(
                self._format_frequency(self.selected_frequency), True, (255, 255, 0))
            trect   = text.get_rect(center=(self.selected_x, y_base - 50))
            padding = 5
            bg      = pygame.Surface((trect.width + padding*2, trect.height + padding*2))
            bg.set_alpha(200)
            bg.fill((0, 0, 0))
            surface.blit(bg, (trect.x - padding, trect.y - padding))
            surface.blit(text, trect)

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
        """Two-line info bar: sweep info on top, zoom status below."""
        padding = 5

        if self.selected_frequency is None:
            text  = self._font_inst.render(
                "Tap to select a frequency", True, (255, 255, 0))
            trect = text.get_rect(topleft=(10, 14))
            bg    = pygame.Surface((trect.width + padding*2, trect.height + padding*2))
            bg.set_alpha(180)
            bg.fill((0, 0, 0))
            surface.blit(bg, (trect.x - padding, trect.y - padding))
            surface.blit(text, trect)
            return

        # -- Line 1: sweep info + band label --
        band_label  = self._get_band_label(self.selected_frequency)
        band_suffix = "  |  {}".format(band_label) if band_label else ""
        sweep_range = self.get_sweep_range()
        if sweep_range:
            s, e      = sweep_range
            line1     = "Sweeps: {} | Range: {} - {}{}".format(
                self.sweep_steps,
                self._format_frequency(s), self._format_frequency(e),
                band_suffix)
        else:
            line1 = "Sweeps: {} | BW: {:.1f} MHz{}".format(
                self.sweep_steps, self.get_sweep_bandwidth() / 1e6, band_suffix)

        t1    = self._font_info.render(line1, True, (255, 255, 0))
        r1    = t1.get_rect(topleft=(10, 10))
        bg1   = pygame.Surface((r1.width + padding*2, r1.height + padding*2))
        bg1.set_alpha(180)
        bg1.fill((0, 0, 0))
        surface.blit(bg1, (r1.x - padding, r1.y - padding))
        surface.blit(t1, r1)

        # -- Line 2: zoom status --
        if self.zoom_level > 0:
            zoom_factor = self.ZOOM_STEP_FACTOR ** self.zoom_level
            line2 = "ZOOM {:.0f}x  |  {:.3f} - {:.3f} MHz  (v to zoom out)".format(
                zoom_factor, self.freq_min / 1e6, self.freq_max / 1e6)
            color2 = (255, 200, 50)   # amber when zoomed
        else:
            line2  = "^ v zoom  |  < > adjust sweep count"
            color2 = (200, 200, 200)  # dim when at full view

        t2  = self._font_inst.render(line2, True, color2)
        r2  = t2.get_rect(topleft=(10, 42))
        bg2 = pygame.Surface((r2.width + padding*2, r2.height + padding*2))
        bg2.set_alpha(180)
        bg2.fill((0, 0, 0))
        surface.blit(bg2, (r2.x - padding, r2.y - padding))
        surface.blit(t2, r2)

    # ------------------------------------------------------------------
    # Main update / event
    # ------------------------------------------------------------------

    def update(self, screen):
        if not self.visible:
            return
        self.image.fill((0, 0, 0))
        self._draw_band_highlights(self.image)
        self._draw_scale(self.image)
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
