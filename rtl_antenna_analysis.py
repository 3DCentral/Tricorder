#!/usr/bin/env python3
"""
rtl_antenna_analysis.py - RTL-SDR Antenna Characterization Tool

This tool performs a comprehensive frequency sweep to characterize antenna behavior
and identify resonant frequencies by analyzing the noise floor and signal response
across the entire RTL-SDR frequency range.

Usage:
    python rtl_antenna_analysis.py [options]

Options:
    --start FREQ     Start frequency in MHz (default: 24)
    --end FREQ       End frequency in MHz (default: 1700)
    --step FREQ      Step size in MHz (default: 10)
    --samples NUM    Number of samples per frequency (default: 8192)
    --gain VALUE     SDR gain in dB (default: auto)
    --output FILE    Output report filename (default: antenna_analysis.txt)
    --plot FILE      Save plot to file (default: antenna_response.png)

Theory:
    - At resonant frequencies, the antenna couples efficiently with electromagnetic waves
    - Better coupling = higher noise floor (more thermal noise captured)
    - Poor coupling = lower noise floor (antenna is mismatched)
    - This tool measures noise floor across frequencies to map antenna response

The script will:
    1. Sweep the specified frequency range
    2. Measure noise floor at each frequency
    3. Identify resonance peaks
    4. Calculate bandwidth at each resonance
    5. Generate detailed report and visualization

Author: Claude
Date: 2026-01-22
"""

import sys
import time
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from scipy import signal as scipy_signal
from scipy.signal import find_peaks
from rtlsdr import RtlSdr


