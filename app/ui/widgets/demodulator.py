"""FM/AM demodulation controller widget with filter width integration

CHANGES FROM ORIGINAL:
- Now uses filter width from waterfall display for demodulation bandwidth
- Increased default bandwidths to match wider filter options
- Added method to set bandwidth dynamically
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
        # Uses narrow-band FM (NBFM) with 12.5 kHz deviation
        if 162.0 <= freq_mhz <= 163.0:
            base_params = {
                'mode': 'fm',           # Narrow-band FM
                'sample_rate': 16000,   # 16 kHz sample rate
                'bandwidth': 16000,     # 16 kHz bandwidth (base)
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
        
        # Marine VHF: 156-162 MHz
        # Uses narrow-band FM with 12.5 kHz deviation
        elif 156.0 <= freq_mhz <= 162.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
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
        elif 118.0 <= freq_mhz <= 137.0:
            base_params = {
                'mode': 'am',
                'sample_rate': 12000,
                'bandwidth': 10000,
                'gain': None,
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
        
        # 70cm Ham Radio: 420-450 MHz
        # Uses narrow-band FM
        elif 420.0 <= freq_mhz <= 450.0:
            base_params = {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
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
        if filter_width_hz is not None:
            # Use the filter width from waterfall display
            base_params['bandwidth'] = filter_width_hz
            base_params['sample_rate'] = max(base_params['sample_rate'], filter_width_hz)
            
            # Add filter width info to mode name
            if filter_width_hz >= 1000:
                base_params['mode_name'] += " ({:.1f} kHz)".format(filter_width_hz / 1000)
            else:
                base_params['mode_name'] += " ({:.0f} Hz)".format(filter_width_hz)
        
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
            lines.append("Filter: Custom")
        
        return lines
    
    def start_demodulation(self, frequency_hz, filter_width_hz=None):
        """
        Start FM/AM demodulation at the specified frequency with optional filter width
        
        Args:
            frequency_hz: Frequency in Hz (will be converted to MHz internally)
            filter_width_hz: Filter width in Hz (from waterfall), or None for auto
        """
        # Stop any existing demodulation first
        self.stop_demodulation()
        
        # Convert to MHz
        freq_mhz = frequency_hz / 1e6
        
        # Get optimal parameters for this frequency (with filter width override)
        demod_params = self.get_demodulation_params(freq_mhz, filter_width_hz)
        
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
        cmd = ' '.join(cmd_parts) + ' 2>&1'  # Capture stderr too
        
        print("  Full command: {}".format(cmd))
        
        try:
            # Start demodulation process
            self.fm_process = self.process_manager.start_process(
                'demodulator',
                ['bash', '-c', cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            
            self.tuned_in = True
            self.current_frequency = frequency_hz
            
            print("Demodulation started (PID: {})".format(self.fm_process.pid))
            
        except Exception as e:
            print("Failed to start demodulation: {}".format(e))
            self.tuned_in = False
            self.fm_process = None
    
    def stop_demodulation(self):
        """Stop FM demodulation"""
        if self.tuned_in:
            self.process_manager.kill_process('demodulator')
            self.fm_process = None
        
        self.tuned_in = False
        self.current_frequency = None
        self.current_bandwidth = None
    
    def is_active(self):
        """
        Check if demodulation is currently running
        
        Returns:
            bool: True if demodulation is active, False otherwise
        """
        return self.tuned_in
    
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
