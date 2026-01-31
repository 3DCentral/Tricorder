#!/usr/bin/env python3
"""
rtl_scan_2.py - ADAPTIVE RESOLUTION VERSION

Improvements over previous version:
1. Adaptive resolution based on number of sweeps (faster wide scans)
2. Y-axis dB scale for signal strength reference
3. Better DC spike removal using interpolation
4. Proper overlap handling to avoid stitching artifacts
5. Diagnostic output
"""

from rtlsdr import RtlSdr
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
from scipy import signal
from scipy.interpolate import interp1d

def remove_dc_spike(frequencies, psd, center_freq, window_hz=50000):
    """
    Remove DC spike using interpolation (better than averaging)
    
    Args:
        frequencies: Frequency array in Hz
        psd: Power spectral density array
        center_freq: Center frequency where DC spike occurs
        window_hz: Width of spike to remove (Hz)
    """
    # Find indices within window of center frequency
    spike_mask = np.abs(frequencies - center_freq) < window_hz
    
    if not np.any(spike_mask):
        return psd
    
    # Find edges of spike region
    spike_indices = np.where(spike_mask)[0]
    if len(spike_indices) == 0:
        return psd
    
    start_idx = spike_indices[0]
    end_idx = spike_indices[-1]
    
    # Need points on both sides for interpolation
    if start_idx < 5 or end_idx > len(psd) - 5:
        return psd
    
    # Get points before and after spike
    before_idx = np.arange(max(0, start_idx - 20), start_idx)
    after_idx = np.arange(end_idx + 1, min(len(psd), end_idx + 21))
    
    if len(before_idx) == 0 or len(after_idx) == 0:
        return psd
    
    # Interpolate across spike
    interp_x = np.concatenate([before_idx, after_idx])
    interp_y = psd[interp_x]
    
    # Create interpolation function
    f = interp1d(interp_x, interp_y, kind='linear', fill_value='extrapolate')
    
    # Fill in spike region with interpolated values
    psd_fixed = psd.copy()
    psd_fixed[spike_indices] = f(spike_indices)
    
    return psd_fixed


def merge_overlapping_data(frequencies, psd_data, bin_width_hz=1000):
    """
    Merge overlapping frequency data by binning and averaging
    
    When scanning with overlap, the same frequency appears multiple times.
    This function bins the data and averages overlapping measurements.
    
    Args:
        frequencies: Array of frequency values (may have duplicates)
        psd_data: Array of PSD values (linear scale, not dB)
        bin_width_hz: Width of frequency bins for averaging (Hz)
    
    Returns:
        merged_freq: Unique frequency array (sorted)
        merged_psd: Averaged PSD values for each frequency bin
    """
    # Find frequency range
    freq_min = np.min(frequencies)
    freq_max = np.max(frequencies)
    
    # Create frequency bins
    num_bins = int(np.ceil((freq_max - freq_min) / bin_width_hz))
    bins = np.linspace(freq_min, freq_max, num_bins + 1)
    
    # Digitize frequencies into bins
    bin_indices = np.digitize(frequencies, bins)
    
    # Average PSD values within each bin
    merged_freq = []
    merged_psd = []
    
    for bin_idx in range(1, len(bins)):
        # Find all data points in this bin
        in_bin = bin_indices == bin_idx
        
        if np.any(in_bin):
            # Average frequency and PSD for this bin
            avg_freq = np.mean(frequencies[in_bin])
            avg_psd = np.mean(psd_data[in_bin])  # Average in linear scale
            
            merged_freq.append(avg_freq)
            merged_psd.append(avg_psd)
    
    return np.array(merged_freq), np.array(merged_psd)


def get_adaptive_parameters(num_sweeps):
    """
    Get adaptive scan parameters based on number of sweeps
    
    For wide scans (many sweeps), use lower resolution for speed.
    For narrow scans (few sweeps), use higher resolution for detail.
    
    Args:
        num_sweeps: Number of sweeps to perform
        
    Returns:
        (fft_size, num_rows) tuple
    """
    if num_sweeps <= 2:
        # Very narrow scan: High detail (reduced from 2048/1000)
        return (1024, 600)
    elif num_sweeps <= 4:
        # Narrow scan: Medium detail (reduced from 1024/800)
        return (1024, 400)
    elif num_sweeps <= 7:
        # Medium scan: Balanced (reduced from 1024/500)
        return (512, 400)
    else:
        # Wide scan: Fast (reduced from 512/300)
        return (512, 250)


