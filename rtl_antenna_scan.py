#!/usr/bin/env python3
"""
rtl_antenna_scan.py - Background Antenna Characterization Scanner

Performs a wide-spectrum antenna characterization sweep and saves all results
to /tmp/antenna_scan_*.npy for the GUI to poll.

What it measures and why:
    At each frequency we tune the SDR and measure the median power level
    (noise floor) across the 2.4 MHz bandwidth.  Where the antenna couples
    well to the environment it picks up more ambient noise, so the noise
    floor rises.  Where it is mismatched, less noise gets in.  Peaks in the
    noise floor curve correspond to frequencies where the antenna is
    efficient -- its resonances.

Output files (written progressively so the GUI can show live data):
    antenna_scan_frequencies.npy            - frequency of each sample (Hz)
    antenna_scan_noise_floors.npy           - median noise floor (dB)
    antenna_scan_dynamic_ranges.npy         - max - median at each point (dB)
    antenna_scan_resonances.npy             - structured array of detected
                                              resonances (written once after
                                              the sweep finishes and analysis
                                              runs)
    antenna_scan_metadata.json              - gain, point count, completion flag
"""

from rtlsdr import RtlSdr
import numpy as np
from scipy import signal
from scipy.signal import find_peaks
import sys
import json
import time


# ---------------------------------------------------------------------------
# Scan parameters
# ---------------------------------------------------------------------------
SAMPLE_RATE   = 2.4e6       # Hz - RTL-SDR bandwidth per tune
FFT_SIZE      = 512         # Welch segment length (up from 256)
NUM_ROWS      = 200         # samples = FFT_SIZE * NUM_ROWS.  Welch with 50 %
                            # overlap yields ~(NUM_ROWS*2 - 1) averaged segments,
                            # giving a much more stable median than the old
                            # FFT_SIZE=256 / NUM_ROWS=100 combination.
FREQ_MIN      = 60e6        # Hz - safe lower limit for R820T2
FREQ_MAX      = 1.76e9      # Hz - R820T2 tuner max
NUM_POINTS    = 60          # Log-spaced sample points (up from 30)
SETTLE_TIME   = 0.05        # Seconds to let the tuner settle after retuning

# No frequency ranges are skipped.  The R820T2 can return noisy readings at
# certain frequencies near its internal LO harmonics (~1.1-1.15 GHz), but this
# just means those data points will have inaccurate noise-floor values — it does
# not crash the hardware or the process.  Skipping entire ranges was masking a
# real bug (OSError handling) and breaking targeted scans for bands like ADS-B
# at 1090 MHz that fell inside the old exclusion zone.


def measure_noise_floor(sdr):
    """
    Read samples and return (noise_floor_db, dynamic_range_db).

    Uses Welch's method to estimate the PSD across the full 2.4 MHz window,
    then takes the median as the noise floor (robust to any strong signal
    present in the band) and the dynamic range as max - median.
    """
    samples = sdr.read_samples(FFT_SIZE * NUM_ROWS)

    _freqs, psd = signal.welch(
        samples,
        fs=sdr.sample_rate,
        nperseg=FFT_SIZE,
        window='hann',
        noverlap=FFT_SIZE // 2
    )

    psd_db = 10 * np.log10(psd + 1e-10)

    noise_floor    = float(np.median(psd_db))
    dynamic_range  = float(np.max(psd_db) - noise_floor)

    return noise_floor, dynamic_range


# ---------------------------------------------------------------------------
# Post-sweep analysis  (ported and adapted from rtl_antenna_analysis.py)
# ---------------------------------------------------------------------------

def smooth(data, window=5):
    """Moving-average smooth.  Reduces per-point measurement jitter before
    peak detection so we don't chase noise spikes."""
    if len(data) < window:
        return data.copy()
    return np.convolve(data, np.ones(window) / window, mode='same')


