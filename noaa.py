#!/usr/bin/env python3
"""
NOAA APT Satellite Receiver - Standalone Development Script

This script handles automatic NOAA weather satellite reception:
1. Predicts satellite passes using TLE data
2. Automatically records during overhead passes
3. Decodes APT images using PURE PYTHON decoder (no external tools needed!)
4. Saves images with metadata

NOAA Satellites:
- NOAA 15: 137.620 MHz
- NOAA 18: 137.9125 MHz  
- NOAA 19: 137.100 MHz

Requirements:
- RTL-SDR dongle
- rtl_fm (from rtl-sdr package)
- sox (for audio processing)
- Python libraries: numpy, scipy, PIL/Pillow
- ephem (for satellite tracking)

NO EXTERNAL APT DECODER NEEDED - includes pure Python decoder!

Optional: Install ephem for satellite pass prediction
    pip3 install ephem --break-system-packages

Usage:
    python3 noaa_apt_receiver.py --record-now --test  # Test 30s recording
    python3 noaa_apt_receiver.py --decode-python myrecording.wav
    
Note: --list-passes requires ephem library and network access for TLE data
"""

import subprocess
import argparse
import time
import os
import sys
import wave
from datetime import datetime, timedelta
from pathlib import Path

# Try to import required libraries
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    print("Warning: numpy not installed. Install with: pip3 install numpy --break-system-packages")
    NUMPY_AVAILABLE = False

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    print("Warning: scipy not installed. Install with: pip3 install scipy --break-system-packages")
    SCIPY_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    print("Warning: PIL/Pillow not installed. Install with: pip3 install Pillow --break-system-packages")
    PIL_AVAILABLE = False

# Try to import satellite tracking library
try:
    import ephem
    TRACKING_AVAILABLE = True
except ImportError:
    print("Warning: ephem library not installed. Install with: pip3 install ephem --break-system-packages")
    TRACKING_AVAILABLE = False


# NOAA satellite frequencies and NORAD IDs
NOAA_SATELLITES = {
    'NOAA-15': {
        'frequency': 137.620e6,
        'norad_id': 25338,
        'tle_name': 'NOAA 15'
    },
    'NOAA-18': {
        'frequency': 137.9125e6,
        'norad_id': 28654,
        'tle_name': 'NOAA 18'
    },
    'NOAA-19': {
        'frequency': 137.100e6,
        'norad_id': 33591,
        'tle_name': 'NOAA 19'
    }
}

# Default observer location (Richmond, VA)
DEFAULT_LOCATION = {
    'lat': '37.5407',  # degrees North
    'lon': '-77.4360',  # degrees West
    'elevation': 50  # meters above sea level
}

# Output directories
OUTPUT_DIR = Path("/tmp/noaa_captures")
WAV_DIR = OUTPUT_DIR / "wav"
IMAGE_DIR = OUTPUT_DIR / "images"


