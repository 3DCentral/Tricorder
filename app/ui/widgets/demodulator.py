"""FM/AM demodulation controller widget"""
import subprocess
import os
import signal
from ui.widgets.sprite import LcarsWidget


class LcarsDemodulator(LcarsWidget):
    """
    Non-visual widget for FM/AM/NBFM demodulation control
    
    This widget manages the rtl_fm process for audio demodulation.
    Although it has no visual representation, it follows the widget
    pattern for consistency with the architecture.
    
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
        
        # Demodulation state
        self.fm_process = None
        self.tuned_in = False
        self.current_frequency = None
        
    def get_demodulation_params(self, freq_mhz):
        """
        Determine optimal demodulation parameters based on frequency
        
        Args:
            freq_mhz: Frequency in MHz
            
        Returns:
            Dictionary with mode, sample_rate, bandwidth, gain, squelch, and mode_name
        """
        # Weather Radio (NOAA): 162.400 - 162.550 MHz
        # Uses narrow-band FM (NBFM) with 12.5 kHz deviation
        if 162.0 <= freq_mhz <= 163.0:
            return {
                'mode': 'fm',           # Narrow-band FM
                'sample_rate': 16000,   # 16 kHz sample rate (increased for better capture)
                'bandwidth': 16000,     # 16 kHz bandwidth
                'gain': 40,             # Specific gain for weak signals
                'squelch': 0,           # No squelch initially (hear everything)
                'mode_name': 'NBFM (Weather Radio)'
            }
        
        # Marine VHF: 156-162 MHz
        # Uses narrow-band FM with 12.5 kHz deviation
        elif 156.0 <= freq_mhz <= 162.0:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,           # Auto gain
                'squelch': 0,
                'mode_name': 'NBFM (Marine VHF)'
            }
        
        # Aviation: 118-137 MHz
        # Uses AM (Amplitude Modulation)
        elif 118.0 <= freq_mhz <= 137.0:
            return {
                'mode': 'am',
                'sample_rate': 12000,
                'bandwidth': 10000,     # 10 kHz for AM aviation
                'gain': None,
                'squelch': 0,
                'mode_name': 'AM (Aviation)'
            }
        
        # 2-meter Ham Radio: 144-148 MHz
        # Uses narrow-band FM with 12.5 kHz or 25 kHz deviation
        elif 144.0 <= freq_mhz <= 148.0:
            return {
                'mode': 'fm',
                'sample_rate': 16000,   # Slightly wider for ham
                'bandwidth': 16000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (2m Ham)'
            }
        
        # Commercial FM Broadcast: 88-108 MHz
        # Uses wide-band FM with 75 kHz deviation
        elif 88.0 <= freq_mhz <= 108.0:
            return {
                'mode': 'wbfm',         # Wide-band FM
                'sample_rate': 200000,  # 200 kHz sample rate
                'bandwidth': 200000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'WBFM (FM Broadcast)'
            }
        
        # PMR446 / FRS / GMRS: 446-467 MHz
        # Uses narrow-band FM
        elif 446.0 <= freq_mhz <= 467.0:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (PMR/FRS/GMRS)'
            }
        
        # 70cm Ham Radio: 420-450 MHz
        # Uses narrow-band FM
        elif 420.0 <= freq_mhz <= 450.0:
            return {
                'mode': 'fm',
                'sample_rate': 16000,
                'bandwidth': 16000,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (70cm Ham)'
            }
        
        # Default: Use narrow-band FM for most applications
        # This is a safe default for unknown frequencies
        else:
            return {
                'mode': 'fm',
                'sample_rate': 12000,
                'bandwidth': 12500,
                'gain': None,
                'squelch': 0,
                'mode_name': 'NBFM (Default)'
            }
    
    def start_demodulation(self, frequency_hz):
        """
        Start FM/AM demodulation at the specified frequency
        
        Args:
            frequency_hz: Frequency in Hz (will be converted to MHz internally)
        """
        # Stop any existing demodulation first
        self.stop_demodulation()
        
        # Convert to MHz
        freq_mhz = frequency_hz / 1e6
        
        # Get optimal parameters for this frequency
        demod_params = self.get_demodulation_params(freq_mhz)
        
        # Print demodulation info
        print("Tuning {} demodulation to {:.3f} MHz...".format(
            demod_params['mode_name'], freq_mhz))
        print("  Mode: {} | Bandwidth: {} kHz | Sample rate: {} kHz".format(
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
            self.fm_process = subprocess.Popen(
                ['bash', '-c', cmd], 
                preexec_fn=os.setsid,
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
        """Stop FM/AM demodulation"""
        if self.tuned_in and self.fm_process:
            try:
                # Kill the process group (kills rtl_fm and play)
                os.killpg(os.getpgid(self.fm_process.pid), signal.SIGTERM)
                print("Demodulation stopped")
            except (OSError, ProcessLookupError, AttributeError) as e:
                print("Demodulation already stopped or could not be stopped: {}".format(e))
            
            self.fm_process = None
        
        self.tuned_in = False
        self.current_frequency = None
    
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
