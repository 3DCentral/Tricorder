#!/usr/bin/env python3
"""
rtl_replay.py - IQ file playback for the LCARS tricorder

Reads a recorded .npy IQ file and writes the same /tmp/*.npy files
that rtl_scan_live.py produces, at the same rate.  From the UI's
perspective the waterfall display sees identical data — it cannot
tell the difference between live and replay.

On reaching the end of the file the last frame is frozen and
/tmp/replay_status.txt is written with "COMPLETE".

Seek control:
  Write /tmp/replay_control.txt with content "SEEK <seconds>"
  to jump forward or backward in the recording.

Status output (/tmp/replay_status.txt):
  PLAYING <current_sec> <total_sec> <filename>
  COMPLETE <filename>

Usage:
    python rtl_replay.py <iq_file.npy>
"""

import sys
import os
import time
import json
import numpy as np
import shutil

# ---------------------------------------------------------------------------
# Paths (must match rtl_scan_live.py exactly)
# ---------------------------------------------------------------------------
OUTPUT_DIR              = "/tmp/"
PSD_FILE                = OUTPUT_DIR + "spectrum_live_psd.npy"
PSD_FILE_TEMP           = OUTPUT_DIR + "spectrum_live_psd_temp.npy"
WATERFALL_FILE          = OUTPUT_DIR + "spectrum_live_waterfall.npy"
WATERFALL_FILE_TEMP     = OUTPUT_DIR + "spectrum_live_waterfall_temp.npy"
FREQUENCIES_FILE        = OUTPUT_DIR + "spectrum_live_frequencies.npy"
FREQUENCIES_FILE_TEMP   = OUTPUT_DIR + "spectrum_live_frequencies_temp.npy"
METADATA_FILE           = OUTPUT_DIR + "spectrum_live_metadata.npy"
METADATA_FILE_TEMP      = OUTPUT_DIR + "spectrum_live_metadata_temp.npy"
REPLAY_CONTROL_FILE     = OUTPUT_DIR + "replay_control.txt"
REPLAY_STATUS_FILE      = OUTPUT_DIR + "replay_status.txt"

# Must match rtl_scan_live.py
FFT_SIZE         = 2048
NUM_AVERAGES     = 4
UPDATE_INTERVAL  = 0.0165   # ~60 Hz
DEFAULT_WF_LINES = 150


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_data_atomic(data, temp_path, final_path):
    np.save(temp_path, data)
    shutil.move(temp_path, final_path)


def write_replay_status(text):
    try:
        with open(REPLAY_STATUS_FILE, 'w') as f:
            f.write(text + "\n")
    except OSError:
        pass


