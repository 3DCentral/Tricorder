#!/usr/bin/env python3
"""
rtl_antenna_scan.py - Background Antenna Characterization Scanner

Performs antenna characterization and outputs progress data for GUI consumption.
Saves intermediate results to /tmp/antenna_scan_*.npy files.
"""

from rtlsdr import RtlSdr
import numpy as np
from scipy import signal
import sys
import json
import time


def scan_antenna_characteristics(gain=40, output_prefix="/tmp/antenna_scan"):
    """
    Perform antenna characterization scan with real-time progress output
    
    Args:
        gain: RF gain setting (0-49 dB)
        output_prefix: File prefix for output files
    """
    print("RTL-SDR ANTENNA CHARACTERIZATION")
    print("Gain: {} dB".format(gain))
    
    # Initialize SDR
    try:
        sdr = RtlSdr()
    except Exception as e:
        print("ERROR: Cannot open RTL-SDR device!")
        print("Error: {}".format(e))
        sys.exit(1)
    
    sdr.sample_rate = 2.4e6
    sdr.freq_correction = 60  # PPM
    sdr.gain = gain
    
    print("RTL-SDR initialized")
    print("Sample rate: {:.1f} MHz".format(sdr.sample_rate / 1e6))
    print("Actual gain: {} dB".format(sdr.gain))
    
    # Discard initial samples
    _ = sdr.read_samples(2048)
    
    # Define test frequencies
    # Scan from 60 MHz to 1.76 GHz (R820T2 tuner safe maximum)
    # Avoiding the problematic 1.05-1.2 GHz range
    test_frequencies = np.logspace(
        np.log10(60e6),     # 60 MHz (safe lower limit)
        np.log10(1.76e9),   # 1.76 GHz (R820T2 tuner maximum)
        num=30              # 30 test points
    )
    
    print("Testing {} frequency points".format(len(test_frequencies)))
    print("Frequency range: {:.1f} MHz to {:.1f} MHz".format(
        test_frequencies[0]/1e6, test_frequencies[-1]/1e6))
    
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
    
    print("STARTING SCAN")
    
    for i, center_freq in enumerate(test_frequencies):
        try:
            # Set center frequency - clamp to safe range
            safe_freq = int(max(50e6, min(2.2e9, center_freq)))
            
            # Skip known problematic frequency ranges
            # The 1.05-1.2 GHz range causes issues on many RTL-SDR dongles
            if 1.05e9 <= safe_freq <= 1.2e9:
                print("SKIP: {:.1f} MHz (known problematic range)".format(safe_freq/1e6))
                results['skipped'].append(float(safe_freq))
                continue
            
            sdr.center_freq = safe_freq
            
            # Let hardware settle
            time.sleep(0.1)
            
            # Read samples
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
            dynamic_range = np.max(psd_db) - noise_floor
            
            # Calculate raw sensitivity
            raw_sensitivity = noise_floor + 100  # Normalize to positive values
            
            # Combine metrics
            sensitivity = raw_sensitivity + (dynamic_range * 0.5)
            
            # Store results
            results['frequencies'].append(float(safe_freq))
            results['sensitivities'].append(float(sensitivity))
            results['noise_floors'].append(float(noise_floor))
            results['dynamic_ranges'].append(float(dynamic_range))
            
            print("DATA: {:.1f} MHz | NF: {:.1f} dB | DR: {:.1f} dB | Sens: {:.1f}".format(
                safe_freq/1e6, noise_floor, dynamic_range, sensitivity))
            
            # Save progress after each point
            np.save(output_prefix + "_frequencies.npy", np.array(results['frequencies']))
            np.save(output_prefix + "_sensitivities.npy", np.array(results['sensitivities']))
            np.save(output_prefix + "_noise_floors.npy", np.array(results['noise_floors']))
            
            # Save normalized sensitivities
            sens_array = np.array(results['sensitivities'])
            if len(sens_array) > 0:
                sens_min = np.min(sens_array)
                sens_max = np.max(sens_array)
                if sens_max > sens_min:
                    normalized = ((sens_array - sens_min) / (sens_max - sens_min)) * 100
                else:
                    normalized = np.full(len(sens_array), 50.0)
                np.save(output_prefix + "_sensitivities_normalized.npy", normalized)
            
        except OSError as e:
            print("USB ERROR at {:.1f} MHz - stopping scan".format(center_freq/1e6))
            print("  Error details: {}".format(str(e)))
            break
        except Exception as e:
            print("ERROR at {:.1f} MHz: {}".format(center_freq/1e6, str(e)))
            import traceback
            traceback.print_exc()
            results['skipped'].append(float(center_freq))
            continue
    
    sdr.close()
    
    # Check if we got any valid data
    if not results['frequencies']:
        print("ERROR: No valid frequency measurements obtained!")
        print("Skipped {} frequencies".format(len(results['skipped'])))
        if results['skipped']:
            print("Skipped range: {:.1f} - {:.1f} MHz".format(
                min(results['skipped'])/1e6, 
                max(results['skipped'])/1e6
            ))
        sys.exit(1)
    
    print("SCAN COMPLETE: {} frequency points measured".format(len(results['frequencies'])))
    
    # Final normalization
    sens_array = np.array(results['sensitivities'])
    sens_min = np.min(sens_array)
    sens_max = np.max(sens_array)
    
    if sens_max > sens_min:
        normalized = ((sens_array - sens_min) / (sens_max - sens_min)) * 100
    else:
        normalized = np.full(len(sens_array), 50.0)
    
    # Save final results
    np.save(output_prefix + "_frequencies.npy", np.array(results['frequencies']))
    np.save(output_prefix + "_sensitivities.npy", np.array(results['sensitivities']))
    np.save(output_prefix + "_sensitivities_normalized.npy", normalized)
    np.save(output_prefix + "_noise_floors.npy", np.array(results['noise_floors']))
    np.save(output_prefix + "_dynamic_ranges.npy", np.array(results['dynamic_ranges']))
    
    # Save metadata
    metadata = {
        'gain': gain,
        'num_points': len(results['frequencies']),
        'freq_min': float(np.min(results['frequencies'])),
        'freq_max': float(np.max(results['frequencies'])),
        'skipped': results['skipped'],
        'complete': True
    }
    
    with open(output_prefix + "_metadata.json", 'w') as f:
        json.dump(metadata, f)
    
    # Analyze and print results
    analyze_results(results['frequencies'], normalized, results['noise_floors'])
    
    print("Results saved to: {}*".format(output_prefix))


