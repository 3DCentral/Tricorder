#!/usr/bin/env python3
"""
rtl_scan_live.py - Real-time SDR scanner with waterfall generation

Usage:
    python rtl_scan_live.py <center_freq> [sample_rate] [waterfall_lines]

Examples:
    python rtl_scan_live.py 99.5e6           # 99.5 MHz, default settings
    python rtl_scan_live.py 99.5e6 2.4e6     # 99.5 MHz, 2.4 MHz bandwidth
    python rtl_scan_live.py 99.5e6 2.4e6 150 # 5 seconds at 30 updates/sec

Arguments:
    center_freq      - Center frequency in Hz (e.g., 99.5e6 for 99.5 MHz)
    sample_rate      - Sample rate in Hz (default: 2.4e6 = 2.4 MHz bandwidth)
    waterfall_lines  - Number of waterfall lines to keep (default: 150 = 5 sec @ 30Hz)
"""

import sys
import time
import numpy as np
import shutil
from collections import deque
from rtlsdr import RtlSdr

# Configuration
DEFAULT_SAMPLE_RATE = 2.4e6  # 2.4 MHz bandwidth
DEFAULT_WATERFALL_LINES = 150  # 5 seconds at 30 updates/sec
FFT_SIZE = 1024
UPDATE_INTERVAL = 0.0165  # ~60 Hz update rate (16.5ms between updates) - doubled from 30 Hz
GAIN = 4  # Can adjust based on signal strength needs
FREQ_CORRECTION = 60  # PPM correction

# Output file paths
OUTPUT_DIR = "/tmp/"
PSD_FILE = OUTPUT_DIR + "spectrum_live_psd.npy"
PSD_FILE_TEMP = OUTPUT_DIR + "spectrum_live_psd_temp.npy"
WATERFALL_FILE = OUTPUT_DIR + "spectrum_live_waterfall.npy"
WATERFALL_FILE_TEMP = OUTPUT_DIR + "spectrum_live_waterfall_temp.npy"
FREQUENCIES_FILE = OUTPUT_DIR + "spectrum_live_frequencies.npy"
FREQUENCIES_FILE_TEMP = OUTPUT_DIR + "spectrum_live_frequencies_temp.npy"
METADATA_FILE = OUTPUT_DIR + "spectrum_live_metadata.npy"
METADATA_FILE_TEMP = OUTPUT_DIR + "spectrum_live_metadata_temp.npy"


def parse_args():
    """Parse command line arguments"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    center_freq = float(sys.argv[1])
    sample_rate = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SAMPLE_RATE
    waterfall_lines = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_WATERFALL_LINES
    
    return center_freq, sample_rate, waterfall_lines


def setup_sdr(center_freq, sample_rate):
    """Initialize and configure the SDR"""
    print("Initializing SDR...")
    print("  Center frequency: {:.3f} MHz".format(center_freq/1e6))
    print("  Sample rate: {:.3f} MHz".format(sample_rate/1e6))
    print("  Bandwidth: {:.3f} MHz".format(sample_rate/1e6))
    
    sdr = RtlSdr()
    sdr.sample_rate = sample_rate
    sdr.center_freq = int(center_freq)
    sdr.freq_correction = FREQ_CORRECTION
    sdr.gain = GAIN
    
    # Discard initial samples to let hardware settle
    _ = sdr.read_samples(2048)
    
    print("  Gain: {} dB".format(sdr.gain))
    print("SDR initialized successfully!")
    
    return sdr


def compute_psd(samples):
    """Compute Power Spectral Density from IQ samples"""
    # Apply window to reduce spectral leakage
    window = np.hanning(len(samples))
    samples_windowed = samples * window
    
    # Compute FFT
    fft_result = np.fft.fft(samples_windowed)
    fft_shifted = np.fft.fftshift(fft_result)
    
    # Compute power spectral density in dB
    psd = 10 * np.log10(np.abs(fft_shifted)**2 + 1e-10)  # Add small value to avoid log(0)
    
    return psd


def save_data_atomic(data, temp_path, final_path):
    """Save numpy array with atomic write to prevent corruption"""
    np.save(temp_path, data)
    shutil.move(temp_path, final_path)


def main():
    center_freq, sample_rate, waterfall_lines = parse_args()
    
    # Initialize SDR
    sdr = setup_sdr(center_freq, sample_rate)
    
    # Generate frequency axis (only needs to be computed once)
    frequencies = np.fft.fftshift(np.fft.fftfreq(FFT_SIZE, 1/sample_rate)) + center_freq
    
    # Save frequency axis
    save_data_atomic(frequencies, FREQUENCIES_FILE_TEMP, FREQUENCIES_FILE)
    
    # Save metadata as a numpy array for compatibility
    metadata = np.array([center_freq, sample_rate, FFT_SIZE, waterfall_lines, UPDATE_INTERVAL])
    save_data_atomic(metadata, METADATA_FILE_TEMP, METADATA_FILE)
    
    # Initialize waterfall buffer (FIFO queue)
    waterfall_buffer = deque(maxlen=waterfall_lines)
    
    print("\nStarting live scan...")
    print("  FFT size: {}".format(FFT_SIZE))
    print("  Update rate: ~{:.1f} Hz".format(1/UPDATE_INTERVAL))
    print("  Waterfall history: {} lines (~{:.1f} seconds)".format(
        waterfall_lines, waterfall_lines*UPDATE_INTERVAL))
    print("\nWriting data to:")
    print("  PSD: {}".format(PSD_FILE))
    print("  Waterfall: {}".format(WATERFALL_FILE))
    print("  Frequencies: {}".format(FREQUENCIES_FILE))
    print("\nPress Ctrl+C to stop\n")
    
    frame_count = 0
    start_time = time.time()
    last_update = time.time()
    
    try:
        while True:
            # Read samples from SDR
            samples = sdr.read_samples(FFT_SIZE)
            
            # Compute PSD
            psd = compute_psd(samples)
            
            # Add to waterfall buffer
            waterfall_buffer.append(psd)
            
            # Check if it's time to update files
            current_time = time.time()
            if current_time - last_update >= UPDATE_INTERVAL:
                # Save current PSD
                save_data_atomic(psd, PSD_FILE_TEMP, PSD_FILE)
                
                # Save waterfall as 2D array (flip so newest line is at bottom for downward scroll)
                waterfall_array = np.array(waterfall_buffer)
                waterfall_flipped = np.flipud(waterfall_array)  # Flip vertically
                save_data_atomic(waterfall_flipped, WATERFALL_FILE_TEMP, WATERFALL_FILE)
                
                last_update = current_time
                frame_count += 1
                
                # Print status every second
                elapsed = current_time - start_time
                if frame_count % 30 == 0:
                    actual_fps = frame_count / elapsed
                    print("Frame {:6d} | Elapsed: {:6.1f}s | Rate: {:5.1f} Hz | Waterfall: {}/{} lines".format(
                        frame_count, elapsed, actual_fps, len(waterfall_buffer), waterfall_lines))
    
    except KeyboardInterrupt:
        print("\n\nStopping live scan...")
        elapsed = time.time() - start_time
        print("Total frames: {}".format(frame_count))
        print("Total time: {:.1f}s".format(elapsed))
        print("Average rate: {:.1f} Hz".format(frame_count/elapsed))
    
    finally:
        sdr.close()
        print("SDR closed. Goodbye!")


if __name__ == "__main__":
    main()
