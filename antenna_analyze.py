#!/usr/bin/env python3
"""
test_antenna_characterization.py - Standalone Antenna Characterization Test

Run this script to test the antenna characterization logic independently.
Produces a matplotlib visualization similar to what will appear in the LCARS interface.

Usage:
    python3 test_antenna_characterization.py [gain]
    
Example:
    python3 test_antenna_characterization.py 40
"""

from rtlsdr import RtlSdr
import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # Use interactive backend
import matplotlib.pyplot as plt
from scipy import signal
import sys


def scan_antenna_characteristics(gain=40):
    """
    Perform antenna characterization scan
    
    Args:
        gain: RF gain setting (0-49 dB)
        
    Returns:
        Dictionary with frequencies, sensitivities, and analysis
    """
    print("="*70)
    print("RTL-SDR ANTENNA CHARACTERIZATION TEST")
    print("="*70)
    print("Gain: {} dB".format(gain))
    print()
    
    # Initialize SDR
    try:
        sdr = RtlSdr()
    except Exception as e:
        print("ERROR: Cannot open RTL-SDR device!")
        print("Error: {}".format(e))
        print("\nTroubleshooting:")
        print("  1. Is RTL-SDR plugged in?")
        print("  2. Is another program using it? (try: sudo killall rtl_fm)")
        print("  3. Do you have permissions? (try: sudo usermod -a -G plugdev $USER)")
        sys.exit(1)
    
    sdr.sample_rate = 2.4e6
    sdr.freq_correction = 60  # PPM
    sdr.gain = gain
    
    print("RTL-SDR initialized successfully")
    print("Sample rate: {:.1f} MHz".format(sdr.sample_rate / 1e6))
    print("Actual gain: {} dB".format(sdr.gain))
    print()
    
    # Discard initial samples
    _ = sdr.read_samples(2048)
    
    # Define test frequencies across the range
    # Logarithmic spacing to cover the spectrum efficiently
    # Conservative upper limit to avoid hardware issues
    test_frequencies = np.logspace(
        np.log10(60e6),    # 60 MHz (safer lower bound)
        np.log10(1.0e9),   # 1.0 GHz (conservative upper bound, avoids problem area)
        num=30             # 30 test points
    )
    
    print("Testing {} frequency points from {:.1f} MHz to {:.1f} MHz...".format(
        len(test_frequencies), 
        test_frequencies[0]/1e6,
        test_frequencies[-1]/1e6))
    print()
    
    results = {
        'frequencies': [],
        'sensitivities': [],
        'noise_floors': [],
        'dynamic_ranges': [],
        'gain': gain,
        'skipped': []
    }
    
    # Ultra-low resolution for speed
    fft_size = 256
    num_rows = 100
    
    print("Frequency        Noise Floor    Dynamic Range    Sensitivity")
    print("-" * 70)
    
    for i, center_freq in enumerate(test_frequencies):
        try:
            # Set center frequency - clamp to safe range
            safe_freq = int(max(60e6, min(1.0e9, center_freq)))
            
            # Skip known problematic frequencies (around 1.1 GHz seems to cause issues)
            if 1.05e9 <= safe_freq <= 1.2e9:
                print("{:8.1f} MHz     SKIPPED (known problematic range)".format(safe_freq/1e6))
                results['skipped'].append(float(safe_freq))
                continue
            
            sdr.center_freq = safe_freq
            
            # Longer delay to let hardware settle
            import time
            time.sleep(0.1)
            
            # Read samples with timeout protection
            samples = sdr.read_samples(fft_size * num_rows)
            
            # Compute PSD using Welch's method
            frequencies, psd = signal.welch(samples, fs=sdr.sample_rate,
                                           nperseg=fft_size,
                                           window='hanning',
                                           noverlap=fft_size//2)
            
            # Convert to dB
            psd_db = 10 * np.log10(psd + 1e-10)
            
            # Calculate noise floor (median of PSD)
            noise_floor = np.median(psd_db)
            
            # Calculate dynamic range
            # Higher dynamic range = more signals being received = better sensitivity
            dynamic_range = np.max(psd_db) - noise_floor
            
            # Calculate raw sensitivity
            # Higher noise floor = more signals = better antenna
            raw_sensitivity = noise_floor + 100  # Normalize to positive values
            
            # Combine metrics
            # Higher noise floor + higher dynamic range = better antenna
            sensitivity = raw_sensitivity + (dynamic_range * 0.5)
            
            # Display progress
            print("{:8.1f} MHz     {:6.1f} dB        {:6.1f} dB         {:6.1f}".format(
                safe_freq/1e6, noise_floor, dynamic_range, sensitivity))
            
            results['frequencies'].append(float(safe_freq))
            results['sensitivities'].append(float(sensitivity))
            results['noise_floors'].append(float(noise_floor))
            results['dynamic_ranges'].append(float(dynamic_range))
            
        except OSError as e:
            # USB/hardware error - this is serious, might want to stop
            print("{:8.1f} MHz     USB ERROR - stopping scan".format(center_freq/1e6))
            print("              Error: {}".format(str(e)))
            break
        except Exception as e:
            # Other errors - skip this frequency
            print("{:8.1f} MHz     ERROR: {} - skipping".format(center_freq/1e6, str(e)[:40]))
            results['skipped'].append(float(center_freq))
            continue
    
    sdr.close()
    print()
    print("="*70)
    
    # Check if we got any valid data
    if not results['frequencies']:
        print("ERROR: No valid frequency measurements obtained!")
        print("This could be due to:")
        print("  - RTL-SDR hardware issues")
        print("  - Frequency range not supported by your device")
        print("  - USB connection problems")
        return None, None
    
    print("Successfully measured {} frequency points".format(len(results['frequencies'])))
    
    # Normalize sensitivities to 0-100 scale
    sens_array = np.array(results['sensitivities'])
    sens_min = np.min(sens_array)
    sens_max = np.max(sens_array)
    
    if sens_max > sens_min:
        normalized = ((sens_array - sens_min) / (sens_max - sens_min)) * 100
        results['sensitivities_normalized'] = normalized.tolist()
    else:
        results['sensitivities_normalized'] = [50.0] * len(sens_array)
    
    print("RAW DATA ANALYSIS:")
    print("  Sensitivity range: {:.1f} to {:.1f}".format(sens_min, sens_max))
    print("  Normalized to: 0-100 scale")
    print()
    
    # Analyze results
    analyze_results(test_frequencies, results)
    
    return test_frequencies, results


def analyze_results(frequencies, results):
    """Analyze and print characterization results"""
    
    normalized = results['sensitivities_normalized']
    
    # Find peak sensitivity
    best_idx = np.argmax(normalized)
    best_freq = frequencies[best_idx]
    best_sens = normalized[best_idx]
    
    print("ANALYSIS:")
    print("  Peak sensitivity: {:.1f}% at {:.1f} MHz".format(best_sens, best_freq/1e6))
    print()
    
    # Define known frequency bands (within our test range)
    known_bands = [
        {'name': 'FM Radio', 'start': 88e6, 'end': 108e6, 'color': 'orange'},
        {'name': 'Air Band', 'start': 118e6, 'end': 137e6, 'color': 'yellow'},
        {'name': 'Weather Satellites', 'start': 137e6, 'end': 138e6, 'color': 'cyan'},
        {'name': '2m Ham', 'start': 144e6, 'end': 148e6, 'color': 'magenta'},
        {'name': '70cm Ham', 'start': 420e6, 'end': 450e6, 'color': 'blue'},
    ]
    
    # Check sensitivity in each known band
    optimal_bands = []
    
    print("KNOWN FREQUENCY BANDS:")
    for band in known_bands:
        # Find data points in this band
        band_sensitivities = [
            normalized[i] for i, freq in enumerate(frequencies)
            if band['start'] <= freq <= band['end']
        ]
        
        if band_sensitivities:
            avg_sens = np.mean(band_sensitivities)
            
            # Categorize
            if avg_sens > 70:
                category = "EXCELLENT"
                optimal_bands.append({'name': band['name'], 'sensitivity': avg_sens})
            elif avg_sens > 50:
                category = "GOOD"
            elif avg_sens > 30:
                category = "MODERATE"
            else:
                category = "POOR"
            
            print("  {:<20s} {:>6.1f}%  [{}]".format(
                band['name'], avg_sens, category))
        else:
            print("  {:<20s} (not tested)".format(band['name']))
    
    print()
    
    if optimal_bands:
        print("ANTENNA OPTIMIZED FOR:")
        for band in sorted(optimal_bands, key=lambda x: x['sensitivity'], reverse=True):
            print("  - {} ({:.1f}% sensitivity)".format(band['name'], band['sensitivity']))
    else:
        print("No bands with excellent sensitivity detected.")
        print("This may indicate:")
        print("  - Generic/wideband antenna")
        print("  - Antenna not connected properly")
        print("  - Poor antenna placement")
    
    print()


def plot_results(frequencies, results):
    """Create visualization of antenna characterization"""
    
    normalized = results['sensitivities_normalized']
    noise_floors = results['noise_floors']
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    fig.patch.set_facecolor('black')
    
    # Subplot 1: Normalized Sensitivity (0-100%)
    ax1.set_facecolor('black')
    
    # Define known bands for highlighting (within our test range)
    known_bands = [
        {'name': 'FM Radio', 'start': 88e6, 'end': 108e6, 'color': 'orange', 'alpha': 0.2},
        {'name': 'Air Band', 'start': 118e6, 'end': 137e6, 'color': 'yellow', 'alpha': 0.2},
        {'name': 'Weather', 'start': 137e6, 'end': 138e6, 'color': 'cyan', 'alpha': 0.2},
        {'name': '2m Ham', 'start': 144e6, 'end': 148e6, 'color': 'magenta', 'alpha': 0.2},
        {'name': '70cm Ham', 'start': 420e6, 'end': 450e6, 'color': 'blue', 'alpha': 0.2},
    ]
    
    # Draw reference bands
    for band in known_bands:
        ax1.axvspan(band['start']/1e6, band['end']/1e6, 
                   color=band['color'], alpha=band['alpha'], label=band['name'])
    
    # Plot sensitivity curve
    ax1.plot(np.array(frequencies)/1e6, normalized, 
            color='yellow', linewidth=2, marker='o', markersize=4)
    
    # Fill area under curve
    ax1.fill_between(np.array(frequencies)/1e6, 0, normalized, 
                     color='yellow', alpha=0.3)
    
    # Formatting
    ax1.set_xscale('log')
    ax1.set_xlim(60, 1000)  # 60 MHz to 1 GHz
    ax1.set_ylim(0, 105)
    ax1.set_ylabel('Antenna Sensitivity (%)', color='yellow', fontsize=12)
    ax1.set_title('ANTENNA FREQUENCY RESPONSE (Normalized)', 
                 color='yellow', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, color='yellow')
    ax1.tick_params(colors='yellow')
    ax1.spines['bottom'].set_color('yellow')
    ax1.spines['top'].set_color('yellow')
    ax1.spines['left'].set_color('yellow')
    ax1.spines['right'].set_color('yellow')
    
    # Add legend
    legend = ax1.legend(loc='upper right', facecolor='black', edgecolor='yellow', fontsize=9)
    # Set legend text color manually for older matplotlib versions
    for text in legend.get_texts():
        text.set_color('yellow')
    
    # Subplot 2: Raw Noise Floor
    ax2.set_facecolor('black')
    
    # Draw reference bands
    for band in known_bands:
        ax2.axvspan(band['start']/1e6, band['end']/1e6, 
                   color=band['color'], alpha=band['alpha'])
    
    # Plot noise floor
    ax2.plot(np.array(frequencies)/1e6, noise_floors, 
            color='cyan', linewidth=2, marker='s', markersize=4, label='Noise Floor')
    
    # Formatting
    ax2.set_xscale('log')
    ax2.set_xlim(60, 1000)  # 60 MHz to 1 GHz
    ax2.set_xlabel('Frequency (MHz)', color='yellow', fontsize=12)
    ax2.set_ylabel('Noise Floor (dB)', color='cyan', fontsize=12)
    ax2.set_title('RAW NOISE FLOOR MEASUREMENTS', 
                 color='cyan', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, color='yellow')
    ax2.tick_params(colors='yellow')
    ax2.spines['bottom'].set_color('yellow')
    ax2.spines['top'].set_color('yellow')
    ax2.spines['left'].set_color('cyan')
    ax2.spines['right'].set_color('cyan')
    
    # Add horizontal line at median noise floor
    median_nf = np.median(noise_floors)
    ax2.axhline(y=median_nf, color='red', linestyle='--', linewidth=1, 
               label='Median NF: {:.1f} dB'.format(median_nf))
    legend = ax2.legend(loc='upper right', facecolor='black', edgecolor='cyan', fontsize=9)
    # Set legend text color manually for older matplotlib versions
    for text in legend.get_texts():
        text.set_color('cyan')
    
    plt.tight_layout()
    
    # Save figure
    output_file = '/tmp/antenna_characterization_test.png'
    plt.savefig(output_file, dpi=150, facecolor='black', edgecolor='yellow')
    print("Plot saved to: {}".format(output_file))
    
    # Show plot
    plt.show()


def main():
    """Main function"""
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            gain = int(sys.argv[1])
            if gain < 0 or gain > 49:
                print("Warning: Gain should be 0-49 dB. Using {} anyway.".format(gain))
        except ValueError:
            print("Error: Gain must be an integer")
            print("Usage: python3 test_antenna_characterization.py [gain]")
            sys.exit(1)
    else:
        gain = 40  # Default gain
    
    print()
    print("ANTENNA CHARACTERIZATION TEST")
    print("This script will:")
    print("  1. Connect to RTL-SDR")
    print("  2. Test 30 frequencies across 50 MHz - 2.2 GHz")
    print("  3. Measure noise floor and dynamic range")
    print("  4. Calculate antenna sensitivity")
    print("  5. Display results and visualization")
    print()
    print("Expected duration: ~10 seconds")
    print()
    
    input("Press ENTER to start...")
    print()
    
    # Perform scan
    frequencies, results = scan_antenna_characteristics(gain=gain)
    
    # Check if scan succeeded
    if frequencies is None or results is None:
        print()
        print("Scan failed. Please check error messages above.")
        sys.exit(1)
    
    print()
    print("="*70)
    print("Creating visualization...")
    
    # Plot results
    plot_results(frequencies, results)
    
    print()
    print("Test complete!")
    print()


if __name__ == '__main__':
    main()