def plot_progress(frequencies, psd_db, start_freq, end_freq, step_num, total_steps):
    """Create progress spectrum plot during scanning with minimalist dB scale"""
    fig = plt.figure(figsize=(6.4, 3.36), dpi=100)
    # Full width for data, no left margin needed
    ax = plt.axes([0, 0.08, 1, 0.92])
    
    # Styling
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    
    # Plot spectrum so far
    ax.plot(frequencies, psd_db, color="yellow", linewidth=2)
    
    # Set limits to full range
    ax.set_xlim(start_freq, end_freq)
    
    # Y-axis: minimalist dB scale with tick marks only
    if len(psd_db) > 0:
        psd_min = np.min(psd_db)
        psd_max = np.max(psd_db)
        
        # Round to nice values
        y_min = np.floor(psd_min / 10) * 10
        y_max = np.ceil(psd_max / 10) * 10
        
        ax.set_ylim(y_min, y_max)
        
        # Draw minimalist tick marks on left edge (moved right to avoid cropping)
        ax.tick_params(axis='y', which='both', left=False, right=False, 
                      labelleft=False, labelright=False)
        
        # Manually draw tick marks at left edge, slightly offset to avoid cropping
        freq_range = end_freq - start_freq
        tick_start = start_freq + freq_range * 0.015  # Start 1.5% from left edge
        tick_length = freq_range * 0.012  # Tick mark length
        
        for y_val in [y_min, y_max]:
            ax.plot([tick_start, tick_start + tick_length], [y_val, y_val], 
                   color='yellow', linewidth=1.5)
        
        # Add top and bottom dB labels, positioned after tick marks
        label_x = tick_start + tick_length * 1.5
        ax.text(label_x, y_max, '{:.0f}dB'.format(y_max),
               color='yellow', fontsize=8, verticalalignment='center')
        ax.text(label_x, y_min, '{:.0f}dB'.format(y_min),
               color='yellow', fontsize=8, verticalalignment='center')
    
    # X-axis labels
    ax.tick_params(axis='x', colors='yellow', labelsize=9)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: '{:.1f}'.format(x/1e6)))
    
    for label in ax.get_xticklabels():
        label.set_color('yellow')
    
    # Add progress indicator
    progress_pct = int(100 * step_num / total_steps)
    ax.text(0.02, 0.95, 'Scanning... {}%'.format(progress_pct), 
            transform=ax.transAxes, color='yellow', fontsize=10,
            verticalalignment='top')
    
    # Save with numbered filename
    output_file = '/tmp/spectrum_progress_{:04d}.png'.format(step_num)
    plt.savefig(output_file, dpi=100, facecolor="black", bbox_inches='tight', pad_inches=0)
    plt.close()


