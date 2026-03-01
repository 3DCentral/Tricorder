"""FM/AM demodulation controller widget with filter width integration

FIXES APPLIED:
1. NOAA Weather: Increased default bandwidth to 30 kHz (was 16 kHz)
2. Added rtl_fm -F flag to actually set bandwidth (was missing!)
3. Added minimum bandwidth checks to prevent rtl_fm crashes
4. Improved sample rate calculations
5. Added public safety bands
"""
import subprocess
import os
import signal
from ui.widgets.sprite import LcarsWidget
from ui.widgets.process_manager import get_process_manager

class LcarsDemodulator(LcarsWidget):
    """
    Non-visual widget for FM/AM/NBFM demodulation control
    
    This widget manages the rtl_fm process for audio demodulation.
    Now integrated with filter width control for dynamic bandwidth adjustment.
    
    Note: Must set self.image = None BEFORE calling parent __init__.
    Must also pass valid color (not None) and size >= 1x1 because
    LcarsWidget creates a Surface and calls fill(color) on it.
    We use (0,0,0) black and 1x1 size since we never display it.
    """
    
    def __init__(self):
        # Set image to None BEFORE calling parent init (required by LcarsWidget)
        self.image = None
        
        # Non-visual widget - pass black color and 1x1 size (minimal surface)
        # Color must be valid for pygame.Surface.fill() even though we don't display it
        LcarsWidget.__init__(self, (0, 0, 0), (0, 0), (1, 1))
        self.process_manager = get_process_manager()
        
        # Demodulation state
        self.fm_process = None
        self.tuned_in = False
        self.current_frequency = None
        self.current_bandwidth = None  # Track current demodulation bandwidth
        
    def get_demodulation_params(self, freq_mhz, filter_width_hz=None):
        """
        Determine optimal demodulation parameters based on frequency and filter width
        
        Args:
            freq_mhz: Frequency in MHz
            filter_width_hz: Filter width in Hz (from waterfall), or None for auto
            
        Returns:
            Dictionary with mode, sample_rate, bandwidth, gain, squelch, mode_name,
            band_name, and band_description
        """
        # Weather Radio (NOAA): 162.400 - 162.550 MHz
        # Uses narrow-band FM with WIDER deviation than typical NBFM
        # NOAA actual bandwidth: ~16 kHz audio, Â±5 kHz deviation = ~25 kHz total
        # But works better with 30-40 kHz filter to capture full signal
        if 162.0 <= freq_mhz <= 163.0:
            base_params = {
                'mode': 'fm',           # Narrow-band FM (NOT wbfm!)
                'sample_rate': 48000,   # 48 kHz sample rate (plenty of headroom)
                'bandwidth': 40000,     # 40 kHz bandwidth (matches GQRX)
                'min_bandwidth': 15000, # Minimum 15 kHz (reduced from 25k)
                'gain': 40,             # Specific gain for weak signals
                'squelch': 0,           # No squelch initially
                'mode_name': 'NBFM (Weather Radio)',
                'band_name': 'NOAA Weather Radio',
                'band_description': [
                    'Continuous weather',
                    'broadcasts, warnings,',
                    'and forecasts'
                ]
            }
        
        # Public Safety VHF: 154-158 MHz (analog systems)
        # NEW: Added public safety support
        elif 154.0 <= freq_mhz <= 158.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Public Safety VHF)',
                'band_name': 'Public Safety VHF',
                'band_description': [
                    'Police, fire, EMS',
                    'and emergency',
                    'services (analog)'
                ]
            }
        
        # Marine VHF: 156-162 MHz
        # Uses narrow-band FM with 12.5 kHz deviation
        elif 156.0 <= freq_mhz <= 162.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Marine VHF)',
                'band_name': 'Marine VHF Radio',
                'band_description': [
                    'Ship-to-ship and',
                    'ship-to-shore',
                    'communications'
                ]
            }
        
        # Aviation: 118-137 MHz
        # Uses AM (Amplitude Modulation)
        # AM demodulation in rtl_fm works better with a higher sample rate —
        # 48 kHz gives the demodulator enough headroom above the 8 kHz audio
        # bandwidth for clean envelope detection.
        elif 118.0 <= freq_mhz <= 137.0:
            base_params = {
                'mode': 'am',
                'sample_rate': 48000,   # 48 kHz: AM needs headroom above audio BW
                'bandwidth': 10000,
                'min_bandwidth': 8000,
                'gain': 40,             # Fixed gain: AGC fights AM envelope detection
                'squelch': 0,
                'mode_name': 'AM (Aviation)',
                'band_name': 'Aviation Band',
                'band_description': [
                    'Air traffic control,',
                    'pilot communications,',
                    'and ATIS broadcasts'
                ]
            }
        
        # 2-meter Ham Radio: 144-148 MHz
        # Uses narrow-band FM with 12.5 kHz or 25 kHz deviation
        elif 144.0 <= freq_mhz <= 148.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (2m Ham)',
                'band_name': '2m Ham Radio (VHF)',
                'band_description': [
                    'Amateur radio',
                    'repeaters and',
                    'simplex operations'
                ]
            }
        
        # Commercial FM Broadcast: 88-108 MHz
        # Uses wide-band FM with 75 kHz deviation
        elif 88.0 <= freq_mhz <= 108.0:
            base_params = {
                'mode': 'wbfm',         # Wide-band FM
                'sample_rate': 200000,  # 200 kHz sample rate
                'bandwidth': 200000,
                'min_bandwidth': 150000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'WBFM (FM Broadcast)',
                'band_name': 'FM Broadcast Radio',
                'band_description': [
                    'Commercial radio',
                    'stations with music',
                    'and talk programming'
                ]
            }
        
        # PMR446 / FRS / GMRS: 446-467 MHz
        # Uses narrow-band FM
        elif 446.0 <= freq_mhz <= 467.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (PMR/FRS/GMRS)',
                'band_name': 'PMR446/FRS/GMRS',
                'band_description': [
                    'Personal mobile radio,',
                    'family radio service,',
                    'and walkie-talkies'
                ]
            }
        
        # Public Safety UHF: 453-470 MHz
        # NEW: Added public safety UHF support
        elif 453.0 <= freq_mhz <= 470.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Public Safety UHF)',
                'band_name': 'Public Safety UHF',
                'band_description': [
                    'Police, fire, EMS,',
                    'business band,',
                    'taxis and security'
                ]
            }
        
        # 70cm Ham Radio: 420-450 MHz
        # Uses narrow-band FM
        elif 420.0 <= freq_mhz <= 450.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (70cm Ham)',
                'band_name': '70cm Ham Radio (UHF)',
                'band_description': [
                    'Amateur radio UHF',
                    'repeaters and',
                    'satellite operations'
                ]
            }
        
        # Default: Use narrow-band FM for most applications
        else:
            base_params = {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'min_bandwidth': 10000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Default)',
                'band_name': 'Unknown Band',
                'band_description': [
                    'Unknown frequency',
                    'range - using',
                    'default NBFM mode'
                ]
            }
        
        # OVERRIDE bandwidth with filter width if provided
        # CRITICAL FIX: Enforce minimum bandwidth to prevent rtl_fm crashes
        if filter_width_hz is not None:
            # Get minimum bandwidth for this mode
            min_bw = base_params.get('min_bandwidth', 8000)
            
            # Clamp filter width to minimum
            if filter_width_hz < min_bw:
                print("WARNING: Filter width {:.0f} Hz too narrow for this mode".format(filter_width_hz))
                print("         Using minimum bandwidth: {:.0f} Hz".format(min_bw))
                actual_bandwidth = min_bw
            else:
                actual_bandwidth = filter_width_hz
            
            # Use the filter width from waterfall display (clamped to minimum)
            base_params['bandwidth'] = actual_bandwidth
            
            # CRITICAL FIX: Sample rate must be significantly higher than bandwidth
            # rtl_fm needs headroom for filter rolloff
            # Rule: sample_rate >= bandwidth * 2 (for proper filtering)
            minimum_sample_rate = int(actual_bandwidth * 2)
            base_params['sample_rate'] = max(base_params['sample_rate'], minimum_sample_rate)
            
            # Add filter width info to mode name
            if actual_bandwidth >= 1000:
                base_params['mode_name'] += " ({:.1f} kHz)".format(actual_bandwidth / 1000)
            else:
                base_params['mode_name'] += " ({:.0f} Hz)".format(actual_bandwidth)
        
        return base_params
    
    def get_demodulation_info(self, freq_hz, filter_width_hz=None):
        """
        Get formatted demodulation information for display
        
        Args:
            freq_hz: Frequency in Hz (or None)
            filter_width_hz: Filter width in Hz (from waterfall), or None
            
        Returns:
            List of strings suitable for LcarsTextDisplay.set_lines()
        """
        if freq_hz is None:
            return [
                "DEMODULATION INFO",
                "",
                "Select a frequency",
                "to see protocols"
            ]
        
        # Get demodulation parameters
        freq_mhz = freq_hz / 1e6
        params = self.get_demodulation_params(freq_mhz, filter_width_hz)
        
        # Build info display
        lines = [
            "DEMOD: {:.3f} MHz".format(freq_mhz),
            "",
        ]
        
        # Add active indicator if demodulation is running
        if self.is_active():
            lines.append(">>> ACTIVE <<<")
            lines.append("")
        
        # Add mode name
        lines.append("Mode: {}".format(params['mode_name']))
        lines.append("")
        
        # Add technical details
        if params['bandwidth'] >= 1000:
            lines.append("BW: {:.1f} kHz".format(params['bandwidth'] / 1000))
        else:
            lines.append("BW: {:.0f} Hz".format(params['bandwidth']))
        
        if params['sample_rate'] >= 1000:
            lines.append("SR: {:.0f} kHz".format(params['sample_rate'] / 1000))
        else:
            lines.append("SR: {:.0f} Hz".format(params['sample_rate']))
        
        if params.get('gain') is not None:
            lines.append("Gain: {} dB".format(params['gain']))
        else:
            lines.append("Gain: Auto")
        
        # Add band description
        lines.append("")
        lines.append(params['band_name'])
        lines.append("")
        
        # Add detailed description (already formatted as list)
        lines.extend(params['band_description'])
        
        # Add filter width note if using custom width
        if filter_width_hz is not None:
            lines.append("")
            # Check if we had to clamp it
            min_bw = params.get('min_bandwidth', 8000)
            if filter_width_hz < min_bw:
                lines.append("Filter: {} Hz (clamped)".format(int(params['bandwidth'])))
                lines.append("Min BW: {} Hz".format(min_bw))
            else:
                lines.append("Filter: Custom")
        
        return lines
    
    def start_demodulation(self, frequency_hz, filter_width_hz=None, force_mode=None):
        """
        Start FM/AM demodulation at the specified frequency with optional filter width.
        
        Args:
            frequency_hz:    Frequency in Hz
            filter_width_hz: Filter width in Hz (from waterfall), or None for auto
            force_mode:      Override band mode: 'am', 'fm', or 'wbfm'. None = auto.
        """
        # Stop any existing demodulation first
        self.stop_demodulation()
        
        # Convert to MHz
        freq_mhz = frequency_hz / 1e6
        
        # Get optimal parameters for this frequency (with filter width override)
        demod_params = self.get_demodulation_params(freq_mhz, filter_width_hz)
        
        # Apply forced mode override if requested
        if force_mode in ('am', 'fm', 'wbfm'):
            demod_params['mode'] = force_mode
            labels = {'am': 'AM (Manual)', 'fm': 'NBFM (Manual)', 'wbfm': 'WBFM (Manual)'}
            demod_params['mode_name'] = labels[force_mode]
            if force_mode == 'wbfm':
                demod_params['sample_rate'] = max(demod_params['sample_rate'], 200000)
                demod_params['bandwidth']   = max(demod_params['bandwidth'], 150000)
            elif force_mode == 'am':
                demod_params['sample_rate'] = max(demod_params['sample_rate'], 48000)

        # Store current bandwidth
        self.current_bandwidth = demod_params['bandwidth']
        
        # Print demodulation info
        print("Tuning {} demodulation to {:.3f} MHz...".format(
            demod_params['mode_name'], freq_mhz))
        print("  Mode: {} | Bandwidth: {:.1f} kHz | Sample rate: {:.1f} kHz".format(
            demod_params['mode'],
            demod_params['bandwidth'] / 1000,
            demod_params['sample_rate'] / 1000))
        
        # Build rtl_fm command with appropriate parameters
        cmd_parts = [
            'rtl_fm',
            '-f {}e6'.format(freq_mhz),
            '-M {}'.format(demod_params['mode']),
            '-s {}'.format(int(demod_params['sample_rate'])),
        ]
        
        # CRITICAL FIX: Add -F flag to set bandwidth filter
        # This was MISSING and causing bandwidth setting to be ignored!
        # Note: Only FM modes support -F flag (not AM)
        if demod_params['mode'] in ['fm', 'wbfm']:
            cmd_parts.append('-F {}'.format(int(demod_params['bandwidth'])))
            print("  Filter: {:.1f} kHz".format(demod_params['bandwidth'] / 1000))
        
        # Add gain if specified
        if demod_params.get('gain') is not None:
            cmd_parts.append('-g {}'.format(demod_params['gain']))
            print("  Gain: {} dB".format(demod_params['gain']))
        else:
            print("  Gain: Auto")
        
        # Add squelch if specified
        if demod_params.get('squelch', 0) > 0:
            cmd_parts.append('-l {}'.format(demod_params['squelch']))
            print("  Squelch: {}".format(demod_params['squelch']))
        
        # Add frequency correction (PPM)
        cmd_parts.append('-p 0')  # PPM correction (0 = no correction)
        
        # Resample and pipe to audio
        cmd_parts.extend([
            '-r 48000',  # Resample to 48kHz
            '-',
            '|',
            'play -t raw -r 48k -es -b 16 -c 1 -V1 -'
        ])
        
        # Build full command
        # Note: ProcessManager discards stdout/stderr via DEVNULL so no
        # pipe-buffer deadlock can occur.  No shell-level redirect needed.
        cmd = ' '.join(cmd_parts)
        
        print("  Full command: {}".format(cmd))
        
        try:
            # Start demodulation process
            self.fm_process = self.process_manager.start_process(
                'demodulator',
                ['bash', '-c', cmd]
            )
            
            self.tuned_in = True
            self.current_frequency = frequency_hz
            
            print("Demodulation started (PID: {})".format(self.fm_process.pid))
            
        except Exception as e:
            print("Failed to start demodulation: {}".format(e))
            self.tuned_in = False
            self.fm_process = None
    
    def stop_demodulation(self):
        """Stop FM demodulation and always reset state"""
        if self.tuned_in:
            self.process_manager.kill_process('demodulator')
        
        # Always clear state unconditionally â€” if kill_process failed or
        # the process was already dead, we still need to reset so the next
        # RECORD press takes the start path.
        self.fm_process = None
        self.tuned_in = False
        self.current_frequency = None
        self.current_bandwidth = None
    
    def is_active(self):
        """
        Check if demodulation is currently running.
        
        Polls the actual process so that a crashed or hung rtl_fm is
        detected immediately rather than leaving tuned_in stuck at True.
        
        Returns:
            bool: True if demodulation is active, False otherwise
        """
        if not self.tuned_in:
            return False
        
        # If the process exited on its own, clean up immediately
        if self.fm_process is not None and self.fm_process.poll() is not None:
            print("Demodulator: rtl_fm exited unexpectedly (code: {})".format(
                self.fm_process.poll()))
            self.fm_process = None
            self.tuned_in = False
            self.current_frequency = None
            self.current_bandwidth = None
            return False
        
        return True
    
    def get_current_frequency(self):
        """
        Get the current demodulation frequency
        
        Returns:
            float: Frequency in Hz, or None if not demodulating
        """
        return self.current_frequency
    
    def get_current_bandwidth(self):
        """
        Get the current demodulation bandwidth
        
        Returns:
            float: Bandwidth in Hz, or None if not demodulating
        """
        return self.current_bandwidth
    
    def update(self, screen):
        """
        Widget update method (required by LcarsWidget)
        
        This widget is non-visual, so this method does nothing.
        """
        pass
    
    def handleEvent(self, event, clock):
        """
        Widget event handler (required by LcarsWidget)
        
        This widget doesn't handle events, so this method does nothing.
        
        Returns:
            bool: Always False (event not handled)
        """
        return False