class PythonAPTDecoder:
    """
    Pure Python APT (Automatic Picture Transmission) decoder
    
    No external dependencies except numpy, scipy, and PIL!
    
    APT Format:
    - Two channels (A and B) transmitted simultaneously
    - Each line is 2080 pixels wide (both channels)
    - Sample rate: 4160 samples/second (20800 samples/line * 2 lines/second)
    - Each pixel corresponds to 2 samples at 4160 Hz
    - Sync patterns every line for alignment
    """
    
    # APT Constants
    SAMPLE_RATE = 11025  # Our WAV file sample rate
    SAMPLES_PER_WORK = 5 * SAMPLE_RATE  # Process in 5-second chunks
    SYNC_WORD_SAMPLES = 20  # Width of sync pattern in samples
    
    # APT line structure (at 4160 Hz effective rate)
    # Each line = 0.5 seconds = 2080 samples at 4160 Hz
    # But we're at 11025 Hz, so scale up
    SAMPLES_PER_LINE = int(11025 * 0.5)  # ~5512 samples per line
    
    # Sync pattern for channel A (approximately)
    # In APT, sync is alternating black/white pattern
    SYNC_A_PATTERN = np.array([0, 255, 0, 255, 0, 255, 0, 255] * 4, dtype=np.uint8)
    
    def __init__(self, wav_file):
        """Initialize decoder with WAV file"""
        self.wav_file = Path(wav_file)
        self.samples = None
        self.sample_rate = None
        
    def load_wav(self):
        """Load WAV file and extract samples"""
        print(f"Loading WAV file: {self.wav_file}")
        
        with wave.open(str(self.wav_file), 'rb') as wav:
            # Get WAV parameters
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            self.sample_rate = wav.getframerate()
            n_frames = wav.getnframes()
            
            print(f"  Channels: {n_channels}")
            print(f"  Sample width: {sample_width} bytes")
            print(f"  Sample rate: {self.sample_rate} Hz")
            print(f"  Duration: {n_frames / self.sample_rate:.1f} seconds")
            
            # Read audio data
            audio_data = wav.readframes(n_frames)
            
            # Convert to numpy array
            if sample_width == 1:
                dtype = np.uint8
            elif sample_width == 2:
                dtype = np.int16
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")
            
            samples = np.frombuffer(audio_data, dtype=dtype)
            
            # Convert to float and normalize to 0-1 range
            if dtype == np.int16:
                samples = samples.astype(np.float32) / 32768.0
            else:
                samples = samples.astype(np.float32) / 128.0 - 1.0
            
            self.samples = samples
            
            print(f"  Loaded {len(samples)} samples")
            
            return True
    
    def hilbert_envelope(self, signal):
        """
        Compute envelope of signal using Hilbert transform
        
        APT is amplitude modulated, so we need to extract the envelope
        to get the image data.
        """
        # Use Hilbert transform to get analytic signal
        analytic = signal.hilbert(signal)
        envelope = np.abs(analytic)
        
        return envelope
    
    def resample(self, signal, target_rate):
        """Resample signal to target sample rate"""
        # Calculate resampling ratio
        current_rate = self.sample_rate
        ratio = target_rate / current_rate
        
        # Use scipy's resample
        num_samples = int(len(signal) * ratio)
        resampled = signal.resample(signal, num_samples)
        
        return resampled
    
    def decode_apt_simple(self):
        """
        Simple APT decoder - just demodulate AM signal and reshape into image
        
        This is a simplified version that doesn't do sync detection.
        Good enough for clear passes!
        """
        if self.samples is None:
            self.load_wav()
        
        print("\nDecoding APT image (simple method)...")
        
        # Step 1: AM demodulation - extract envelope
        print("  Step 1: Demodulating AM signal...")
        envelope = self.hilbert_envelope(self.samples)
        
        # Step 2: Low-pass filter to remove carrier remnants
        print("  Step 2: Filtering...")
        # Design low-pass filter at 2400 Hz (APT bandwidth)
        nyquist = self.sample_rate / 2
        cutoff = 2400 / nyquist
        b, a = signal.butter(5, cutoff, btype='low')
        filtered = signal.filtfilt(b, a, envelope)
        
        # Step 3: Resample to APT rate (4160 Hz effective)
        # We'll use 2080 samples per line (each line is 0.5 seconds)
        print("  Step 3: Resampling to APT rate...")
        target_rate = 4160  # APT samples per second
        resampled = self.resample(filtered, target_rate)
        
        # Step 4: Normalize to 0-255 range
        print("  Step 4: Normalizing...")
        # Remove DC offset
        resampled = resampled - np.mean(resampled)
        # Normalize to 0-255
        img_max = np.max(np.abs(resampled))
        if img_max > 0:
            normalized = ((resampled / img_max) * 127.5 + 127.5).astype(np.uint8)
        else:
            normalized = np.zeros_like(resampled, dtype=np.uint8)
        
        # Step 5: Reshape into image
        print("  Step 5: Reshaping into image...")
        # Each line is 2080 samples (both channels A and B)
        samples_per_line = 2080
        num_lines = len(normalized) // samples_per_line
        
        # Trim to exact multiple of line length
        trimmed = normalized[:num_lines * samples_per_line]
        
        # Reshape into 2D array
        image_data = trimmed.reshape((num_lines, samples_per_line))
        
        print(f"  Generated image: {samples_per_line}x{num_lines} pixels")
        
        # Step 6: Split into channels A and B
        # Channel A is left half, Channel B is right half
        channel_a = image_data[:, :1040]
        channel_b = image_data[:, 1040:]
        
        return {
            'full': image_data,
            'channel_a': channel_a,
            'channel_b': channel_b
        }
    
    def save_images(self, decoded, output_base):
        """Save decoded images to PNG files"""
        if not PIL_AVAILABLE:
            print("Error: PIL/Pillow not available for saving images")
            return []
        
        saved_files = []
        
        # Save full image
        full_path = output_base.parent / f"{output_base.name}_full.png"
        img = Image.fromarray(decoded['full'], mode='L')
        img.save(full_path)
        print(f"  Saved: {full_path.name}")
        saved_files.append(full_path)
        
        # Save channel A (visible/IR depending on satellite)
        a_path = output_base.parent / f"{output_base.name}_channel_a.png"
        img_a = Image.fromarray(decoded['channel_a'], mode='L')
        img_a.save(a_path)
        print(f"  Saved: {a_path.name}")
        saved_files.append(a_path)
        
        # Save channel B (IR)
        b_path = output_base.parent / f"{output_base.name}_channel_b.png"
        img_b = Image.fromarray(decoded['channel_b'], mode='L')
        img_b.save(b_path)
        print(f"  Saved: {b_path.name}")
        saved_files.append(b_path)
        
        return saved_files