def scan_frequency_range(start_freq, end_freq, sample_rate=2.4e6, gain=40, show_progress=True):
    """
    Scan a frequency range and return stitched spectrum
    Uses adaptive resolution based on scan width.
    
    Args:
        start_freq: Start frequency (Hz)
        end_freq: End frequency (Hz)
        sample_rate: SDR sample rate (Hz)
        gain: RF gain (dB) - higher = more sensitive
        show_progress: If True, generate progress images during scan
    """
    # Clean up old progress files
    if show_progress:
        import glob
        import os
        old_files = glob.glob('/tmp/spectrum_progress_*.png')
        for f in old_files:
            try:
                os.remove(f)
            except:
                pass
    
    print("="*60)
    print("RTL-SDR Frequency Scanner - ADAPTIVE RESOLUTION VERSION")
    print("="*60)
    print("Frequency range: {:.1f} - {:.1f} MHz".format(start_freq/1e6, end_freq/1e6))
    print("Sample rate: {:.1f} MHz".format(sample_rate/1e6))
    print("Gain: {} dB".format(gain))
    
    sdr = RtlSdr()
    sdr.sample_rate = sample_rate
    sdr.freq_correction = 60  # PPM
    sdr.gain = gain
    
    print("Actual gain set: {} dB".format(sdr.gain))
    
    # Discard initial samples
    _ = sdr.read_samples(2048)
    
    # Calculate sweep parameters with 10% overlap to reduce stitching artifacts
    overlap = 0.1
    step_size = int(sample_rate * (1 - overlap))
    num_steps = int(np.ceil((end_freq - start_freq) / step_size))
    
    # Get adaptive parameters based on number of sweeps
    fft_size, num_rows = get_adaptive_parameters(num_steps)
    
    print("Sweep steps: {}".format(num_steps))
    print("Overlap: {}%".format(overlap*100))
    print("Resolution mode: FFT={}, Rows={}".format(fft_size, num_rows))
    if num_steps > 7:
        print("  (Using lower resolution for faster wide scan)")
    elif num_steps <= 2:
        print("  (Using maximum resolution for detailed narrow scan)")
    print()
    
    all_frequencies = []
    all_psd_data = []
    
    for step_num in range(num_steps):
        # Calculate center frequency for this step
        center_freq = start_freq + step_size * step_num + sample_rate / 2
        
        # Don't go past end frequency
        if center_freq - sample_rate/2 > end_freq:
            break
        
        scan_start = center_freq - sample_rate/2
        scan_end = center_freq + sample_rate/2
        
        print("Step {}/{}: {:.3f} - {:.3f} MHz".format(
            step_num+1, num_steps, scan_start/1e6, scan_end/1e6), end='')
        
        sdr.center_freq = int(center_freq)
        
        # Read samples
        samples = sdr.read_samples(fft_size * num_rows)
        
        # Compute PSD using Welch's method
        frequencies, psd = signal.welch(samples, fs=sample_rate, 
                                       nperseg=fft_size,
                                       window='hanning',
                                       noverlap=fft_size//2)
        
        # Shift to center
        frequencies = np.fft.fftshift(frequencies)
        psd = np.fft.fftshift(psd)
        
        # Adjust frequencies to absolute
        frequencies = frequencies + center_freq
        
        # Remove DC spike using interpolation
        psd = remove_dc_spike(frequencies, psd, center_freq)
        
        # Check signal quality
        psd_db = 10 * np.log10(psd + 1e-10)
        dynamic_range = np.max(psd_db) - np.min(psd_db)
        print(" | DR: {:.1f} dB".format(dynamic_range), end='')
        
        # Warn if no signals detected
        if dynamic_range < 10:
            print(" ⚠ LOW SIGNAL", end='')
        
        print()
        
        # Add to collection (raw data for now, we'll merge overlaps later)
        all_frequencies.extend(frequencies.tolist())
        all_psd_data.extend(psd.tolist())
        
        # Generate progress image if requested
        if show_progress and len(all_frequencies) > 0:
            # For progress view, use merged data
            merged_freq, merged_psd = merge_overlapping_data(
                np.array(all_frequencies), 
                np.array(all_psd_data)
            )
            temp_psd_db = 10 * np.log10(merged_psd + 1e-10)
            
            # Plot progress
            plot_progress(merged_freq, temp_psd_db, start_freq, end_freq, step_num+1, num_steps)
    
    sdr.close()
    
    # Merge overlapping data points by averaging
    print("\nMerging overlapping frequency data...")
    all_frequencies = np.array(all_frequencies)
    all_psd_data = np.array(all_psd_data)
    
    # Call the merge function
    all_frequencies, all_psd_data = merge_overlapping_data(all_frequencies, all_psd_data)
    
    print()
    print("="*60)
    print("Scan complete!")
    print("Total data points: {}".format(len(all_frequencies)))
    
    # Convert to dB
    psd_db = 10 * np.log10(all_psd_data + 1e-10)
    
    # Remove outliers (spurious signals)
    outlier_threshold_db = -200
    valid_mask = psd_db > outlier_threshold_db
    
    if np.sum(valid_mask) > 0:
        filtered_frequencies = all_frequencies[valid_mask]
        filtered_psd_db = psd_db[valid_mask]
        
        print("Valid data points: {}".format(len(filtered_frequencies)))
        print("PSD range: {:.1f} to {:.1f} dB".format(
            np.min(filtered_psd_db), np.max(filtered_psd_db)))
        print("Dynamic range: {:.1f} dB".format(
            np.max(filtered_psd_db) - np.min(filtered_psd_db)))
        
        # Detect peaks (potential signals)
        noise_floor = np.median(filtered_psd_db)
        threshold = noise_floor + 10
        peaks = np.where(filtered_psd_db > threshold)[0]
        print("Noise floor: {:.1f} dB".format(noise_floor))
        print("Detected peaks: {}".format(len(peaks)))
        
        if len(peaks) == 0:
            print("\n⚠ WARNING: No signals detected above noise floor!")
            print("  Check:")
            print("  - Antenna connected?")
            print("  - Gain setting ({} dB)?".format(gain))
            print("  - Frequency range has active transmitters?")
    else:
        filtered_frequencies = all_frequencies
        filtered_psd_db = psd_db
        print("⚠ No valid data after filtering!")
    
    return filtered_frequencies, filtered_psd_db


def plot_spectrum(frequencies, psd_db, start_freq, end_freq, output_file='/tmp/spectrum.png'):
    """Create spectrum plot with minimalist dB scale"""
    # Create figure
    fig = plt.figure(figsize=(6.4, 3.36), dpi=100)
    # Full width for data, no left margin needed
    ax = plt.axes([0, 0.08, 1, 0.92])
    
    # Styling
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    
    # Plot spectrum
    ax.plot(frequencies, psd_db, color="yellow", linewidth=2)
    
    # Set X limits
    ax.set_xlim(start_freq, end_freq)
    
    # Y-axis: minimalist dB scale with tick marks only
    if len(psd_db) > 0:
        psd_min = np.min(psd_db)
        psd_max = np.max(psd_db)
        
        # Round to nice values
        y_min = np.floor(psd_min / 10) * 10
        y_max = np.ceil(psd_max / 10) * 10
        
        ax.set_ylim(y_min, y_max)
        
        # Draw minimalist tick marks on left edge (moved right to avoid cropping)
        ax.tick_params(axis='y', which='both', left=False, right=False, 
                      labelleft=False, labelright=False)
        
        # Manually draw tick marks at left edge, slightly offset to avoid cropping
        freq_range = end_freq - start_freq
        tick_start = start_freq + freq_range * 0.015  # Start 1.5% from left edge
        tick_length = freq_range * 0.012  # Tick mark length
        
        for y_val in [y_min, y_max]:
            ax.plot([tick_start, tick_start + tick_length], [y_val, y_val], 
                   color='yellow', linewidth=1.5)
        
        # Add top and bottom dB labels, positioned after tick marks
        label_x = tick_start + tick_length * 1.5
        ax.text(label_x, y_max, '{:.0f}dB'.format(y_max),
               color='yellow', fontsize=8, verticalalignment='center')
        ax.text(label_x, y_min, '{:.0f}dB'.format(y_min),
               color='yellow', fontsize=8, verticalalignment='center')
    
    # X-axis labels
    ax.tick_params(axis='x', colors='yellow', labelsize=9)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: '{:.1f}'.format(x/1e6)))
    
    for label in ax.get_xticklabels():
        label.set_color('yellow')
    
    # Save
    plt.savefig(output_file, dpi=100, facecolor="black", bbox_inches='tight', pad_inches=0)
    plt.close()
    
    print("\n✓ Spectrum saved to {}".format(output_file))


def main():
    if len(sys.argv) < 3:
        print("Usage: python rtl_scan_2.py <start_freq> <end_freq> [gain] [show_progress]")
        print("Example: python rtl_scan_2.py 88e6 108e6 40 1")
        print("  show_progress: 1=show progress images (default), 0=final only")
        print("\nAdaptive Resolution:")
        print("  1-2 sweeps: High detail (1024 FFT, 600 rows)")
        print("  3-4 sweeps: Medium (1024 FFT, 400 rows)")
        print("  5-7 sweeps: Balanced (512 FFT, 400 rows)")
        print("  8+ sweeps:  Fast (512 FFT, 250 rows)")
        sys.exit(1)
    
    start_freq = int(float(sys.argv[1]))
    end_freq = int(float(sys.argv[2]))
    gain = int(sys.argv[3]) if len(sys.argv) > 3 else 40  # Default 40 dB
    show_progress = bool(int(sys.argv[4])) if len(sys.argv) > 4 else True  # Default True
    
    # Scan
    frequencies, psd_db = scan_frequency_range(start_freq, end_freq, gain=gain, show_progress=show_progress)
    
    # Plot final
    plot_spectrum(frequencies, psd_db, start_freq, end_freq)


if __name__ == '__main__':
    main()
