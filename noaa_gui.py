#!/usr/bin/env python3
"""
Simple GUI for NOAA APT Receiver Testing

A basic interface for testing satellite recording and decoding
without needing to wait for actual satellite passes.

Features:
- Record button (test recording for configurable duration)
- Image display for decoded APT images
- Status messages

Usage:
    python3 noaa_apt_gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import subprocess
import threading
from pathlib import Path
import time

# Import the decoder
import sys
import wave
import numpy as np
from scipy import signal
from PIL import Image as PILImage


class PythonAPTDecoder:
    """Pure Python APT decoder (copied from main script)"""
    
    def __init__(self, wav_file, progress_callback=None):
        self.wav_file = Path(wav_file)
        self.samples = None
        self.sample_rate = None
        self.progress_callback = progress_callback  # Callback for line-by-line updates


class LiveAPTDecoder:
    """
    Real-time APT decoder for live audio streams
    
    Processes audio line-by-line for waterfall-style display.
    """
    
    def __init__(self, sample_rate=11025):
        """Initialize live decoder"""
        self.sample_rate = sample_rate
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # APT parameters - each line is 0.5 seconds
        self.samples_per_line = int(sample_rate * 0.5)  # ~5512 samples per line at 11025 Hz
        
        # Filter state
        nyquist = sample_rate / 2
        cutoff = 2400 / nyquist
        self.filter_b, self.filter_a = signal.butter(5, cutoff, btype='low')
        self.filter_zi = signal.lfilter_zi(self.filter_b, self.filter_a)
        
    def add_audio_chunk(self, audio_chunk):
        """
        Add new audio chunk and decode complete lines
        
        Args:
            audio_chunk: numpy array of float32 audio samples
            
        Returns:
            List of decoded image lines (each line is 2080 pixels)
        """
        # Add to buffer
        self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk])
        
        # Decode all complete lines available
        lines = []
        
        while len(self.audio_buffer) >= self.samples_per_line:
            # Extract one line worth of samples
            line_samples = self.audio_buffer[:self.samples_per_line]
            self.audio_buffer = self.audio_buffer[self.samples_per_line:]
            
            # Decode this line
            decoded_line = self._decode_line(line_samples)
            if decoded_line is not None:
                lines.append(decoded_line)
        
        return lines
    
    def _decode_line(self, samples):
        """Decode one line of audio (0.5 seconds) into 2080 pixels"""
        try:
            # 1. AM demodulation - Hilbert transform for envelope detection
            analytic = signal.hilbert(samples)
            envelope = np.abs(analytic)
            
            # 2. Low-pass filter with state preservation
            filtered, self.filter_zi = signal.lfilter(
                self.filter_b, self.filter_a, envelope, zi=self.filter_zi
            )
            
            # 3. Resample from ~5512 samples to 2080 samples (one APT line)
            resampled = signal.resample(filtered, 2080)
            
            # 4. Normalize to 0-255 range
            # Remove DC offset
            resampled = resampled - np.mean(resampled)
            
            # Scale to 0-255
            img_max = np.max(np.abs(resampled))
            if img_max > 0:
                normalized = ((resampled / img_max) * 127.5 + 127.5).astype(np.uint8)
            else:
                normalized = np.zeros(2080, dtype=np.uint8)
            
            return normalized
            
        except Exception as e:
            print(f"Error decoding line: {e}")
            return None


class PythonAPTDecoder:
    """Pure Python APT decoder (copied from main script)"""
    
    def __init__(self, wav_file, progress_callback=None):
        self.wav_file = Path(wav_file)
        self.samples = None
        self.sample_rate = None
        self.progress_callback = progress_callback  # Callback for line-by-line updates
        
    def load_wav(self):
        """Load WAV file and extract samples"""
        print(f"Loading WAV file: {self.wav_file}")
        
        with wave.open(str(self.wav_file), 'rb') as wav:
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            self.sample_rate = wav.getframerate()
            n_frames = wav.getnframes()
            
            print(f"  Sample rate: {self.sample_rate} Hz, Duration: {n_frames / self.sample_rate:.1f}s")
            
            audio_data = wav.readframes(n_frames)
            
            if sample_width == 1:
                dtype = np.uint8
            elif sample_width == 2:
                dtype = np.int16
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")
            
            samples = np.frombuffer(audio_data, dtype=dtype)
            
            if dtype == np.int16:
                samples = samples.astype(np.float32) / 32768.0
            else:
                samples = samples.astype(np.float32) / 128.0 - 1.0
            
            self.samples = samples
            return True
    
    def hilbert_envelope(self, sig):
        """Compute envelope using Hilbert transform"""
        analytic = signal.hilbert(sig)
        envelope = np.abs(analytic)
        return envelope
    
    def resample(self, sig, target_rate):
        """Resample signal to target rate"""
        ratio = target_rate / self.sample_rate
        num_samples = int(len(sig) * ratio)
        resampled = signal.resample(sig, num_samples)
        return resampled
    
    def decode_apt_simple(self):
        """Simple APT decoder with line-by-line processing"""
        if self.samples is None:
            self.load_wav()
        
        print("Decoding APT...")
        
        # AM demodulation
        print("  Demodulating...")
        envelope = self.hilbert_envelope(self.samples)
        
        # Low-pass filter
        print("  Filtering...")
        nyquist = self.sample_rate / 2
        cutoff = 2400 / nyquist
        b, a = signal.butter(5, cutoff, btype='low')
        filtered = signal.filtfilt(b, a, envelope)
        
        # Resample to APT rate
        print("  Resampling...")
        target_rate = 4160
        resampled = self.resample(filtered, target_rate)
        
        # Normalize
        print("  Normalizing...")
        resampled = resampled - np.mean(resampled)
        img_max = np.max(np.abs(resampled))
        if img_max > 0:
            normalized = ((resampled / img_max) * 127.5 + 127.5).astype(np.uint8)
        else:
            normalized = np.zeros_like(resampled, dtype=np.uint8)
        
        # Reshape line by line with progress updates
        print("  Reshaping into image...")
        samples_per_line = 2080
        num_lines = len(normalized) // samples_per_line
        
        # Trim to exact multiple of line length
        trimmed = normalized[:num_lines * samples_per_line]
        
        # Create empty image arrays
        channel_a_lines = []
        channel_b_lines = []
        
        # Process line by line
        for line_num in range(num_lines):
            start_idx = line_num * samples_per_line
            end_idx = start_idx + samples_per_line
            line_data = trimmed[start_idx:end_idx]
            
            # Split into channels
            ch_a = line_data[:1040]
            ch_b = line_data[1040:]
            
            channel_a_lines.append(ch_a)
            channel_b_lines.append(ch_b)
            
            # Progress callback every 10 lines
            if self.progress_callback and line_num % 10 == 0:
                partial_a = np.array(channel_a_lines)
                partial_b = np.array(channel_b_lines)
                self.progress_callback(partial_a, partial_b, line_num, num_lines)
        
        # Convert to arrays
        channel_a = np.array(channel_a_lines)
        channel_b = np.array(channel_b_lines)
        image_data = trimmed.reshape((num_lines, samples_per_line))
        
        print(f"  Generated image: {samples_per_line}x{num_lines} pixels")
        
        return {
            'full': image_data,
            'channel_a': channel_a,
            'channel_b': channel_b
        }


class NOAAReceiverGUI:
    """Simple GUI for NOAA APT testing"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("NOAA APT Receiver - Test GUI")
        self.root.geometry("1200x700")  # Wider window
        
        # Output directory
        self.output_dir = Path("/tmp/noaa_captures")
        self.output_dir.mkdir(exist_ok=True)
        
        # Satellite frequencies (Hz)
        self.frequencies = {
            "NOAA-15": 137.620e6,
            "NOAA-18": 137.9125e6,
            "NOAA-19": 137.100e6
        }
        
        # Recording state
        self.recording = False
        self.record_process = None
        
        # Live view state
        self.live_view_active = False
        self.live_decoder = None
        self.decoded_lines = []
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        """Create UI elements"""
        
        # Control panel at top
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        # Satellite selection
        ttk.Label(control_frame, text="Satellite:").pack(side=tk.LEFT, padx=5)
        self.satellite_var = tk.StringVar(value="NOAA-19")
        satellite_combo = ttk.Combobox(
            control_frame, 
            textvariable=self.satellite_var,
            values=["NOAA-15", "NOAA-18", "NOAA-19"],
            state="readonly",
            width=10
        )
        satellite_combo.pack(side=tk.LEFT, padx=5)
        
        # Frequency display
        self.freq_label = ttk.Label(control_frame, text="137.100 MHz", foreground="blue")
        self.freq_label.pack(side=tk.LEFT, padx=10)
        
        # Update frequency when satellite changes
        def update_freq(*args):
            freqs = {
                "NOAA-15": "137.620 MHz",
                "NOAA-18": "137.9125 MHz",
                "NOAA-19": "137.100 MHz"
            }
            self.freq_label.config(text=freqs.get(self.satellite_var.get(), ""))
        
        self.satellite_var.trace('w', update_freq)
        
        # Duration
        ttk.Label(control_frame, text="Duration (sec):").pack(side=tk.LEFT, padx=5)
        self.duration_var = tk.StringVar(value="30")
        duration_entry = ttk.Entry(control_frame, textvariable=self.duration_var, width=8)
        duration_entry.pack(side=tk.LEFT, padx=5)
        
        # Record button
        self.record_btn = ttk.Button(
            control_frame, 
            text="RECORD",
            command=self.toggle_recording,
            width=15
        )
        self.record_btn.pack(side=tk.LEFT, padx=10)
        
        # Live View button
        self.live_view_btn = ttk.Button(
            control_frame,
            text="LIVE VIEW",
            command=self.toggle_live_view,
            width=15
        )
        self.live_view_btn.pack(side=tk.LEFT, padx=5)
        
        # Decode button
        decode_btn = ttk.Button(
            control_frame,
            text="Load & Decode WAV",
            command=self.load_and_decode,
            width=18
        )
        decode_btn.pack(side=tk.LEFT, padx=5)
        
        # Status panel
        status_frame = ttk.Frame(self.root, padding="10")
        status_frame.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(
            status_frame, 
            text="Ready", 
            foreground="green",
            font=("Arial", 10, "bold")
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            status_frame,
            mode='indeterminate',
            length=200
        )
        self.progress.pack(side=tk.LEFT, padx=10)
        
        # Image display area
        image_frame = ttk.LabelFrame(self.root, text="Decoded Image", padding="10")
        image_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas for image
        self.canvas = tk.Canvas(image_frame, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Log area at bottom
        log_frame = ttk.LabelFrame(self.root, text="Log", padding="5")
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False, padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
    def log(self, message):
        """Add message to log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        print(message)  # Also print to console
        
    def set_status(self, message, color="green"):
        """Update status label"""
        self.status_label.config(text=message, foreground=color)
        
    def toggle_recording(self):
        """Start or stop recording"""
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()
            
    def start_recording(self):
        """Start recording satellite signal"""
        self.recording = True
        self.record_btn.config(text="STOP")
        self.set_status("Recording...", "red")
        self.progress.start()
        
        # Get parameters
        satellite = self.satellite_var.get()
        try:
            duration = int(self.duration_var.get())
        except ValueError:
            duration = 30
        
        # Frequency mapping
        freqs = {
            "NOAA-15": 137.620e6,
            "NOAA-18": 137.9125e6,
            "NOAA-19": 137.100e6
        }
        frequency = freqs[satellite]
        
        self.log(f"Starting recording: {satellite} at {frequency/1e6:.4f} MHz for {duration}s")
        
        # Start recording in background thread
        thread = threading.Thread(target=self._record_thread, args=(satellite, frequency, duration))
        thread.daemon = True
        thread.start()
        
    def toggle_recording(self):
        """Start/stop recording"""
        if not self.recording:
            # Start recording
            satellite = self.satellite_var.get()
            frequency = self.frequencies[satellite]
            
            try:
                duration = int(self.duration_var.get())
            except ValueError:
                self.log("Invalid duration")
                return
            
            self.log(f"Starting recording: {satellite} at {frequency/1e6:.4f} MHz for {duration}s")
            self.set_status("Recording...", "red")
            self.recording = True
            self.record_btn.config(text="STOP")
            
            # Start recording thread
            thread = threading.Thread(
                target=self._record_thread,
                args=(satellite, frequency, duration),
                daemon=True
            )
            thread.start()
        else:
            # Stop recording
            self.log("Stopping recording...")
            self.recording = False
            self.record_btn.config(text="RECORD")
    
    def toggle_live_view(self):
        """Start/stop live view mode"""
        if not self.live_view_active:
            # Start live view
            satellite = self.satellite_var.get()
            frequency = self.frequencies[satellite]
            
            self.log(f"Starting LIVE VIEW: {satellite} at {frequency/1e6:.4f} MHz")
            self.set_status("Live View Active", "orange")
            self.live_view_active = True
            self.live_view_btn.config(text="STOP LIVE VIEW")
            self.decoded_lines = []
            
            # Clear canvas
            self.canvas.delete("all")
            
            # Start live view thread
            thread = threading.Thread(
                target=self._live_view_thread,
                args=(satellite, frequency),
                daemon=True
            )
            thread.start()
        else:
            # Stop live view
            self.log("Stopping live view...")
            self.live_view_active = False
            self.live_view_btn.config(text="LIVE VIEW")
            self.set_status("Ready", "green")
    
    def _record_thread(self, satellite, frequency, duration):
        """Recording thread - simple WAV capture only"""
        try:
            # Generate filename
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            wav_file = self.output_dir / f"{satellite}_{timestamp}.wav"
            
            # rtl_fm command
            rtl_fm_cmd = [
                'rtl_fm',
                '-f', str(int(frequency)),
                '-s', '60k',
                '-g', '40',
                '-p', '0',
                '-E', 'dc',
                '-F', '9',
                '-A', 'fast',
                '-'
            ]
            
            # sox command
            sox_cmd = [
                'sox',
                '-t', 'raw', '-r', '60k', '-e', 's', '-b', '16', '-c', '1', '-V1', '-',
                '-t', 'wav', str(wav_file),
                'rate', '11025'
            ]
            
            # Start processes
            rtl_fm_proc = subprocess.Popen(rtl_fm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sox_proc = subprocess.Popen(sox_cmd, stdin=rtl_fm_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.record_process = (rtl_fm_proc, sox_proc)
            
            # Wait for duration
            start = time.time()
            while time.time() - start < duration and self.recording:
                time.sleep(0.5)
            
            # Stop recording
            rtl_fm_proc.terminate()
            sox_proc.terminate()
            rtl_fm_proc.wait(timeout=5)
            sox_proc.wait(timeout=5)
            
            if wav_file.exists():
                size_mb = wav_file.stat().st_size / 1024 / 1024
                self.log(f"Recording saved: {wav_file.name} ({size_mb:.1f} MB)")
                
                # Auto-decode
                self.root.after(100, lambda: self.decode_wav(wav_file))
            else:
                self.log("Error: Recording file not created")
                
        except Exception as e:
            self.log(f"Recording error: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            self.recording = False
            self.root.after(0, self._recording_complete)
    
    def _live_view_thread(self, satellite, frequency):
        """Live view thread - decode in real-time like waterfall"""
        try:
            self.log("Initializing live decoder...")
            
            # Create live decoder
            self.live_decoder = LiveAPTDecoder(sample_rate=11025)
            
            # rtl_fm command
            rtl_fm_cmd = [
                'rtl_fm',
                '-f', str(int(frequency)),
                '-s', '60k',
                '-g', '40',
                '-p', '0',
                '-E', 'dc',
                '-F', '9',
                '-A', 'fast',
                '-'
            ]
            
            # sox command - resample to 11025 Hz and output to stdout
            sox_cmd = [
                'sox',
                '-t', 'raw', '-r', '60k', '-e', 's', '-b', '16', '-c', '1', '-V1', '-',
                '-t', 'raw', '-r', '11025', '-e', 's', '-b', '16', '-c', '1', '-',
            ]
            
            # Start processes
            rtl_fm_proc = subprocess.Popen(rtl_fm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sox_proc = subprocess.Popen(sox_cmd, stdin=rtl_fm_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.record_process = (rtl_fm_proc, sox_proc)
            
            self.log("Live view started - decoding line by line...")
            
            # Read chunks and decode line by line
            chunk_size = 11025  # 1 second of audio = ~2 lines
            
            while self.live_view_active:
                # Read chunk from sox stdout
                chunk_bytes = sox_proc.stdout.read(chunk_size * 2)  # 2 bytes per int16 sample
                
                if len(chunk_bytes) == 0:
                    break
                
                # Convert bytes to numpy array
                chunk_samples = np.frombuffer(chunk_bytes, dtype=np.int16)
                chunk_float = chunk_samples.astype(np.float32) / 32768.0
                
                # Decode lines from this chunk
                new_lines = self.live_decoder.add_audio_chunk(chunk_float)
                
                # Add new lines and update display
                if new_lines:
                    self.decoded_lines.extend(new_lines)
                    self.root.after(0, self._update_waterfall_display)
            
            # Clean up
            rtl_fm_proc.terminate()
            sox_proc.terminate()
            rtl_fm_proc.wait(timeout=5)
            sox_proc.wait(timeout=5)
            
            self.log(f"Live view stopped. Decoded {len(self.decoded_lines)} lines total")
            
        except Exception as e:
            self.log(f"Live view error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.live_view_active = False
            self.root.after(0, lambda: self.live_view_btn.config(text="LIVE VIEW"))
            self.root.after(0, lambda: self.set_status("Ready", "green"))
    
    def _update_waterfall_display(self):
        """Update display with waterfall effect - newest line at bottom"""
        if not self.decoded_lines:
            return
        
        try:
            # Get canvas dimensions
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width < 10 or canvas_height < 10:
                return
            
            # Determine how many lines to show (keep last N lines that fit)
            max_lines = canvas_height  # One pixel per line for now
            
            if len(self.decoded_lines) > max_lines:
                # Show only the most recent lines (scrolling waterfall effect)
                visible_lines = self.decoded_lines[-max_lines:]
            else:
                visible_lines = self.decoded_lines
            
            # Convert lines to image
            # Each line is 2080 pixels (both channels)
            # Split into channel A (first 1040) for display
            image_data = np.array(visible_lines)
            channel_a = image_data[:, :1040]  # Just channel A (visible light usually)
            
            # Create PIL image
            img = PILImage.fromarray(channel_a, mode='L')
            
            # Resize to fit canvas width (maintain aspect ratio)
            aspect_ratio = img.width / img.height if img.height > 0 else 1
            new_width = canvas_width
            new_height = int(new_width / aspect_ratio)
            
            # If image is taller than canvas, limit to canvas height
            if new_height > canvas_height:
                new_height = canvas_height
                new_width = int(new_height * aspect_ratio)
            
            img = img.resize((new_width, new_height), PILImage.LANCZOS)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(img)
            
            # Clear canvas and display at bottom (waterfall from top, newest at bottom)
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height - new_height // 2,  # Anchor at bottom
                image=self.photo,
                anchor=tk.CENTER
            )
            
            # Update status with line count
            self.set_status(f"Live: {len(self.decoded_lines)} lines", "orange")
            
        except Exception as e:
            print(f"Waterfall display error: {e}")
            import traceback
            traceback.print_exc()
    
    def _old_record_thread(self, satellite, frequency, duration):
        """Recording thread"""
        try:
            # Generate filename
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            wav_file = self.output_dir / f"{satellite}_{timestamp}.wav"
            
            # rtl_fm command
            rtl_fm_cmd = [
                'rtl_fm',
                '-f', str(int(frequency)),
                '-s', '60k',
                '-g', '40',
                '-p', '0',
                '-E', 'dc',
                '-F', '9',
                '-A', 'fast',
                '-'
            ]
            
            # sox command
            sox_cmd = [
                'sox',
                '-t', 'raw', '-r', '60k', '-e', 's', '-b', '16', '-c', '1', '-V1', '-',
                '-t', 'wav', str(wav_file),
                'rate', '11025'
            ]
            
            # Start processes
            rtl_fm_proc = subprocess.Popen(rtl_fm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sox_proc = subprocess.Popen(sox_cmd, stdin=rtl_fm_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.record_process = (rtl_fm_proc, sox_proc)
            
            # Wait for duration
            start = time.time()
            while time.time() - start < duration and self.recording:
                time.sleep(0.5)
            
            # Stop recording
            rtl_fm_proc.terminate()
            sox_proc.terminate()
            rtl_fm_proc.wait(timeout=5)
            sox_proc.wait(timeout=5)
            
            if wav_file.exists():
                size_mb = wav_file.stat().st_size / 1024 / 1024
                self.log(f"Recording saved: {wav_file.name} ({size_mb:.1f} MB)")
                
                # Auto-decode
                self.root.after(100, lambda: self.decode_wav(wav_file))
            else:
                self.log("Error: Recording file not created")
                
        except Exception as e:
            self.log(f"Recording error: {e}")
            
        finally:
            self.recording = False
            self.root.after(0, self._recording_complete)
            
    def _recording_complete(self):
        """Called when recording completes"""
        self.record_btn.config(text="RECORD")
        self.set_status("Ready", "green")
        self.progress.stop()
        
    def stop_recording(self):
        """Stop ongoing recording"""
        self.recording = False
        self.log("Stopping recording...")
        
    def load_and_decode(self):
        """Load WAV file and decode"""
        filename = filedialog.askopenfilename(
            title="Select WAV file",
            initialdir=self.output_dir,
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")]
        )
        
        if filename:
            self.decode_wav(Path(filename))
            
    def decode_wav(self, wav_file):
        """Decode WAV file and display image"""
        self.set_status("Decoding...", "orange")
        self.progress.start()
        self.log(f"Decoding: {wav_file.name}")
        
        # Decode in background thread
        thread = threading.Thread(target=self._decode_thread, args=(wav_file,))
        thread.daemon = True
        thread.start()
        
    def _decode_thread(self, wav_file):
        """Decoding thread"""
        try:
            # Create decoder with progress callback
            def progress_callback(channel_a, channel_b, line_num, total_lines):
                """Called periodically during decoding with partial image"""
                # Update display in main thread
                self.root.after(0, lambda: self._update_partial_image(channel_a, line_num, total_lines))
            
            decoder = PythonAPTDecoder(wav_file, progress_callback=progress_callback)
            
            # Decode
            decoded = decoder.decode_apt_simple()
            
            # Save images
            output_base = wav_file.parent / wav_file.stem
            
            # Save channel A (usually better)
            img_path = output_base.parent / f"{output_base.name}_channel_a.png"
            img = PILImage.fromarray(decoded['channel_a'], mode='L')
            img.save(img_path)
            
            self.log(f"Decoded image saved: {img_path.name}")
            
            # Display final image
            self.root.after(0, lambda: self.display_image(img_path))
            
        except Exception as e:
            self.log(f"Decoding error: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            self.root.after(0, self._decoding_complete)
    
    def _update_partial_image(self, channel_a, line_num, total_lines):
        """Update display with partial decoded image"""
        try:
            # Convert to PIL image
            img = PILImage.fromarray(channel_a, mode='L')
            
            # Calculate progress percentage
            progress = int((line_num / total_lines) * 100)
            self.set_status(f"Decoding... {progress}%", "orange")
            
            # Resize to fit canvas
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                # Calculate scaling
                img_ratio = img.width / img.height
                canvas_ratio = canvas_width / canvas_height
                
                if img_ratio > canvas_ratio:
                    new_width = canvas_width
                    new_height = int(canvas_width / img_ratio)
                else:
                    new_height = canvas_height
                    new_width = int(canvas_height * img_ratio)
                
                img = img.resize((new_width, new_height), PILImage.LANCZOS)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(img)
            
            # Clear canvas and display
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.photo,
                anchor=tk.CENTER
            )
            
        except Exception as e:
            # Silently ignore errors during partial updates
            pass
            
    def _decoding_complete(self):
        """Called when decoding completes"""
        self.set_status("Ready", "green")
        self.progress.stop()
        
    def display_image(self, image_path):
        """Display image on canvas"""
        try:
            # Load image
            img = PILImage.open(image_path)
            
            # Resize to fit canvas
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                # Calculate scaling
                img_ratio = img.width / img.height
                canvas_ratio = canvas_width / canvas_height
                
                if img_ratio > canvas_ratio:
                    # Image wider than canvas
                    new_width = canvas_width
                    new_height = int(canvas_width / img_ratio)
                else:
                    # Image taller than canvas
                    new_height = canvas_height
                    new_width = int(canvas_height * img_ratio)
                
                img = img.resize((new_width, new_height), PILImage.LANCZOS)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(img)
            
            # Clear canvas and display
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.photo,
                anchor=tk.CENTER
            )
            
            self.log(f"Displaying: {image_path.name}")
            
        except Exception as e:
            self.log(f"Display error: {e}")


def main():
    """Main entry point"""
    root = tk.Tk()
    app = NOAAReceiverGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