class NOAAReceiver:
    """NOAA APT satellite receiver"""
    
    def __init__(self, location=None, min_elevation=20):
        """
        Initialize NOAA receiver
        
        Args:
            location: Dict with 'lat', 'lon', 'elevation' (uses DEFAULT_LOCATION if None)
            min_elevation: Minimum elevation angle for useful passes (degrees)
        """
        self.location = location or DEFAULT_LOCATION
        self.min_elevation = min_elevation
        
        # Create output directories
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        WAV_DIR.mkdir(parents=True, exist_ok=True)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Initialize observer
        if TRACKING_AVAILABLE:
            self.observer = ephem.Observer()
            self.observer.lat = str(self.location['lat'])
            self.observer.lon = str(self.location['lon'])
            self.observer.elevation = self.location['elevation']
        
        # TLE data cache
        self.tle_data = {}
        
        print("NOAA APT Receiver initialized")
        print(f"Location: {self.location['lat']}°N, {self.location['lon']}°W")
        print(f"Minimum elevation: {self.min_elevation}°")
        print(f"Output directory: {OUTPUT_DIR}")
    
    def update_tle_data(self):
        """
        Download latest TLE (Two-Line Element) data for NOAA satellites
        
        TLEs are orbital parameters that describe satellite position.
        They should be updated regularly (daily is ideal).
        """
        print("\nUpdating TLE data from Celestrak...")
        
        import urllib.request
        
        try:
            # Download NOAA TLE data
            url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle"
            response = urllib.request.urlopen(url, timeout=10)
            tle_text = response.read().decode('utf-8')
            
            # Parse TLE data
            lines = tle_text.strip().split('\n')
            for i in range(0, len(lines), 3):
                if i + 2 < len(lines):
                    name = lines[i].strip()
                    line1 = lines[i + 1].strip()
                    line2 = lines[i + 2].strip()
                    
                    # Store TLE for each NOAA satellite
                    # Match more flexibly - look for "NOAA" and the number
                    for sat_name, sat_info in NOAA_SATELLITES.items():
                        # Extract number from sat_name (e.g., "NOAA-19" -> "19")
                        sat_number = sat_name.split('-')[1]
                        # Check if TLE name contains "NOAA" and the number
                        if 'NOAA' in name.upper() and sat_number in name:
                            self.tle_data[sat_name] = (name, line1, line2)
                            print(f"  ✓ {sat_name}: {name}")
            
            # Save to file for offline use
            tle_file = OUTPUT_DIR / "noaa_tle.txt"
            with open(tle_file, 'w') as f:
                f.write(tle_text)
            
            print(f"\nTLE data saved to {tle_file}")
            return True
            
        except Exception as e:
            print(f"Error updating TLE data: {e}")
            print("Attempting to load from cached file...")
            
            # Try to load from cache
            tle_file = OUTPUT_DIR / "noaa_tle.txt"
            if tle_file.exists():
                with open(tle_file, 'r') as f:
                    tle_text = f.read()
                
                lines = tle_text.strip().split('\n')
                for i in range(0, len(lines), 3):
                    if i + 2 < len(lines):
                        name = lines[i].strip()
                        line1 = lines[i + 1].strip()
                        line2 = lines[i + 2].strip()
                        
                        for sat_name, sat_info in NOAA_SATELLITES.items():
                            if sat_info['tle_name'] in name:
                                self.tle_data[sat_name] = (name, line1, line2)
                
                print("Loaded TLE data from cache")
                return True
            
            return False
    
    def predict_passes(self, satellite_name, hours_ahead=24, min_passes=5):
        """
        Predict upcoming satellite passes
        
        Args:
            satellite_name: 'NOAA-15', 'NOAA-18', or 'NOAA-19'
            hours_ahead: How many hours to look ahead
            min_passes: Minimum number of passes to find
            
        Returns:
            List of pass dictionaries with rise_time, set_time, max_elevation, etc.
        """
        if not TRACKING_AVAILABLE:
            print("Error: ephem library not available for pass prediction")
            return []
        
        if satellite_name not in self.tle_data:
            print(f"Error: No TLE data for {satellite_name}")
            return []
        
        # Create satellite object from TLE
        name, line1, line2 = self.tle_data[satellite_name]
        satellite = ephem.readtle(name, line1, line2)
        
        passes = []
        self.observer.date = ephem.now()
        end_time = ephem.Date(datetime.now() + timedelta(hours=hours_ahead))
        
        print(f"\nPredicting passes for {satellite_name}...")
        print(f"Search window: {datetime.now()} to {datetime.now() + timedelta(hours=hours_ahead)}")
        
        while self.observer.date < end_time and len(passes) < min_passes:
            try:
                # Compute next pass
                rise_time, rise_azimuth, max_time, max_altitude, set_time, set_azimuth = \
                    self.observer.next_pass(satellite)
                
                # Convert to degrees
                max_elevation = max_altitude * 180.0 / ephem.pi
                
                # Only include passes above minimum elevation
                if max_elevation >= self.min_elevation:
                    pass_info = {
                        'satellite': satellite_name,
                        'rise_time': rise_time.datetime(),
                        'max_time': max_time.datetime(),
                        'set_time': set_time.datetime(),
                        'rise_azimuth': rise_azimuth * 180.0 / ephem.pi,
                        'max_elevation': max_elevation,
                        'set_azimuth': set_azimuth * 180.0 / ephem.pi,
                        'duration': (set_time.datetime() - rise_time.datetime()).total_seconds()
                    }
                    passes.append(pass_info)
                
                # Move to next pass
                self.observer.date = set_time + ephem.minute
                
            except ValueError:
                # No more passes in time window
                break
        
        return passes
    
    def print_passes(self, passes):
        """Print formatted pass predictions"""
        if not passes:
            print("No passes found above minimum elevation")
            return
        
        print("\n" + "="*80)
        print(f"{'SATELLITE':<12} {'RISE TIME':<20} {'MAX ELEV':<10} {'DURATION':<10} {'AZIMUTH':<15}")
        print("="*80)
        
        for p in passes:
            rise_str = p['rise_time'].strftime("%Y-%m-%d %H:%M:%S")
            duration_str = f"{int(p['duration'] / 60)}m {int(p['duration'] % 60)}s"
            azimuth_str = f"{p['rise_azimuth']:.0f}° → {p['set_azimuth']:.0f}°"
            
            print(f"{p['satellite']:<12} {rise_str:<20} {p['max_elevation']:>6.1f}°    {duration_str:<10} {azimuth_str:<15}")
        
        print("="*80 + "\n")
    
    def record_pass(self, satellite_name, duration=None, test_mode=False):
        """
        Record a satellite pass
        
        Args:
            satellite_name: Which satellite to record
            duration: Recording duration in seconds (auto-calculated if None)
            test_mode: If True, record for only 30 seconds for testing
        """
        if satellite_name not in NOAA_SATELLITES:
            print(f"Error: Unknown satellite {satellite_name}")
            return None
        
        sat_info = NOAA_SATELLITES[satellite_name]
        frequency = sat_info['frequency']
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_file = WAV_DIR / f"{satellite_name}_{timestamp}.wav"
        
        if test_mode:
            duration = 30
            print(f"\n*** TEST MODE: Recording for {duration} seconds ***")
        elif duration is None:
            duration = 15 * 60  # Default 15 minutes (covers most passes)
        
        print(f"\nRecording {satellite_name}:")
        print(f"  Frequency: {frequency/1e6:.4f} MHz")
        print(f"  Duration: {duration}s ({duration/60:.1f} minutes)")
        print(f"  Output: {wav_file}")
        
        # rtl_fm command for NOAA APT reception
        # APT is FM, 11025 Hz sample rate works well
        rtl_fm_cmd = [
            'rtl_fm',
            '-f', str(int(frequency)),
            '-s', '60k',  # Sample rate
            '-g', '40',  # Gain (adjust as needed)
            '-p', '0',   # PPM correction
            '-E', 'dc',  # DC blocking
            '-F', '9',   # Filter
            '-A', 'fast', # AGC mode
            '-'          # Output to stdout
        ]
        
        # sox command to resample to 11025 Hz for APT decoding
        sox_cmd = [
            'sox',
            '-t', 'raw',
            '-r', '60k',
            '-e', 's',
            '-b', '16',
            '-c', '1',
            '-V1',
            '-',
            '-t', 'wav',
            str(wav_file),
            'rate', '11025'
        ]
        
        print(f"\nCommand: {' '.join(rtl_fm_cmd)} | {' '.join(sox_cmd)}")
        print("\nRecording started...")
        print("Press Ctrl+C to stop early\n")
        
        try:
            # Start rtl_fm
            rtl_fm_proc = subprocess.Popen(
                rtl_fm_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Start sox
            sox_proc = subprocess.Popen(
                sox_cmd,
                stdin=rtl_fm_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for completion or timeout
            start_time = time.time()
            while time.time() - start_time < duration:
                # Check if processes are still running
                if rtl_fm_proc.poll() is not None or sox_proc.poll() is not None:
                    print("\nError: Recording process terminated unexpectedly")
                    break
                
                # Print progress
                elapsed = time.time() - start_time
                remaining = duration - elapsed
                print(f"\rRecording: {int(elapsed)}s / {duration}s ({int(remaining)}s remaining)  ", end='', flush=True)
                
                time.sleep(1)
            
            print("\n\nStopping recording...")
            
            # Terminate processes
            rtl_fm_proc.terminate()
            sox_proc.terminate()
            
            # Wait for cleanup
            rtl_fm_proc.wait(timeout=5)
            sox_proc.wait(timeout=5)
            
            print(f"Recording saved to: {wav_file}")
            print(f"File size: {wav_file.stat().st_size / 1024 / 1024:.1f} MB")
            
            return wav_file
            
        except KeyboardInterrupt:
            print("\n\nRecording interrupted by user")
            rtl_fm_proc.terminate()
            sox_proc.terminate()
            return wav_file
        
        except Exception as e:
            print(f"\nError during recording: {e}")
            return None
    
    def decode_apt_python(self, wav_file):
        """
        Decode APT image using pure Python decoder
        
        Args:
            wav_file: Path to recorded WAV file
            
        Returns:
            List of generated image files
        """
        if not NUMPY_AVAILABLE or not SCIPY_AVAILABLE or not PIL_AVAILABLE:
            print("Error: Required libraries not available (numpy, scipy, PIL)")
            print("Install with: pip3 install numpy scipy Pillow --break-system-packages")
            return []
        
        print(f"\nDecoding APT image using Python decoder...")
        
        try:
            # Create decoder
            decoder = PythonAPTDecoder(wav_file)
            
            # Decode image
            decoded = decoder.decode_apt_simple()
            
            # Save images
            output_base = IMAGE_DIR / wav_file.stem
            images = decoder.save_images(decoded, output_base)
            
            print(f"\n✓ Python APT decoding successful!")
            print(f"Generated {len(images)} images")
            
            return images
            
        except Exception as e:
            print(f"Error during Python decoding: {e}")
            import traceback
            traceback.print_exc()
            return []


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='NOAA APT Satellite Receiver',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--satellite',
        choices=['NOAA-15', 'NOAA-18', 'NOAA-19'],
        default='NOAA-19',
        help='Satellite to track/record'
    )
    
    parser.add_argument(
        '--min-elevation',
        type=float,
        default=20,
        help='Minimum elevation angle for passes (degrees)'
    )
    
    parser.add_argument(
        '--list-passes',
        action='store_true',
        help='List upcoming passes for all NOAA satellites'
    )
    
    parser.add_argument(
        '--record-next',
        action='store_true',
        help='Wait for and record the next pass automatically'
    )
    
    parser.add_argument(
        '--record-now',
        action='store_true',
        help='Record immediately (for testing or manual operation)'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: record for only 30 seconds'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        help='Recording duration in seconds (default: 900 = 15 minutes)'
    )
    
    parser.add_argument(
        '--decode',
        type=str,
        metavar='WAV_FILE',
        help='Decode an existing WAV file (same as --decode-python)'
    )
    
    parser.add_argument(
        '--decode-python',
        type=str,
        metavar='WAV_FILE',
        help='Decode an existing WAV file using pure Python decoder'
    )
    
    args = parser.parse_args()
    
    # Initialize receiver
    receiver = NOAAReceiver(min_elevation=args.min_elevation)
    
    # Update TLE data (only for pass prediction)
    if args.list_passes or args.record_next:
        if not receiver.update_tle_data():
            print("Warning: Could not update TLE data. Pass predictions may be inaccurate.")
    
    # Decode existing file with Python decoder
    if args.decode_python or args.decode:
        wav_file = Path(args.decode_python or args.decode)
        receiver.decode_apt_python(wav_file)
        return
    
    # List passes
    if args.list_passes:
        print("\nSearching for passes in next 24 hours...\n")
        all_passes = []
        for sat in ['NOAA-15', 'NOAA-18', 'NOAA-19']:
            passes = receiver.predict_passes(sat, hours_ahead=24)
            all_passes.extend(passes)
        
        # Sort by time
        all_passes.sort(key=lambda p: p['rise_time'])
        receiver.print_passes(all_passes)
        return
    
    # Record next pass
    if args.record_next:
        passes = receiver.predict_passes(args.satellite, hours_ahead=24, min_passes=1)
        
        if not passes:
            print(f"No passes found for {args.satellite} in next 24 hours")
            return
        
        next_pass = passes[0]
        receiver.print_passes([next_pass])
        
        # Wait until pass starts
        wait_time = (next_pass['rise_time'] - datetime.now()).total_seconds()
        
        if wait_time > 0:
            print(f"\nWaiting {int(wait_time)}s until pass begins...")
            print("Press Ctrl+C to cancel\n")
            
            try:
                time.sleep(wait_time)
            except KeyboardInterrupt:
                print("\nCancelled by user")
                return
        
        # Record the pass
        duration = int(next_pass['duration']) + 60  # Add 1 minute buffer
        wav_file = receiver.record_pass(args.satellite, duration=duration, test_mode=args.test)
        
        if wav_file and wav_file.exists():
            # Decode the recording
            receiver.decode_apt_python(wav_file)
        
        return
    
    # Record immediately
    if args.record_now:
        wav_file = receiver.record_pass(
            args.satellite,
            duration=args.duration,
            test_mode=args.test
        )
        
        if wav_file and wav_file.exists():
            # Decode the recording
            receiver.decode_apt_python(wav_file)
        
        return
    
    # Default: show help
    parser.print_help()


if __name__ == '__main__':
    main()
