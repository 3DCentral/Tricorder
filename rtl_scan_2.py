from rtlsdr import RtlSdr
import numpy as np
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
sampling_freq = sample_rate #(end_freq - start_freq) / sdr.sample_rate * sdr.sample_rate
total_scan_count  = int((end_freq - start_freq) / sample_rate)
print(middle_freq)
print(sampling_freq)
print(total_scan_count)
sdr.center_freq = int(start_freq+sample_rate/2)

#sdr.center_freq = start_freq + sdr.sample_rate/2 #161e6   # Hz
sdr.freq_correction = 60  # PPM
#print(sdr.valid_gains_db)
sdr.gain = 4 #49.6
print(sdr.gain)


# 5% overlap
#sdr.sample_rate = sdr.sample_rate * 1.1

fft_size = 512
num_rows = 500
x = sdr.read_samples(2048) # get rid of initial empty samples
print("Size of the array:", np.prod(x.shape))
x = np.array([])
all_frequencies = []
all_psd_data = []

#z = sdr.read_samples(fft_size*num_rows)

print("Size of the array:", np.prod(x.shape))
num_scans = 0
for f in range(int(start_freq+sample_rate/2),int(end_freq-sample_rate/2),int(sample_rate)):
    start = f - sample_rate/2
    end = f + sample_rate/2
    print("scanning ",f,start,end)
    sdr.center_freq = f
    y = sdr.read_samples(fft_size*num_rows)
    #y = y - np.mean(y)  # Subtract the mean value, try to minimize center frequency bias
    frequencies, psd = signal.welch(y, fs=sample_rate, window='boxcar')
    #frequencies, psd = signal.welch(y, fs=sample_rate, window='hann')

    target_f = f
    print("target ", target_f)
    # Find the center frequency index
    center_frequency_index = np.argmin(np.abs(frequencies - target_f))
    # Define a window around the center frequency
    window_size = 10  # Adjust as needed
    window_indices = np.arange(center_frequency_index - window_size, center_frequency_index + window_size + 1)
    window_indices = np.clip(window_indices, 0, len(psd) - 1)  # Ensure indices are within bounds

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
    progress_frequencies = np.array(progress_frequencies)  # Convert to NumPy array
    progress_psd_data = np.array(progress_psd_data)  # Convert to NumPy array

    # Define outlier threshold in dB
    outlier_threshold_db = -200  # Adjust as needed

    # Create outlier mask
    outlier_mask = 10 * np.log10(progress_psd_data) < outlier_threshold_db

    # Remove outliers
    non_outlier_indices = np.where(~outlier_mask)[0]  # Use np.where to get indices
    filtered_psd = progress_psd_data[non_outlier_indices]
    filtered_frequencies = progress_frequencies[non_outlier_indices]  # Use indices for frequencies as well



    num_scans = num_scans + 1
    plt.clf()
    plt.rcParams['axes.facecolor'] = 'black'
    avg_f = (start_freq + end)/2
    print(avg_f)
    #plt.psd(x, Fs=sdr.sample_rate/1e6, Fc=sdr.center_freq/1e6, color="yellow")
    #plt.psd(x, Fs=sampling_freq*total_scan_count/1e6, Fc=middle_freq/1e6, color="yellow", window=None)
    #plt.psd(x, Fs=sampling_freq*num_scans/1e6, Fc=avg_f/1e6, color="yellow", window=None)
    plt.xlabel("MHz", color="yellow")
    plt.ylabel("dB", color="yellow")
    plt.tick_params(colors='yellow', which='both')
    plt.plot(filtered_frequencies, 10*np.log10(filtered_psd),color="yellow")
    plt.savefig("/home/tricorder/rpi_lcars-master/spectrum_progress_"+str(num_scans)+".png", bbox_inches='tight',dpi=110, facecolor="black")
    plt.savefig("/home/tricorder/rpi_lcars-master/spectrum.png", bbox_inches='tight',dpi=110, facecolor="black")

print(num_scans)
print(total_scan_count)
print("Size of the array:", np.prod(x.shape))
#x = sdr.read_samples(fft_size*num_rows) # get all the samples we need for the spectrogram

sdr.close()

all_frequencies, all_psd_data = zip(*sorted(zip(all_frequencies, all_psd_data)))
all_frequencies = np.array(all_frequencies)
all_psd_data = np.array(all_psd_data)
#smoothed_psd = ndimage.uniform_filter1d(merged_psd, size=5)

# Define outlier threshold in dB
outlier_threshold_db = -200  # Adjust as needed

# Create outlier mask
outlier_mask = 10 * np.log10(all_psd_data) < outlier_threshold_db

# Remove outliers
non_outlier_indices = np.where(~outlier_mask)[0]  # Use np.where to get indices
filtered_psd = all_psd_data[non_outlier_indices]
filtered_frequencies = all_frequencies[non_outlier_indices]  # Use indices for frequencies as well


plt.figure()


#plt.clf()
plt.rcParams['axes.facecolor'] = 'black'
#plt.psd(x, Fs=sdr.sample_rate/1e6, Fc=sdr.center_freq/1e6, color="yellow")
#plt.psd(x, Fs=sampling_freq*total_scan_count/1e6, Fc=middle_freq/1e6, color="yellow", window=None)
plt.xlabel("MHz", color="yellow")
plt.ylabel("dB", color="yellow")
plt.tick_params(colors='yellow', which='both')

plt.plot(filtered_frequencies, 10*np.log10(filtered_psd),color="yellow")
plt.savefig("/home/tricorder/rpi_lcars-master/spectrum.png", bbox_inches='tight',dpi=110, facecolor="black")




#plt.rcParams['axes.facecolor'] = 'black'
#plt.psd(x, Fs=sdr.sample_rate/1e6, Fc=sdr.center_freq/1e6, color="yellow")
#plt.psd(z, Fs=sdr.sample_rate*6/1e6, Fc=sdr.center_freq/1e6 - 3*sdr.sample_rate/1e6, color="yellow", window=None)
##plt.xlabel("MHz", color="yellow")
#plt.ylabel("dB", color="yellow", labelpad=5)  # Keep or adjust as needed
#plt.tick_params(colors='yellow', which='both')
##plt.tick_params(axis='y', colors='yellow', direction='in', pad=-15)  # Adjust y-axis tick parameters
#plt.tick_params(axis='x', colors='yellow', pad=0)  # Adjust y-axis tick parameters
#plt.tight_layout() #This line was added
#plt.gca().yaxis.set_label_coords(0.05, 0.5) # Adjust y-axis label position
#plt.savefig("/home/tricorder/rpi_lcars-master/spectrum.png", bbox_inches='tight',dpi=108, facecolor="black", pad_inches=0)

#spectrogram = np.zeros((num_rows, fft_size))
#for i in range(num_rows):
#    spectrogram[i,:] = 10*np.log10(np.abs(np.fft.fftshift(np.fft.fft(x[i*fft_size:(i+1)*fft_size])))**2)

# extent is for the x and y label ranges
#extent = [(sdr.center_freq + sdr.sample_rate/-2)/1e6,
#            (sdr.center_freq + sdr.sample_rate/2)/1e6,
#            len(x)/sdr.sample_rate, 0]
#plt.imshow(spectrogram, aspect='auto', extent=extent)
#plt.xlabel("Frequency [MHz]")
#plt.ylabel("Time [s]")

#plt.savefig("/home/tricorder/rpi_lcars-master/spectrum.png", bbox_inches='tight')
#cairosvg.svg2png(url="../pi/spectrum.svg", write_to="../pi/spectrum.png", scale=3.0)

#plt.show()