def find_resonances(frequencies, noise_floors, prominence=2.0, min_distance=3):
    """
    Detect resonance peaks in the smoothed noise-floor curve.

    prominence   - minimum height a peak must rise above its surroundings (dB).
                   2 dB is a reasonable floor; broadband antennas with very
                   gradual curves may need this lowered.
    min_distance - minimum separation between peaks in data-point indices.
                   With 60 log-spaced points this is intentionally low so we
                   don't accidentally merge two close but independent resonances
                   (e.g. 2m and Air Band are only ~7 MHz apart).

    Each resonance dict contains:
        frequency     - center (Hz)
        noise_floor   - smoothed value at peak (dB)
        prominence    - scipy prominence (dB)
        bandwidth     - FWHM: distance between the two points where the curve
                        drops to half the prominence below the peak (Hz)
        q_factor      - frequency / bandwidth  (high Q = narrow-band,
                        low Q = broadband)
        left_freq     - lower FWHM edge (Hz)
        right_freq    - upper FWHM edge (Hz)
    """
    smoothed = smooth(noise_floors)

    peaks, props = find_peaks(
        smoothed,
        prominence=prominence,
        distance=min_distance
    )

    resonances = []
    for i, pidx in enumerate(peaks):
        freq   = frequencies[pidx]
        nf     = smoothed[pidx]
        prom   = props['prominences'][i]
        half   = nf - prom / 2.0          # the "half-prominence" threshold

        # Walk left until we drop below half-prominence
        left = pidx
        while left > 0 and smoothed[left] > half:
            left -= 1

        # Walk right
        right = pidx
        while right < len(smoothed) - 1 and smoothed[right] > half:
            right += 1

        left_freq  = frequencies[left]
        right_freq = frequencies[right]
        bw         = right_freq - left_freq

        resonances.append({
            'frequency':   float(freq),
            'noise_floor': float(nf),
            'prominence':  float(prom),
            'bandwidth':   float(bw),
            'q_factor':    float(freq / bw) if bw > 0 else 0.0,
            'left_freq':   float(left_freq),
            'right_freq':  float(right_freq),
        })

    # Sort by prominence descending -- strongest resonance first.
    resonances.sort(key=lambda r: r['prominence'], reverse=True)
    return resonances


def check_harmonics(resonances, tolerance=0.05):
    """
    Tag resonances that are likely integer harmonics of another resonance.

    Walk the list in prominence order so the strongest candidate fundamental
    gets first claim.  A resonance is tagged as a harmonic of r1 when
    its frequency is within 'tolerance' (5 %) of an integer multiple of r1.

    Adds a 'harmonic_of' key to each dict:
        None                          -> independent fundamental
        { fundamental_freq, n, err }  -> likely the nth harmonic
    """
    for res in resonances:
        res['harmonic_of'] = None

    for i, r1 in enumerate(resonances):
        f1 = r1['frequency']
        for j, r2 in enumerate(resonances):
            if i == j:
                continue
            ratio = r2['frequency'] / f1
            n     = round(ratio)
            if n >= 2 and abs(ratio - n) / n < tolerance:
                if r2['harmonic_of'] is None:   # first (strongest) match wins
                    r2['harmonic_of'] = {
                        'fundamental_freq': float(f1),
                        'harmonic_number':  n,
                        'error_pct':        float(abs(ratio - n) / n * 100),
                    }


# ---------------------------------------------------------------------------
# Structured numpy dtype for the resonances file
# ---------------------------------------------------------------------------
RESONANCE_DTYPE = np.dtype([
    ('frequency',        'f8'),
    ('noise_floor',      'f8'),
    ('prominence',       'f8'),
    ('bandwidth',        'f8'),
    ('q_factor',         'f8'),
    ('left_freq',        'f8'),
    ('right_freq',       'f8'),
    ('is_harmonic',      'bool'),
    ('harmonic_number',  'i4'),
    ('fundamental_freq', 'f8'),
])