def analyze_results(frequencies, normalized, noise_floors):
    """Analyze and print characterization results"""
    
    # Find peak sensitivity
    best_idx = np.argmax(normalized)
    best_freq = frequencies[best_idx]
    best_sens = normalized[best_idx]
    
    print("\nANALYSIS:")
    print("  Peak sensitivity: {:.1f}% at {:.1f} MHz".format(best_sens, best_freq/1e6))
    
    # Define known frequency bands
    known_bands = [
        {'name': 'FM Radio', 'start': 88e6, 'end': 108e6},
        {'name': 'Air Band', 'start': 118e6, 'end': 137e6},
        {'name': 'Weather Satellites', 'start': 137e6, 'end': 138e6},
        {'name': '2m Ham', 'start': 144e6, 'end': 148e6},
        {'name': '70cm Ham', 'start': 420e6, 'end': 450e6},
    ]
    
    print("\nKNOWN FREQUENCY BANDS:")
    optimal_bands = []
    
    for band in known_bands:
        # Find data points in this band
        band_sensitivities = [
            normalized[i] for i, freq in enumerate(frequencies)
            if band['start'] <= freq <= band['end']
        ]
        
        if band_sensitivities:
            avg_sens = np.mean(band_sensitivities)
            
            if avg_sens > 70:
                category = "EXCELLENT"
                optimal_bands.append({'name': band['name'], 'sensitivity': avg_sens})
            elif avg_sens > 50:
                category = "GOOD"
            elif avg_sens > 30:
                category = "MODERATE"
            else:
                category = "POOR"
            
            print("  {:<25s} {:>6.1f}%  [{}]".format(
                band['name'], avg_sens, category))
    
    if optimal_bands:
        print("\nANTENNA OPTIMIZED FOR:")
        for band in sorted(optimal_bands, key=lambda x: x['sensitivity'], reverse=True):
            print("  - {} ({:.1f}% sensitivity)".format(band['name'], band['sensitivity']))


def main():
    """Main function"""
    
    # Parse command line arguments
    gain = 40  # Default gain
    if len(sys.argv) > 1:
        try:
            gain = int(sys.argv[1])
        except ValueError:
            print("Error: Gain must be an integer")
            sys.exit(1)
    
    # Run scan
    scan_antenna_characteristics(gain=gain)


if __name__ == '__main__':
    main()
