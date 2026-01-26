#!/usr/bin/env python3
"""
rtl_scan_live.py - Real-time SDR scanner with waterfall generation - FIXED VERSION

BUG FIXES:
1. Increased GAIN from 4 to 40 dB (matches working rtl_scan_2.py)
2. Added DC spike removal using interpolation
3. Increased FFT_SIZE for better resolution
4. Added averaging for smoother display

Usage:
    python rtl_scan_live.py <center_freq> [sample_rate] [waterfall_lines]

Examples:
    python rtl_scan_live.py 99.5e6           # 99.5 MHz, default settings
    python rtl_scan_live.py 99.5e6 2.4e6     # 99.5 MHz, 2.4 MHz bandwidth
    python rtl_scan_live.py 99.5e6 2.4e6 150 # 5 seconds at 30 updates/sec
"""

import sys
import time
import numpy as np
import shutil
from collections import deque
from rtlsdr import RtlSdr
from scipy.interpolate import interp1d

# Import demodulator's frequency-dependent parameter function
# This is the SINGLE SOURCE OF TRUTH for all frequency-dependent settings
try:
    # Try importing from the app structure
    from app.ui.widgets.demodulator import LcarsDemodulator
    _demod_instance = LcarsDemodulator()
    
    def get_optimal_sample_rate(center_freq_hz):
        """Get optimal sample rate from demodulator's configuration"""
        params = _demod_instance.get_demodulation_params(center_freq_hz)
        return params['sample_rate']
    
    print("Using demodulator's frequency configuration (single source of truth)")
    
except ImportError as e:
    print("Warning: Could not import demodulator - using built-in defaults")
    print("  Error: {}".format(e))
    
    def get_optimal_sample_rate(center_freq_hz):
        """Fallback function if demodulator is not available"""
        freq_mhz = center_freq_hz / 1e6
        if 156.0 <= freq_mhz <= 163.0:
            return 250000  # NOAA/Marine - narrow
        elif 118.0 <= freq_mhz <= 148.0:
            return 250000  # Aviation/2m Ham - narrow
        elif 88.0 <= freq_mhz <= 108.0:
            return 1200000  # FM Broadcast - wide
        elif 420.0 <= freq_mhz <= 467.0:
            return 250000  # UHF narrow-band
        else:
            return 2400000  # Default - wide

# Configuration
DEFAULT_SAMPLE_RATE = 2.4e6  # Default if demodulator lookup fails
DEFAULT_WATERFALL_LINES = 150
FFT_SIZE = 2048
UPDATE_INTERVAL = 0.0165
GAIN = 40
FREQ_CORRECTION = 60
NUM_AVERAGES = 4

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