def resonances_to_array(resonances):
    """Convert list of resonance dicts to a structured numpy array."""
    arr = np.zeros(len(resonances), dtype=RESONANCE_DTYPE)
    for idx, r in enumerate(resonances):
        arr[idx]['frequency']        = r['frequency']
        arr[idx]['noise_floor']      = r['noise_floor']
        arr[idx]['prominence']       = r['prominence']
        arr[idx]['bandwidth']        = r['bandwidth']
        arr[idx]['q_factor']         = r['q_factor']
        arr[idx]['left_freq']        = r['left_freq']
        arr[idx]['right_freq']       = r['right_freq']
        if r['harmonic_of']:
            arr[idx]['is_harmonic']      = True
            arr[idx]['harmonic_number']  = r['harmonic_of']['harmonic_number']
            arr[idx]['fundamental_freq'] = r['harmonic_of']['fundamental_freq']
        else:
            arr[idx]['is_harmonic']      = False
            arr[idx]['harmonic_number']  = 1
            arr[idx]['fundamental_freq'] = r['frequency']
    return arr


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def scan_antenna_characteristics(gain=40, output_prefix="/tmp/antenna_scan",
                                  freq_min=None, freq_max=None, num_points=None):
    """Run the full characterisation sweep, then run post-sweep analysis.
    
    Args:
        gain: RF gain in dB
        output_prefix: Path prefix for output files
        freq_min: Minimum frequency in Hz (default: FREQ_MIN constant)
        freq_max: Maximum frequency in Hz (default: FREQ_MAX constant)
        num_points: Number of measurement points (default: NUM_POINTS constant)
    """
    
    # Use defaults if not specified
    if freq_min is None:
        freq_min = FREQ_MIN
    if freq_max is None:
        freq_max = FREQ_MAX
    if num_points is None:
        num_points = NUM_POINTS

    print("RTL-SDR ANTENNA CHARACTERIZATION")
    print("Gain: {} dB".format(gain))
    print("Frequency range: {:.3f} - {:.3f} MHz".format(freq_min/1e6, freq_max/1e6))
    print("Measurement points: {}".format(num_points))

    # --- SDR init (with retry) -----------------------------------------------
    # The RTL-SDR USB driver can take a moment to fully release after a prior
    # session (e.g. the wide scan) closes.  Retry up to 5 times with a short
    # delay before giving up.
    sdr = None
    for attempt in range(5):
        try:
            sdr = RtlSdr()
            sdr.sample_rate     = SAMPLE_RATE
            sdr.freq_correction = 60   # PPM
            sdr.gain            = gain
            _ = sdr.read_samples(2048)  # discard initial noisy samples
            break  # success
        except Exception as e:
            print("SDR init attempt {}/5 failed: {}".format(attempt + 1, e))
            if sdr is not None:
                try:
                    sdr.close()
                except Exception:
                    pass
                sdr = None
            time.sleep(1.0)

    if sdr is None:
        print("ERROR: Cannot open RTL-SDR device after 5 attempts")
        sys.exit(1)

    print("Sample rate: {:.1f} MHz".format(sdr.sample_rate / 1e6))
    print("Actual gain: {} dB".format(sdr.gain))

    # --- Frequency grid ------------------------------------------------------
    test_frequencies = np.logspace(
        np.log10(freq_min),
        np.log10(freq_max),
        num=num_points
    )

    print("Testing {} frequency points ({:.1f} - {:.1f} MHz)".format(
        num_points, freq_min / 1e6, freq_max / 1e6))

    # --- Sweep ---------------------------------------------------------------
    frequencies    = []
    noise_floors   = []
    dynamic_ranges = []
    skipped        = []

    for i, center_freq in enumerate(test_frequencies):
        safe_freq = int(np.clip(center_freq, 50e6, 2.2e9))

        try:
            sdr.center_freq = safe_freq
            time.sleep(SETTLE_TIME)

            nf, dr = measure_noise_floor(sdr)

            frequencies.append(float(safe_freq))
            noise_floors.append(nf)
            dynamic_ranges.append(dr)

            print("DATA: {:.1f} MHz | NF: {:.1f} dB | DR: {:.1f} dB".format(
                safe_freq / 1e6, nf, dr))

            # --- Save progress files (GUI polls every 200 ms) ----------------
            np.save(output_prefix + "_frequencies.npy",     np.array(frequencies))
            np.save(output_prefix + "_noise_floors.npy",    np.array(noise_floors))
            np.save(output_prefix + "_dynamic_ranges.npy",  np.array(dynamic_ranges))

        except OSError as e:
            # USB/device errors (e.g. tuner hiccup at certain frequencies) —
            # log and skip this point rather than aborting the entire scan.
            # A true device disconnect will surface again on the next iteration
            # and quickly exhaust all points, ending naturally.
            print("USB ERROR at {:.1f} MHz - skipping point".format(safe_freq / 1e6))
            print("  {}".format(e))
            skipped.append(float(safe_freq))
            time.sleep(0.1)  # brief pause to let the tuner recover
            continue
        except Exception as e:
            print("ERROR at {:.1f} MHz: {}".format(safe_freq / 1e6, e))
            skipped.append(float(safe_freq))
            continue

    sdr.close()

    # --- Guard: need data ----------------------------------------------------
    if not frequencies:
        print("ERROR: No valid measurements obtained!")
        sys.exit(1)

    print("\nSCAN COMPLETE: {} points measured".format(len(frequencies)))

    # --- Post-sweep analysis -------------------------------------------------
    freq_arr = np.array(frequencies)
    nf_arr   = np.array(noise_floors)

    resonances = find_resonances(freq_arr, nf_arr)
    check_harmonics(resonances)

    # Save resonances (structured array -- widget loads this once on completion)
    res_array = resonances_to_array(resonances)
    np.save(output_prefix + "_resonances.npy", res_array)

    if resonances:
        print("\nResonances found: {}".format(len(resonances)))
        for r in resonances:
            tag = ""
            if r['harmonic_of']:
                tag = " [{}x harmonic of {:.1f} MHz]".format(
                    r['harmonic_of']['harmonic_number'],
                    r['harmonic_of']['fundamental_freq'] / 1e6)
            print("  {:.1f} MHz | prom {:.1f} dB | BW {:.1f} MHz | Q {:.1f}{}".format(
                r['frequency'] / 1e6,
                r['prominence'],
                r['bandwidth'] / 1e6,
                r['q_factor'],
                tag))
    else:
        print("\nNo resonances detected above prominence threshold.")

    # --- Metadata ------------------------------------------------------------
    metadata = {
        'gain':           gain,
        'num_points':     len(frequencies),
        'freq_min':       float(np.min(freq_arr)),
        'freq_max':       float(np.max(freq_arr)),
        'skipped':        skipped,
        'num_resonances': len(resonances),
        'complete':       True,
    }
    with open(output_prefix + "_metadata.json", 'w') as f:
        json.dump(metadata, f)

    print("Results saved to: {}*".format(output_prefix))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='RTL-SDR Antenna Characterization Scanner'
    )
    parser.add_argument(
        'gain',
        type=int,
        nargs='?',
        default=40,
        help='RF gain in dB (default: 40)'
    )
    parser.add_argument(
        '--freq-min',
        type=float,
        default=None,
        help='Minimum frequency in Hz (default: 60 MHz for wide scan)'
    )
    parser.add_argument(
        '--freq-max',
        type=float,
        default=None,
        help='Maximum frequency in Hz (default: 1.76 GHz for wide scan)'
    )
    parser.add_argument(
        '--num-points',
        type=int,
        default=None,
        help='Number of measurement points (default: 60 for wide, 200 for targeted)'
    )
    parser.add_argument(
        '--output-prefix',
        type=str,
        default='/tmp/antenna_scan',
        help='Output file prefix (default: /tmp/antenna_scan)'
    )
    
    args = parser.parse_args()
    
    # Determine if this is a targeted scan
    is_targeted = args.freq_min is not None or args.freq_max is not None
    
    if is_targeted:
        freq_min = args.freq_min if args.freq_min else 60e6
        freq_max = args.freq_max if args.freq_max else 1.76e9
        num_points = args.num_points if args.num_points else 200  # High density for targeted
        print("TARGETED SCAN MODE")
        print("  Range: {:.3f} - {:.3f} MHz".format(freq_min/1e6, freq_max/1e6))
        print("  Points: {} (high density)".format(num_points))
    else:
        freq_min = 60e6
        freq_max = 1.76e9
        num_points = args.num_points if args.num_points else 60
        print("WIDE SCAN MODE")
        print("  Range: {:.3f} - {:.3f} MHz".format(freq_min/1e6, freq_max/1e6))
        print("  Points: {}".format(num_points))
    
    scan_antenna_characteristics(
        gain=args.gain,
        output_prefix=args.output_prefix,
        freq_min=freq_min,
        freq_max=freq_max,
        num_points=num_points,
    )


if __name__ == '__main__':
    main()