class AntennaAnalyzer:
    """RTL-SDR Antenna Analysis Tool"""
    
    def __init__(self, start_freq_mhz=24, end_freq_mhz=1700, step_mhz=10, 
                 num_samples=8192, gain='auto'):
        """
        Initialize antenna analyzer
        
        Args:
            start_freq_mhz: Start frequency in MHz
            end_freq_mhz: End frequency in MHz
            step_mhz: Step size in MHz
            num_samples: Number of samples per frequency point
            gain: SDR gain (dB) or 'auto'
        """
        self.start_freq = start_freq_mhz * 1e6
        self.end_freq = end_freq_mhz * 1e6
        self.step = step_mhz * 1e6
        self.num_samples = num_samples
        self.gain = gain
        
        # Results storage
        self.frequencies = []
        self.noise_floors = []
        self.resonances = []
        
        # SDR parameters
        self.sample_rate = 2.4e6  # 2.4 MHz bandwidth
        self.freq_correction = 60  # PPM
        
    def setup_sdr(self):
        """Initialize and configure the SDR"""
        print("\n" + "="*70)
        print("RTL-SDR ANTENNA ANALYSIS TOOL")
        print("="*70)
        print("\nInitializing SDR...")
        
        self.sdr = RtlSdr()
        self.sdr.sample_rate = self.sample_rate
        self.sdr.freq_correction = self.freq_correction
        
        if self.gain == 'auto':
            self.sdr.gain = 'auto'
            print("  Gain: AUTO")
        else:
            self.sdr.gain = float(self.gain)
            print("  Gain: {} dB".format(self.sdr.gain))
        
        # Discard initial samples
        _ = self.sdr.read_samples(2048)
        
        print("  Sample rate: {:.1f} MHz".format(self.sample_rate / 1e6))
        print("  Frequency correction: {} PPM".format(self.freq_correction))
        print("\nSDR initialized successfully!")
        
    def compute_noise_floor(self, samples):
        """
        Compute noise floor from IQ samples
        
        The noise floor is estimated as the median power level, which is
        robust to strong signals that might be present.
        
        Args:
            samples: Complex IQ samples from SDR
            
        Returns:
            noise_floor_db: Noise floor in dB
        """
        # Apply window to reduce spectral leakage
        window = np.hanning(len(samples))
        samples_windowed = samples * window
        
        # Compute FFT
        fft_result = np.fft.fft(samples_windowed)
        
        # Compute power spectrum
        power_spectrum = np.abs(fft_result)**2
        
        # Convert to dB
        power_db = 10 * np.log10(power_spectrum + 1e-10)
        
        # Use median as noise floor (robust to signals)
        # Alternatively, use percentile for even more robustness
        noise_floor = np.percentile(power_db, 50)  # 50th percentile = median
        
        return noise_floor
    
    def sweep_frequency_range(self):
        """
        Perform frequency sweep and measure noise floor at each point
        """
        print("\n" + "="*70)
        print("FREQUENCY SWEEP")
        print("="*70)
        print("  Start: {:.1f} MHz".format(self.start_freq / 1e6))
        print("  End: {:.1f} MHz".format(self.end_freq / 1e6))
        print("  Step: {:.1f} MHz".format(self.step / 1e6))
        print("  Samples per point: {}".format(self.num_samples))
        
        # Calculate number of steps
        num_steps = int((self.end_freq - self.start_freq) / self.step) + 1
        print("  Total measurements: {}".format(num_steps))
        
        # Estimate time
        time_per_step = 0.5  # seconds (rough estimate)
        estimated_time = num_steps * time_per_step / 60
        print("  Estimated time: {:.1f} minutes".format(estimated_time))
        
        print("\nStarting sweep...\n")
        
        start_time = time.time()
        
        for i, freq in enumerate(np.arange(self.start_freq, self.end_freq + self.step, self.step)):
            # Set center frequency
            self.sdr.center_freq = int(freq)
            
            # Allow SDR to settle
            time.sleep(0.05)
            
            # Read samples
            samples = self.sdr.read_samples(self.num_samples)
            
            # Compute noise floor
            noise_floor = self.compute_noise_floor(samples)
            
            # Store results
            self.frequencies.append(freq)
            self.noise_floors.append(noise_floor)
            
            # Progress indicator
            if (i + 1) % 10 == 0 or i == 0:
                progress = (i + 1) / num_steps * 100
                elapsed = time.time() - start_time
                eta = (elapsed / (i + 1)) * (num_steps - i - 1)
                print("  [{:6.2f}%] {:.1f} MHz | Noise: {:6.1f} dB | ETA: {:.1f}s".format(
                    progress, freq / 1e6, noise_floor, eta))
        
        elapsed = time.time() - start_time
        print("\nSweep complete!")
        print("  Total time: {:.1f} seconds".format(elapsed))
        print("  Average time per point: {:.2f} seconds".format(elapsed / num_steps))
        
        # Convert to numpy arrays
        self.frequencies = np.array(self.frequencies)
        self.noise_floors = np.array(self.noise_floors)
        
    def smooth_data(self, window_size=5):
        """
        Apply moving average smoothing to reduce measurement noise
        
        Args:
            window_size: Size of smoothing window
        """
        if len(self.noise_floors) < window_size:
            return self.noise_floors
        
        # Apply moving average
        smoothed = np.convolve(self.noise_floors, 
                              np.ones(window_size)/window_size, 
                              mode='same')
        
        return smoothed
    
    def find_resonances(self, smoothed_data, prominence=2.0, min_distance=10):
        """
        Identify resonance peaks in the noise floor data
        
        Args:
            smoothed_data: Smoothed noise floor data
            prominence: Minimum prominence of peaks (dB)
            min_distance: Minimum distance between peaks (data points)
            
        Returns:
            resonance_info: List of dictionaries with resonance information
        """
        print("\n" + "="*70)
        print("RESONANCE DETECTION")
        print("="*70)
        
        # Find peaks in smoothed data
        peaks, properties = find_peaks(smoothed_data, 
                                      prominence=prominence,
                                      distance=min_distance)
        
        print("  Prominence threshold: {:.1f} dB".format(prominence))
        print("  Minimum peak separation: {} points ({:.1f} MHz)".format(
            min_distance, min_distance * self.step / 1e6))
        print("  Peaks found: {}".format(len(peaks)))
        
        # Extract resonance information
        resonances = []
        
        for i, peak_idx in enumerate(peaks):
            freq = self.frequencies[peak_idx]
            noise_floor = smoothed_data[peak_idx]
            prominence_val = properties['prominences'][i]
            
            # Calculate bandwidth (FWHM - Full Width at Half Maximum)
            # Find points where signal drops to half the prominence
            half_prom = noise_floor - prominence_val / 2
            
            # Search left
            left_idx = peak_idx
            while left_idx > 0 and smoothed_data[left_idx] > half_prom:
                left_idx -= 1
            
            # Search right
            right_idx = peak_idx
            while right_idx < len(smoothed_data) - 1 and smoothed_data[right_idx] > half_prom:
                right_idx += 1
            
            # Calculate bandwidth
            left_freq = self.frequencies[left_idx]
            right_freq = self.frequencies[right_idx]
            bandwidth = right_freq - left_freq
            
            resonance = {
                'index': i + 1,
                'frequency': freq,
                'noise_floor': noise_floor,
                'prominence': prominence_val,
                'bandwidth': bandwidth,
                'q_factor': freq / bandwidth if bandwidth > 0 else 0,
                'left_freq': left_freq,
                'right_freq': right_freq
            }
            
            resonances.append(resonance)
        
        self.resonances = resonances
        return resonances
    
    def check_harmonics(self):
        """
        Check if detected resonances are harmonically related
        
        This can indicate a fundamental resonance with harmonics
        """
        if len(self.resonances) < 2:
            return
        
        print("\n" + "="*70)
        print("HARMONIC ANALYSIS")
        print("="*70)
        
        # Check each resonance against others
        for i, res1 in enumerate(self.resonances):
            f1 = res1['frequency']
            
            harmonics_found = []
            
            for j, res2 in enumerate(self.resonances):
                if i == j:
                    continue
                
                f2 = res2['frequency']
                
                # Check if f2 is approximately a harmonic of f1
                ratio = f2 / f1
                
                # Check if ratio is close to an integer (within 5%)
                nearest_int = round(ratio)
                if nearest_int > 1 and abs(ratio - nearest_int) / nearest_int < 0.05:
                    harmonics_found.append({
                        'harmonic_number': nearest_int,
                        'frequency': f2,
                        'expected': f1 * nearest_int,
                        'error_pct': abs(f2 - f1 * nearest_int) / (f1 * nearest_int) * 100
                    })
            
            if harmonics_found:
                print("\nPotential fundamental: {:.2f} MHz".format(f1 / 1e6))
                for h in harmonics_found:
                    print("  {}x harmonic: {:.2f} MHz (expected: {:.2f} MHz, error: {:.2f}%)".format(
                        h['harmonic_number'], h['frequency'] / 1e6, 
                        h['expected'] / 1e6, h['error_pct']))
    
    def generate_report(self, output_file='antenna_analysis.txt'):
        """
        Generate detailed text report of antenna analysis
        
        Args:
            output_file: Output filename
        """
        print("\n" + "="*70)
        print("GENERATING REPORT")
        print("="*70)
        
        with open(output_file, 'w') as f:
            # Header
            f.write("="*70 + "\n")
            f.write("RTL-SDR ANTENNA ANALYSIS REPORT\n")
            f.write("="*70 + "\n")
            f.write("Generated: {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
            f.write("\n")
            
            # Scan parameters
            f.write("SCAN PARAMETERS\n")
            f.write("-"*70 + "\n")
            f.write("Frequency range: {:.1f} - {:.1f} MHz\n".format(
                self.start_freq / 1e6, self.end_freq / 1e6))
            f.write("Step size: {:.1f} MHz\n".format(self.step / 1e6))
            f.write("Samples per point: {}\n".format(self.num_samples))
            f.write("SDR gain: {}\n".format(self.gain))
            f.write("Total measurements: {}\n".format(len(self.frequencies)))
            f.write("\n")
            
            # Overall statistics
            f.write("OVERALL STATISTICS\n")
            f.write("-"*70 + "\n")
            f.write("Mean noise floor: {:.2f} dB\n".format(np.mean(self.noise_floors)))
            f.write("Std deviation: {:.2f} dB\n".format(np.std(self.noise_floors)))
            f.write("Min noise floor: {:.2f} dB at {:.1f} MHz\n".format(
                np.min(self.noise_floors), 
                self.frequencies[np.argmin(self.noise_floors)] / 1e6))
            f.write("Max noise floor: {:.2f} dB at {:.1f} MHz\n".format(
                np.max(self.noise_floors), 
                self.frequencies[np.argmax(self.noise_floors)] / 1e6))
            f.write("Dynamic range: {:.2f} dB\n".format(
                np.max(self.noise_floors) - np.min(self.noise_floors)))
            f.write("\n")
            
            # Resonances
            f.write("DETECTED RESONANCES\n")
            f.write("-"*70 + "\n")
            f.write("Number of resonances: {}\n".format(len(self.resonances)))
            f.write("\n")
            
            if self.resonances:
                for res in self.resonances:
                    f.write("Resonance #{}\n".format(res['index']))
                    f.write("  Frequency: {:.2f} MHz\n".format(res['frequency'] / 1e6))
                    f.write("  Noise floor: {:.2f} dB\n".format(res['noise_floor']))
                    f.write("  Prominence: {:.2f} dB\n".format(res['prominence']))
                    f.write("  Bandwidth (FWHM): {:.2f} MHz ({:.0f} kHz)\n".format(
                        res['bandwidth'] / 1e6, res['bandwidth'] / 1e3))
                    f.write("  Frequency range: {:.2f} - {:.2f} MHz\n".format(
                        res['left_freq'] / 1e6, res['right_freq'] / 1e6))
                    f.write("  Q factor: {:.1f}\n".format(res['q_factor']))
                    f.write("\n")
            else:
                f.write("No clear resonances detected.\n")
                f.write("This may indicate:\n")
                f.write("  - Broadband antenna design\n")
                f.write("  - Antenna not optimized for this frequency range\n")
                f.write("  - Measurement noise masking resonances\n")
                f.write("\n")
            
            # Recommendations
            f.write("INTERPRETATION\n")
            f.write("-"*70 + "\n")
            f.write("The noise floor measurement technique works as follows:\n")
            f.write("  - Higher noise floor = better antenna coupling (resonance)\n")
            f.write("  - Lower noise floor = poor antenna coupling (mismatch)\n")
            f.write("\n")
            
            if self.resonances:
                primary = self.resonances[0]
                f.write("PRIMARY RESONANCE: {:.2f} MHz\n".format(primary['frequency'] / 1e6))
                f.write("  This is likely the fundamental resonant frequency of your antenna.\n")
                f.write("  The antenna is most efficient near this frequency.\n")
                f.write("\n")
                
                if len(self.resonances) > 1:
                    f.write("ADDITIONAL RESONANCES:\n")
                    for res in self.resonances[1:]:
                        f.write("  {:.2f} MHz - ".format(res['frequency'] / 1e6))
                        # Check if harmonic
                        ratio = res['frequency'] / primary['frequency']
                        nearest_int = round(ratio)
                        if nearest_int > 1 and abs(ratio - nearest_int) / nearest_int < 0.05:
                            f.write("Likely {}x harmonic of primary\n".format(nearest_int))
                        else:
                            f.write("Independent resonance\n")
                    f.write("\n")
            
            f.write("RECOMMENDATIONS:\n")
            if self.resonances:
                primary = self.resonances[0]
                f.write("  - Use frequencies near {:.2f} MHz for best performance\n".format(
                    primary['frequency'] / 1e6))
                f.write("  - Usable bandwidth: {:.2f} - {:.2f} MHz\n".format(
                    primary['left_freq'] / 1e6, primary['right_freq'] / 1e6))
                if primary['q_factor'] > 10:
                    f.write("  - High Q factor ({:.1f}) indicates narrow-band antenna\n".format(
                        primary['q_factor']))
                else:
                    f.write("  - Low Q factor ({:.1f}) indicates broad-band antenna\n".format(
                        primary['q_factor']))
            else:
                f.write("  - Consider using a different antenna for this frequency range\n")
                f.write("  - Or verify antenna connection and placement\n")
            
            f.write("\n")
            f.write("="*70 + "\n")
            f.write("End of report\n")
            f.write("="*70 + "\n")
        
        print("  Report saved to: {}".format(output_file))
    
    def plot_results(self, output_file='antenna_response.png'):
        """
        Generate visualization of antenna response
        
        Args:
            output_file: Output filename for plot
        """
        print("  Generating plot...")
        
        # Smooth data for plotting
        smoothed = self.smooth_data(window_size=5)
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Plot 1: Full frequency response
        ax1.plot(self.frequencies / 1e6, self.noise_floors, 
                'b-', alpha=0.3, linewidth=0.5, label='Raw data')
        ax1.plot(self.frequencies / 1e6, smoothed, 
                'b-', linewidth=2, label='Smoothed')
        
        # Mark resonances
        for res in self.resonances:
            ax1.axvline(res['frequency'] / 1e6, color='r', 
                       linestyle='--', alpha=0.5, linewidth=1)
            ax1.plot(res['frequency'] / 1e6, res['noise_floor'], 
                    'ro', markersize=8)
            ax1.text(res['frequency'] / 1e6, res['noise_floor'] + 1, 
                    '#{}\n{:.1f} MHz'.format(res['index'], res['frequency'] / 1e6),
                    ha='center', va='bottom', fontsize=8,
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
        
        ax1.set_xlabel('Frequency (MHz)', fontsize=12)
        ax1.set_ylabel('Noise Floor (dB)', fontsize=12)
        ax1.set_title('Antenna Frequency Response (Full Range)', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Plot 2: Zoomed view of primary resonance (if exists)
        if self.resonances:
            primary = self.resonances[0]
            center = primary['frequency']
            
            # Zoom to +/- 50 MHz around primary resonance
            zoom_range = 50e6
            zoom_start = max(self.start_freq, center - zoom_range)
            zoom_end = min(self.end_freq, center + zoom_range)
            
            # Find indices in zoom range
            zoom_mask = (self.frequencies >= zoom_start) & (self.frequencies <= zoom_end)
            zoom_freqs = self.frequencies[zoom_mask]
            zoom_noise = self.noise_floors[zoom_mask]
            zoom_smoothed = smoothed[zoom_mask]
            
            ax2.plot(zoom_freqs / 1e6, zoom_noise, 
                    'b-', alpha=0.3, linewidth=0.5, label='Raw data')
            ax2.plot(zoom_freqs / 1e6, zoom_smoothed, 
                    'b-', linewidth=2, label='Smoothed')
            
            # Mark primary resonance
            ax2.axvline(primary['frequency'] / 1e6, color='r', 
                       linestyle='--', alpha=0.5, linewidth=1)
            ax2.plot(primary['frequency'] / 1e6, primary['noise_floor'], 
                    'ro', markersize=10)
            
            # Mark bandwidth
            ax2.axvline(primary['left_freq'] / 1e6, color='g', 
                       linestyle=':', alpha=0.5, linewidth=1)
            ax2.axvline(primary['right_freq'] / 1e6, color='g', 
                       linestyle=':', alpha=0.5, linewidth=1)
            ax2.axhspan(primary['noise_floor'] - primary['prominence']/2, 
                       primary['noise_floor'], 
                       alpha=0.2, color='green', 
                       label='Bandwidth (FWHM)')
            
            ax2.set_xlabel('Frequency (MHz)', fontsize=12)
            ax2.set_ylabel('Noise Floor (dB)', fontsize=12)
            ax2.set_title('Primary Resonance Detail: {:.2f} MHz (BW: {:.2f} MHz, Q: {:.1f})'.format(
                primary['frequency'] / 1e6, primary['bandwidth'] / 1e6, primary['q_factor']),
                fontsize=14, fontweight='bold')
            ax2.grid(True, alpha=0.3)
            ax2.legend()
        else:
            # No resonances - show full range in second plot too
            ax2.plot(self.frequencies / 1e6, self.noise_floors, 
                    'b-', alpha=0.5, linewidth=1)
            ax2.set_xlabel('Frequency (MHz)', fontsize=12)
            ax2.set_ylabel('Noise Floor (dB)', fontsize=12)
            ax2.set_title('No Clear Resonances Detected', fontsize=14, fontweight='bold')
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        
        print("  Plot saved to: {}".format(output_file))
    
    def run_analysis(self, report_file='antenna_analysis.txt', 
                    plot_file='antenna_response.png'):
        """
        Run complete antenna analysis
        
        Args:
            report_file: Output filename for text report
            plot_file: Output filename for plot
        """
        try:
            # Setup SDR
            self.setup_sdr()
            
            # Perform sweep
            self.sweep_frequency_range()
            
            # Smooth data
            smoothed = self.smooth_data(window_size=5)
            
            # Find resonances
            self.find_resonances(smoothed, prominence=2.0, min_distance=10)
            
            # Check for harmonics
            self.check_harmonics()
            
            # Generate outputs
            self.generate_report(report_file)
            self.plot_results(plot_file)
            
            print("\n" + "="*70)
            print("ANALYSIS COMPLETE!")
            print("="*70)
            print("\nOutput files:")
            print("  Report: {}".format(report_file))
            print("  Plot: {}".format(plot_file))
            
            if self.resonances:
                print("\nPrimary resonance: {:.2f} MHz".format(
                    self.resonances[0]['frequency'] / 1e6))
                print("Bandwidth: {:.2f} MHz".format(
                    self.resonances[0]['bandwidth'] / 1e6))
                print("Q factor: {:.1f}".format(
                    self.resonances[0]['q_factor']))
            else:
                print("\nNo clear resonances detected.")
                print("Review the plot and report for details.")
            
            print("\n")
            
        finally:
            # Clean up
            if hasattr(self, 'sdr'):
                self.sdr.close()
                print("SDR closed.\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='RTL-SDR Antenna Characterization Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full spectrum analysis (24-1700 MHz, 10 MHz steps)
  python rtl_antenna_analysis.py
  
  # FM broadcast band analysis (88-108 MHz, 1 MHz steps)
  python rtl_antenna_analysis.py --start 88 --end 108 --step 1
  
  # VHF analysis with finer resolution (140-160 MHz, 0.5 MHz steps)
  python rtl_antenna_analysis.py --start 140 --end 160 --step 0.5
  
  # Quick scan with fixed gain (400-500 MHz, 5 MHz steps)
  python rtl_antenna_analysis.py --start 400 --end 500 --step 5 --gain 20

Note: The analysis uses the noise floor technique - higher noise floor
      indicates better antenna coupling (resonance) at that frequency.
        """)
    
    parser.add_argument('--start', type=float, default=24,
                       help='Start frequency in MHz (default: 24)')
    parser.add_argument('--end', type=float, default=1700,
                       help='End frequency in MHz (default: 1700)')
    parser.add_argument('--step', type=float, default=10,
                       help='Step size in MHz (default: 10)')
    parser.add_argument('--samples', type=int, default=8192,
                       help='Number of samples per point (default: 8192)')
    parser.add_argument('--gain', default='auto',
                       help='SDR gain in dB or "auto" (default: auto)')
    parser.add_argument('--output', default='antenna_analysis.txt',
                       help='Output report filename (default: antenna_analysis.txt)')
    parser.add_argument('--plot', default='antenna_response.png',
                       help='Output plot filename (default: antenna_response.png)')
    
    args = parser.parse_args()
    
    # Create analyzer
    analyzer = AntennaAnalyzer(
        start_freq_mhz=args.start,
        end_freq_mhz=args.end,
        step_mhz=args.step,
        num_samples=args.samples,
        gain=args.gain
    )
    
    # Run analysis
    analyzer.run_analysis(
        report_file=args.output,
        plot_file=args.plot
    )


if __name__ == "__main__":
    main()