def remove_dc_spike(psd, center_idx, window_size=50):
    """
    Remove DC spike using smooth polynomial fitting
    
    This creates a much smoother transition than linear interpolation
    by fitting a polynomial curve to the surrounding data and blending
    it into the spike region.
    
    Args:
        psd: Power spectral density array
        center_idx: Index of center frequency (DC spike location)
        window_size: Width of spike to remove (bins)
    
    Returns:
        psd_fixed: PSD with DC spike smoothly removed
    """
    # Find spike region
    start_idx = max(0, center_idx - window_size // 2)
    end_idx = min(len(psd), center_idx + window_size // 2)
    
    # Need points on both sides for fitting
    if start_idx < 10 or end_idx > len(psd) - 10:
        return psd
    
    # Use wider region for polynomial fit (smoother result)
    fit_margin = 40  # Use 40 bins on each side for fitting
    
    # Get points before and after spike for fitting
    before_start = max(0, start_idx - fit_margin)
    before_end = start_idx
    after_start = end_idx
    after_end = min(len(psd), end_idx + fit_margin)
    
    # Combine regions for fitting
    fit_x = np.concatenate([
        np.arange(before_start, before_end),
        np.arange(after_start, after_end)
    ])
    fit_y = psd[fit_x]
    
    if len(fit_x) < 10:
        return psd
    
    # Fit 3rd degree polynomial (smooth curve, not just linear)
    # This creates a natural-looking interpolation
    try:
        coeffs = np.polyfit(fit_x, fit_y, deg=3)
        poly_func = np.poly1d(coeffs)
        
        # Generate smooth interpolated values for spike region
        spike_indices = np.arange(start_idx, end_idx)
        interpolated_values = poly_func(spike_indices)
        
        # Apply gradual blending at edges for ultra-smooth transition
        blend_width = 10  # Blend over 10 bins at each edge
        
        psd_fixed = psd.copy()
        
        # Replace center with interpolated values
        psd_fixed[start_idx:end_idx] = interpolated_values
        
        # Blend at left edge
        if start_idx >= blend_width:
            for i in range(blend_width):
                blend_idx = start_idx - blend_width + i
                alpha = i / blend_width  # 0 to 1
                psd_fixed[blend_idx] = (1 - alpha) * psd[blend_idx] + alpha * poly_func(blend_idx)
        
        # Blend at right edge  
        if end_idx + blend_width <= len(psd):
            for i in range(blend_width):
                blend_idx = end_idx + i
                alpha = 1 - (i / blend_width)  # 1 to 0
                psd_fixed[blend_idx] = alpha * poly_func(blend_idx) + (1 - alpha) * psd[blend_idx]
        
        return psd_fixed
        
    except np.linalg.LinAlgError:
        # Fallback: if polynomial fit fails, use simple linear interpolation
        # (This shouldn't happen but good to be safe)
        before_idx = np.arange(max(0, start_idx - 20), start_idx)
        after_idx = np.arange(end_idx, min(len(psd), end_idx + 20))
        
        if len(before_idx) == 0 or len(after_idx) == 0:
            return psd
        
        interp_x = np.concatenate([before_idx, after_idx])
        interp_y = psd[interp_x]
        
        f = interp1d(interp_x, interp_y, kind='linear', fill_value='extrapolate')
        
        psd_fixed = psd.copy()
        spike_indices = np.arange(start_idx, end_idx)
        psd_fixed[spike_indices] = f(spike_indices)
        
        return psd_fixed


def parse_args():
    """Parse command line arguments"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    center_freq = float(sys.argv[1])
    
    # If sample rate not specified, use adaptive rate based on frequency
    if len(sys.argv) > 2:
        sample_rate = float(sys.argv[2])
        print("Using user-specified sample rate: {:.3f} MHz".format(sample_rate/1e6))
    else:
        sample_rate = get_optimal_sample_rate(center_freq)
        print("Using adaptive sample rate for {:.3f} MHz: {:.3f} MHz".format(
            center_freq/1e6, sample_rate/1e6))
    
    waterfall_lines = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_WATERFALL_LINES
    
    return center_freq, sample_rate, waterfall_lines


def setup_sdr(center_freq, sample_rate):
    """Initialize and configure the SDR"""
    print("Initializing SDR...")
    print("  Center frequency: {:.3f} MHz".format(center_freq/1e6))
    print("  Sample rate: {:.3f} MHz".format(sample_rate/1e6))
    print("  Bandwidth: {:.3f} MHz".format(sample_rate/1e6))
    
    # Validate frequency range
    if center_freq < 24e6 or center_freq > 1766e6:
        print("\n WARNING: Frequency {:.3f} MHz is outside typical RTL-SDR range (24-1766 MHz)".format(
            center_freq/1e6))
        print("  This may not work properly!")
    
    # Validate sample rate
    if sample_rate < 225001 or sample_rate > 3200000:
        print("\n WARNING: Sample rate {:.3f} MHz is outside recommended range (0.225-3.2 MHz)".format(
            sample_rate/1e6))
        print("  Adjusting to safe value...")
        sample_rate = max(225001, min(3200000, sample_rate))
        print("  New sample rate: {:.3f} MHz".format(sample_rate/1e6))
    
    try:
        sdr = RtlSdr()
        sdr.sample_rate = sample_rate
        sdr.center_freq = int(center_freq)
        sdr.freq_correction = FREQ_CORRECTION
        sdr.gain = GAIN
        
        # Verify settings were applied
        actual_freq = sdr.center_freq
        actual_rate = sdr.sample_rate
        
        print("  Actual center freq: {:.3f} MHz".format(actual_freq/1e6))
        print("  Actual sample rate: {:.3f} MHz".format(actual_rate/1e6))
        
        if abs(actual_freq - center_freq) > 1000:
            print("   Frequency mismatch detected!")
        
        if abs(actual_rate - sample_rate) > 1000:
            print("   Sample rate mismatch detected!")
        
        # Discard initial samples to let hardware settle
        print("  Settling hardware...")
        _ = sdr.read_samples(4096)  # Read more samples for better settling
        
        print("  Gain: {} dB (FIXED - was 4 dB)".format(sdr.gain))
        print("SDR initialized successfully!")
        
        return sdr
        
    except Exception as e:
        print("\n ERROR: Failed to initialize SDR!")
        print("  Error: {}".format(str(e)))
        print("\nTroubleshooting:")
        print("  1. Check RTL-SDR is connected")
        print("  2. Try different sample rate (250 kHz - 2.4 MHz)")
        print("  3. Check frequency is in valid range (24-1766 MHz)")
        print("  4. Kill any other processes using RTL-SDR:")
        print("     killall rtl_fm rtl_sdr rtl_test")
        raise


def compute_psd_averaged(sdr, fft_size, num_averages):
    """
    Compute averaged Power Spectral Density from multiple FFTs
    
    Args:
        sdr: RTL-SDR object
        fft_size: FFT size
        num_averages: Number of FFTs to average
    
    Returns:
        psd: Averaged power spectral density in dB
    """
    psd_accumulator = np.zeros(fft_size)
    
    for _ in range(num_averages):
        # Read samples
        samples = sdr.read_samples(fft_size)
        
        # Apply window to reduce spectral leakage
        window = np.hanning(len(samples))
        samples_windowed = samples * window
        
        # Compute FFT
        fft_result = np.fft.fft(samples_windowed)
        fft_shifted = np.fft.fftshift(fft_result)
        
        # Compute power (linear scale for averaging)
        power = np.abs(fft_shifted)**2
        psd_accumulator += power
    
    # Average and convert to dB
    psd_avg = psd_accumulator / num_averages
    psd_db = 10 * np.log10(psd_avg + 1e-10)
    
    return psd_db


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
    
    # Calculate center index for DC spike removal
    center_idx = FFT_SIZE // 2
    
    # Save frequency axis
    save_data_atomic(frequencies, FREQUENCIES_FILE_TEMP, FREQUENCIES_FILE)
    
    # Save metadata
    metadata = np.array([center_freq, sample_rate, FFT_SIZE, waterfall_lines, UPDATE_INTERVAL])
    save_data_atomic(metadata, METADATA_FILE_TEMP, METADATA_FILE)
    
    # Initialize waterfall buffer (FIFO queue)
    waterfall_buffer = deque(maxlen=waterfall_lines)
    
    print("\nStarting live scan...")
    print("  FFT size: {} (INCREASED for better resolution)".format(FFT_SIZE))
    print("  Averaging: {} FFTs per update (NEW - smoother display)".format(NUM_AVERAGES))
    print("  Update rate: ~{:.1f} Hz".format(1/UPDATE_INTERVAL))
    print("  Waterfall history: {} lines (~{:.1f} seconds)".format(
        waterfall_lines, waterfall_lines*UPDATE_INTERVAL))
    print("  DC spike removal: SMOOTH POLYNOMIAL (eliminates discontinuities)")
    print("\nWriting data to:")
    print("  PSD: {}".format(PSD_FILE))
    print("  Waterfall: {}".format(WATERFALL_FILE))
    print("  Frequencies: {}".format(FREQUENCIES_FILE))
    print("\nPress Ctrl+C to stop\n")
    
    frame_count = 0
    start_time = time.time()
    last_update = time.time()
    
    # Statistics for monitoring
    psd_min = float('inf')
    psd_max = float('-inf')
    
    try:
        while True:
            # Compute averaged PSD
            psd = compute_psd_averaged(sdr, FFT_SIZE, NUM_AVERAGES)
            
            # Remove DC spike
            psd = remove_dc_spike(psd, center_idx)
            
            # Add to waterfall buffer
            waterfall_buffer.append(psd)
            
            # Track statistics
            psd_min = min(psd_min, np.min(psd))
            psd_max = max(psd_max, np.max(psd))
            
            # Check if it's time to update files
            current_time = time.time()
            if current_time - last_update >= UPDATE_INTERVAL:
                # Save current PSD
                save_data_atomic(psd, PSD_FILE_TEMP, PSD_FILE)
                
                # Save waterfall as 2D array
                waterfall_array = np.array(waterfall_buffer)
                waterfall_flipped = np.flipud(waterfall_array)
                save_data_atomic(waterfall_flipped, WATERFALL_FILE_TEMP, WATERFALL_FILE)
                
                last_update = current_time
                frame_count += 1
                
                # Print status every 30 frames (~0.5 seconds)
                if frame_count % 30 == 0:
                    elapsed = current_time - start_time
                    actual_fps = frame_count / elapsed
                    dynamic_range = psd_max - psd_min
                    print("Frame {:6d} | {:6.1f}s | {:5.1f} Hz | Waterfall: {}/{} | DR: {:.1f} dB | Range: {:.1f} to {:.1f} dB".format(
                        frame_count, elapsed, actual_fps, len(waterfall_buffer), 
                        waterfall_lines, dynamic_range, psd_min, psd_max))
    
    except KeyboardInterrupt:
        print("\n\nStopping live scan...")
        elapsed = time.time() - start_time
        print("Total frames: {}".format(frame_count))
        print("Total time: {:.1f}s".format(elapsed))
        print("Average rate: {:.1f} Hz".format(frame_count/elapsed))
        print("Dynamic range: {:.1f} dB".format(psd_max - psd_min))
    
    finally:
        sdr.close()
        print("SDR closed. Goodbye!")


if __name__ == "__main__":
    main()
