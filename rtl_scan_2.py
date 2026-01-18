from rtlsdr import RtlSdr
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import sys
from scipy import signal

sdr = RtlSdr()
print("scanning SDR")

sdr.sample_rate = 3e6
sample_rate = 3e6

start_freq = int(float(sys.argv[1]))
end_freq = int(float(sys.argv[2]))
print(start_freq)
print(end_freq)
middle_freq = (end_freq + start_freq) / 2
sampling_freq = sample_rate
total_scan_count  = int((end_freq - start_freq) / sample_rate)
print(middle_freq)
print(sampling_freq)
print(total_scan_count)
sdr.center_freq = int(start_freq+sample_rate/2)

sdr.freq_correction = 60  # PPM
sdr.gain = 4
print(sdr.gain)

fft_size = 512
num_rows = 500
x = sdr.read_samples(2048) # get rid of initial empty samples
print("Size of the array:", np.prod(x.shape))
x = np.array([])
all_frequencies = []
all_psd_data = []

print("Size of the array:", np.prod(x.shape))
num_scans = 0

for f in range(int(start_freq+sample_rate/2),int(end_freq-sample_rate/2)+int(sample_rate),int(sample_rate)):
    start = f - sample_rate/2
    end = f + sample_rate/2
    print("scanning ",f,start,end)
    sdr.center_freq = f
    y = sdr.read_samples(fft_size*num_rows)
    frequencies, psd = signal.welch(y, fs=sample_rate, window='boxcar')

    target_f = f
    print("target ", target_f)
    # Find the center frequency index
    center_frequency_index = np.argmin(np.abs(frequencies - target_f))
    # Define a window around the center frequency
    window_size = 10  # Adjust as needed
    window_indices = np.arange(center_frequency_index - window_size, center_frequency_index + window_size + 1)
    window_indices = np.clip(window_indices, 0, len(psd) - 1)

    # Calculate the average PSD within the window
    average_psd = np.mean(psd[window_indices])

    # Set the center frequency PSD to the average value
    psd[center_frequency_index - window_size:center_frequency_index + window_size + 1] = average_psd

    # Adjust frequencies to account for center frequency shift
    frequencies = frequencies + sdr.center_freq - sample_rate / 2

    all_frequencies.extend(frequencies)
    all_psd_data.extend(psd)

    progress_frequencies, progress_psd_data = zip(*sorted(zip(all_frequencies, all_psd_data)))

    # Convert to NumPy arrays
    progress_frequencies = np.array(progress_frequencies)
    progress_psd_data = np.array(progress_psd_data)

    # Define outlier threshold in dB
    outlier_threshold_db = -200

    # Create outlier mask
    outlier_mask = 10 * np.log10(progress_psd_data) < outlier_threshold_db

    # Remove outliers
    non_outlier_indices = np.where(~outlier_mask)[0]
    filtered_psd = progress_psd_data[non_outlier_indices]
    filtered_frequencies = progress_frequencies[non_outlier_indices]

    num_scans = num_scans + 1
    
    # Create figure with proper layout for labels
    fig = plt.figure(figsize=(6.4, 3.36), dpi=100)  # 640x336 pixels
    
    # Create axes that leaves room for x-axis labels at bottom
    # [left, bottom, width, height] in figure coordinates
    ax = plt.axes([0, 0.08, 1, 0.92])  # Leave 8% at bottom for labels
    
    # Remove top, right, and left spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    # Remove y-axis completely (no labels, no ticks)
    ax.set_yticks([])
    ax.set_ylabel('')
    
    # Set background to black
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    
    # Plot the spectrum data
    ax.plot(filtered_frequencies, 10*np.log10(filtered_psd), color="yellow", linewidth=2)
    
    # Set x-limits to exact frequency range (no padding)
    ax.set_xlim(start_freq, end_freq)
    
    # Set x-axis labels in MHz
    ax.tick_params(axis='x', colors='yellow', labelsize=9)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: '{:.1f}'.format(x/1e6)))
    
    # Set background color for tick labels
    for label in ax.get_xticklabels():
        label.set_color('yellow')
    
    # Save progress image
    plt.savefig("/tmp/spectrum_progress_"+str(num_scans)+".png", 
                dpi=100, facecolor="black", bbox_inches='tight', pad_inches=0)
    plt.savefig("/tmp/spectrum.png", 
                dpi=100, facecolor="black", bbox_inches='tight', pad_inches=0)
    plt.close()

print(num_scans)
print(total_scan_count)
print("Size of the array:", np.prod(x.shape))

sdr.close()

# Final processing
all_frequencies, all_psd_data = zip(*sorted(zip(all_frequencies, all_psd_data)))
all_frequencies = np.array(all_frequencies)
all_psd_data = np.array(all_psd_data)

# Define outlier threshold in dB
outlier_threshold_db = -200

# Create outlier mask
outlier_mask = 10 * np.log10(all_psd_data) < outlier_threshold_db

# Remove outliers
non_outlier_indices = np.where(~outlier_mask)[0]
filtered_psd = all_psd_data[non_outlier_indices]
filtered_frequencies = all_frequencies[non_outlier_indices]

# Create final figure with frequency labels
fig = plt.figure(figsize=(6.4, 3.36), dpi=100)  # 640x336 pixels

# Create axes that leaves room for x-axis labels at bottom
ax = plt.axes([0, 0.08, 1, 0.92])  # Leave 8% at bottom for labels

# Remove top, right, and left spines
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(False)
ax.spines['bottom'].set_visible(False)

# Remove y-axis completely (no labels, no ticks)
ax.set_yticks([])
ax.set_ylabel('')

# Set background to black
fig.patch.set_facecolor('black')
ax.set_facecolor('black')

# Plot final spectrum
ax.plot(filtered_frequencies, 10*np.log10(filtered_psd), color="yellow", linewidth=2)

# Set x-limits to exact frequency range (no padding)
ax.set_xlim(start_freq, end_freq)

# Set x-axis labels in MHz
ax.tick_params(axis='x', colors='yellow', labelsize=9)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: '{:.1f}'.format(x/1e6)))

# Set background color for tick labels
for label in ax.get_xticklabels():
    label.set_color('yellow')

# Save final image
plt.savefig("/tmp/spectrum.png", 
            dpi=100, facecolor="black", bbox_inches='tight', pad_inches=0)
plt.close()

print("Scan complete!")