def remove_dc_spike(psd, center_idx, window_size=50):
    """Same DC spike removal as rtl_scan_live.py."""
    from scipy.interpolate import interp1d

    start_idx = max(0, center_idx - window_size // 2)
    end_idx   = min(len(psd), center_idx + window_size // 2)

    if start_idx < 10 or end_idx > len(psd) - 10:
        return psd

    fit_x = np.concatenate([
        np.arange(max(0, start_idx - 40), start_idx),
        np.arange(end_idx, min(len(psd), end_idx + 40))
    ])
    if len(fit_x) < 10:
        return psd

    try:
        poly      = np.poly1d(np.polyfit(fit_x, psd[fit_x], deg=3))
        psd_fixed = psd.copy()
        spike     = np.arange(start_idx, end_idx)
        psd_fixed[spike] = poly(spike)

        blend = 10
        if start_idx >= blend:
            for i in range(blend):
                idx = start_idx - blend + i
                a   = i / blend
                psd_fixed[idx] = (1 - a) * psd[idx] + a * poly(idx)
        if end_idx + blend <= len(psd):
            for i in range(blend):
                idx = end_idx + i
                a   = 1 - (i / blend)
                psd_fixed[idx] = a * poly(idx) + (1 - a) * psd[idx]
        return psd_fixed

    except np.linalg.LinAlgError:
        ix = np.concatenate([
            np.arange(max(0, start_idx - 20), start_idx),
            np.arange(end_idx, min(len(psd), end_idx + 20))
        ])
        if len(ix) < 2:
            return psd
        f = interp1d(ix, psd[ix], kind='linear', fill_value='extrapolate')
        psd_fixed = psd.copy()
        psd_fixed[np.arange(start_idx, end_idx)] = f(np.arange(start_idx, end_idx))
        return psd_fixed


def compute_psd_from_chunk(chunk, fft_size):
    """FFT a block of complex samples → dB PSD (same pipeline as live)."""
    window      = np.hanning(fft_size)
    fft_shifted = np.fft.fftshift(np.fft.fft(chunk[:fft_size] * window))
    power       = np.abs(fft_shifted) ** 2
    return 10.0 * np.log10(power + 1e-10)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    iq_path = sys.argv[1]
    if not os.path.exists(iq_path):
        print("ERROR: file not found: {}".format(iq_path))
        sys.exit(1)

    # Load companion metadata JSON
    json_path = os.path.splitext(iq_path)[0] + ".json"
    if not os.path.exists(json_path):
        print("ERROR: metadata file not found: {}".format(json_path))
        sys.exit(1)

    with open(json_path, 'r') as f:
        meta = json.load(f)

    center_freq = float(meta["center_freq_hz"])
    sample_rate = float(meta["sample_rate_hz"])
    band_name   = meta.get("band_name", "UNK")
    fname       = os.path.basename(iq_path)

    print("Replay: {}".format(fname))
    print("  Center: {:.3f} MHz  SR: {:.3f} MHz  Band: {}".format(
        center_freq / 1e6, sample_rate / 1e6, band_name))

    # Load entire IQ array into memory
    iq_data = np.load(iq_path)
    if iq_data.dtype != np.complex64:
        iq_data = iq_data.astype(np.complex64)

    total_samples  = len(iq_data)
    total_duration = total_samples / sample_rate
    chunk_size     = FFT_SIZE * NUM_AVERAGES   # samples consumed per waterfall row

    print("  Duration: {:.1f}s  Samples: {}  Chunk: {}".format(
        total_duration, total_samples, chunk_size))

    # Frequency axis
    frequencies = (np.fft.fftshift(np.fft.fftfreq(FFT_SIZE, 1.0 / sample_rate))
                   + center_freq)
    center_idx  = FFT_SIZE // 2

    save_data_atomic(frequencies, FREQUENCIES_FILE_TEMP, FREQUENCIES_FILE)
    save_data_atomic(
        np.array([center_freq, sample_rate, FFT_SIZE,
                  DEFAULT_WF_LINES, UPDATE_INTERVAL]),
        METADATA_FILE_TEMP, METADATA_FILE)

    # Waterfall buffer
    from collections import deque
    waterfall_buffer = deque(maxlen=DEFAULT_WF_LINES)

    # Playhead: index into iq_data (in samples)
    playhead    = 0
    last_update = time.time()
    last_seek_check = 0.0

    # Clean up stale control file
    try:
        os.remove(REPLAY_CONTROL_FILE)
    except OSError:
        pass

    write_replay_status("PLAYING 0 {:.1f} {}".format(total_duration, fname))
    print("Replay running. Ctrl+C to stop.")

    try:
        while True:
            current_time = time.time()

            # ----------------------------------------------------------------
            # Poll seek control file every 0.25 s
            # ----------------------------------------------------------------
            if current_time - last_seek_check >= 0.25:
                last_seek_check = current_time
                try:
                    if os.path.exists(REPLAY_CONTROL_FILE):
                        with open(REPLAY_CONTROL_FILE, 'r') as fh:
                            line = fh.read().strip()
                        if line:
                            parts = line.split()
                            if parts[0].upper() == 'SEEK' and len(parts) >= 2:
                                seek_secs  = float(parts[1])
                                seek_samps = int(seek_secs * sample_rate)
                                playhead   = max(0, min(
                                    total_samples - chunk_size,
                                    playhead + seek_samps))
                                current_sec = playhead / sample_rate
                                print("SEEK {:.1f}s -> playhead {:.1f}s".format(
                                    seek_secs, current_sec))
                                # Consume the control file so we don't
                                # re-apply the same seek next poll
                                os.remove(REPLAY_CONTROL_FILE)
                except (OSError, IOError, ValueError):
                    pass

            # ----------------------------------------------------------------
            # End of file: freeze last frame
            # ----------------------------------------------------------------
            if playhead + chunk_size > total_samples:
                write_replay_status("COMPLETE {}".format(fname))
                print("Replay complete — freezing last frame.")
                # Keep the /tmp files as-is; the UI will detect COMPLETE
                # and stop polling for new data.
                while True:
                    time.sleep(1.0)   # Wait for UI to stop us via ProcessManager

            # ----------------------------------------------------------------
            # Process one waterfall row (NUM_AVERAGES chunks)
            # ----------------------------------------------------------------
            psd_accumulator = np.zeros(FFT_SIZE)

            for _ in range(NUM_AVERAGES):
                chunk = iq_data[playhead: playhead + FFT_SIZE]
                if len(chunk) < FFT_SIZE:
                    chunk = np.pad(chunk, (0, FFT_SIZE - len(chunk)))
                playhead += FFT_SIZE

                window      = np.hanning(FFT_SIZE)
                fft_shifted = np.fft.fftshift(np.fft.fft(chunk * window))
                psd_accumulator += np.abs(fft_shifted) ** 2

            psd = 10.0 * np.log10(psd_accumulator / NUM_AVERAGES + 1e-10)
            psd = remove_dc_spike(psd, center_idx)

            waterfall_buffer.append(psd)

            # ----------------------------------------------------------------
            # Write /tmp files at UPDATE_INTERVAL (throttle to real-time)
            # ----------------------------------------------------------------
            if current_time - last_update >= UPDATE_INTERVAL:
                save_data_atomic(psd, PSD_FILE_TEMP, PSD_FILE)
                save_data_atomic(np.flipud(np.array(waterfall_buffer)),
                                 WATERFALL_FILE_TEMP, WATERFALL_FILE)

                current_sec = playhead / sample_rate
                write_replay_status("PLAYING {:.1f} {:.1f} {}".format(
                    current_sec, total_duration, fname))

                last_update = current_time

                # Pace playback to real-time: sleep until next frame is due
                sleep_time = UPDATE_INTERVAL - (time.time() - current_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                # We're ahead of real-time; sleep for the remaining interval
                sleep_time = UPDATE_INTERVAL - (time.time() - last_update)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nReplay stopped.")

    finally:
        write_replay_status("IDLE")
        try:
            os.remove(REPLAY_CONTROL_FILE)
        except OSError:
            pass
        print("Done.")


if __name__ == "__main__":
    main()
