#!/usr/bin/env python3
"""
tv_channels.py - TV Channel Utilities for Tricorder EMF Mode

Provides helper functions for TV channel frequency lookups, band identification,
and channel scanning optimization for use with RTL-SDR.

Compatible with North American ATSC digital television standards.
"""

import json


class TVChannelDatabase:
    """Database of TV channel frequencies and band information."""
    
    def __init__(self):
        """Initialize TV channel database with ATSC frequencies."""
        
        # VHF Low Band (Channels 2-6)
        # Note: Channel 1 was removed from TV allocation
        self.vhf_low = {
            2: {'center': 57e6,  'lower': 54e6,  'upper': 60e6},
            3: {'center': 63e6,  'lower': 60e6,  'upper': 66e6},
            4: {'center': 69e6,  'lower': 66e6,  'upper': 72e6},
            5: {'center': 79e6,  'lower': 76e6,  'upper': 82e6},
            6: {'center': 85e6,  'lower': 82e6,  'upper': 88e6},
        }
        
        # VHF High Band (Channels 7-13)
        self.vhf_high = {
            7:  {'center': 177e6, 'lower': 174e6, 'upper': 180e6},
            8:  {'center': 183e6, 'lower': 180e6, 'upper': 186e6},
            9:  {'center': 189e6, 'lower': 186e6, 'upper': 192e6},
            10: {'center': 195e6, 'lower': 192e6, 'upper': 198e6},
            11: {'center': 201e6, 'lower': 198e6, 'upper': 204e6},
            12: {'center': 207e6, 'lower': 204e6, 'upper': 210e6},
            13: {'center': 213e6, 'lower': 210e6, 'upper': 216e6},
        }
        
        # UHF Band (Channels 14-69)
        # Channel 37 reserved for radio astronomy
        # Channels 52-69 repurposed for other services (LTE, etc.)
        # Typical TV allocation: 14-51
        self.uhf = {}
        for ch in range(14, 70):
            center_freq = 470e6 + (ch - 14) * 6e6 + 3e6
            self.uhf[ch] = {
                'center': center_freq,
                'lower': center_freq - 3e6,
                'upper': center_freq + 3e6
            }
        
        # Combine all channels
        self.all_channels = {}
        self.all_channels.update(self.vhf_low)
        self.all_channels.update(self.vhf_high)
        self.all_channels.update(self.uhf)
        
        # Band definitions
        self.bands = {
            'vhf_low': {
                'name': 'VHF Low',
                'channels': list(range(2, 7)),
                'freq_min': 54e6,
                'freq_max': 88e6,
                'description': 'Channels 2-6'
            },
            'vhf_high': {
                'name': 'VHF High',
                'channels': list(range(7, 14)),
                'freq_min': 174e6,
                'freq_max': 216e6,
                'description': 'Channels 7-13'
            },
            'uhf_low': {
                'name': 'UHF Low',
                'channels': list(range(14, 37)),
                'freq_min': 470e6,
                'freq_max': 608e6,
                'description': 'Channels 14-36'
            },
            'uhf_mid': {
                'name': 'UHF Mid',
                'channels': list(range(37, 52)),
                'freq_min': 608e6,
                'freq_max': 698e6,
                'description': 'Channels 37-51'
            }
        }
    
    def get_channel_info(self, channel_number):
        """Get frequency information for a specific channel.
        
        Args:
            channel_number (int): TV channel number (2-69)
            
        Returns:
            dict: Channel info with 'center', 'lower', 'upper' frequencies in Hz
            None if channel doesn't exist
        """
        return self.all_channels.get(channel_number)
    
    def get_band_for_channel(self, channel_number):
        """Determine which band a channel belongs to.
        
        Args:
            channel_number (int): TV channel number
            
        Returns:
            str: Band key ('vhf_low', 'vhf_high', 'uhf_low', 'uhf_mid')
            None if channel doesn't exist
        """
        if channel_number in range(2, 7):
            return 'vhf_low'
        elif channel_number in range(7, 14):
            return 'vhf_high'
        elif channel_number in range(14, 37):
            return 'uhf_low'
        elif channel_number in range(37, 70):
            return 'uhf_mid'
        return None
    
    def frequency_to_channel(self, frequency_hz):
        """Find the TV channel closest to a given frequency.
        
        Args:
            frequency_hz (float): Frequency in Hz
            
        Returns:
            int: Closest channel number, or None if outside TV bands
        """
        # Check if frequency is within any TV band
        in_tv_band = False
        for band_info in self.bands.values():
            if band_info['freq_min'] <= frequency_hz <= band_info['freq_max']:
                in_tv_band = True
                break
        
        if not in_tv_band:
            return None
        
        # Find closest channel
        min_distance = float('inf')
        closest_channel = None
        
        for ch, info in self.all_channels.items():
            distance = abs(info['center'] - frequency_hz)
            if distance < min_distance:
                min_distance = distance
                closest_channel = ch
        
        # Only return if within 3 MHz (half channel width)
        if min_distance <= 3e6:
            return closest_channel
        
        return None
    
    def get_channels_in_range(self, freq_start_hz, freq_end_hz):
        """Get all TV channels within a frequency range.
        
        Args:
            freq_start_hz (float): Start frequency in Hz
            freq_end_hz (float): End frequency in Hz
            
        Returns:
            list: List of channel numbers in range
        """
        channels = []
        for ch, info in sorted(self.all_channels.items()):
            if info['lower'] >= freq_start_hz and info['upper'] <= freq_end_hz:
                channels.append(ch)
            elif info['center'] >= freq_start_hz and info['center'] <= freq_end_hz:
                channels.append(ch)
        
        return sorted(channels)
    
    def get_scan_frequencies(self, channels):
        """Get optimal scan frequencies for a list of channels.
        
        Since RTL-SDR can capture ~2.4 MHz at once and TV channels are 6 MHz,
        this returns center frequencies that should be scanned to cover all
        channels efficiently.
        
        Args:
            channels (list): List of channel numbers to scan
            
        Returns:
            list: List of (frequency_hz, channels_covered) tuples
        """
        if not channels:
            return []
        
        scan_points = []
        for ch in sorted(channels):
            info = self.get_channel_info(ch)
            if info:
                # For 6 MHz channels, need to scan lower, center, and upper
                # to cover with 2.4 MHz RTL-SDR bandwidth
                scan_points.append((info['lower'] + 1.2e6, [ch]))
                scan_points.append((info['center'], [ch]))
                scan_points.append((info['upper'] - 1.2e6, [ch]))
        
        return scan_points
    
    def format_frequency(self, freq_hz):
        """Format frequency for human-readable display.
        
        Args:
            freq_hz (float): Frequency in Hz
            
        Returns:
            str: Formatted frequency string
        """
        if freq_hz >= 1e9:
            return "{:.2f} GHz".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            return "{:.1f} MHz".format(freq_hz / 1e6)
        elif freq_hz >= 1e3:
            return "{:.1f} kHz".format(freq_hz / 1e3)
        else:
            return "{:.0f} Hz".format(freq_hz)
    
    def print_channel_table(self):
        """Print a formatted table of all TV channels."""
        print("\n" + "="*70)
        print("TV CHANNEL FREQUENCY TABLE (ATSC Digital)")
        print("="*70)
        
        # VHF Low
        print("\nVHF LOW BAND (Channels 2-6)")
        print("-" * 70)
        for ch in sorted(self.vhf_low.keys()):
            info = self.vhf_low[ch]
            print("Channel {:2d}:  {:>8s} center  [{:>8s} - {:>8s}]".format(
                ch,
                self.format_frequency(info['center']),
                self.format_frequency(info['lower']),
                self.format_frequency(info['upper'])
            ))
        
        # VHF High
        print("\nVHF HIGH BAND (Channels 7-13)")
        print("-" * 70)
        for ch in sorted(self.vhf_high.keys()):
            info = self.vhf_high[ch]
            print("Channel {:2d}:  {:>8s} center  [{:>8s} - {:>8s}]".format(
                ch,
                self.format_frequency(info['center']),
                self.format_frequency(info['lower']),
                self.format_frequency(info['upper'])
            ))
        
        # UHF (sample - first 10 and last 10)
        print("\nUHF BAND (Channels 14-69, showing first and last 10)")
        print("-" * 70)
        uhf_channels = sorted(self.uhf.keys())
        
        # First 10
        for ch in uhf_channels[:10]:
            info = self.uhf[ch]
            print("Channel {:2d}:  {:>8s} center  [{:>8s} - {:>8s}]".format(
                ch,
                self.format_frequency(info['center']),
                self.format_frequency(info['lower']),
                self.format_frequency(info['upper'])
            ))
        
        print("    ...")
        
        # Last 10
        for ch in uhf_channels[-10:]:
            info = self.uhf[ch]
            print("Channel {:2d}:  {:>8s} center  [{:>8s} - {:>8s}]".format(
                ch,
                self.format_frequency(info['center']),
                self.format_frequency(info['lower']),
                self.format_frequency(info['upper'])
            ))
        
        print("="*70 + "\n")
    
    def save_to_json(self, filename):
        """Save channel database to JSON file.
        
        Args:
            filename (str): Output JSON filename
        """
        data = {
            'vhf_low': self.vhf_low,
            'vhf_high': self.vhf_high,
            'uhf': self.uhf,
            'bands': self.bands
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("TV channel database saved to {}".format(filename))


def get_common_channels():
    """Get list of most commonly used TV channels in North America.
    
    Returns:
        dict: Common channels organized by band
    """
    return {
        'vhf_low': [2, 4, 5, 6],      # Less common due to interference
        'vhf_high': [7, 9, 11, 13],   # Very common in cities
        'uhf': [14, 20, 25, 30, 36, 38, 44, 50]  # Most common modern allocation
    }


def main():
    """Demo/test function."""
    db = TVChannelDatabase()
    
    # Print channel table
    db.print_channel_table()
    
    # Test frequency lookup
    print("\nTEST: Frequency to Channel Conversion")
    print("-" * 40)
    test_freqs = [57e6, 177e6, 189e6, 539e6, 100e6]
    for freq in test_freqs:
        ch = db.frequency_to_channel(freq)
        if ch:
            print("{:>10s} -> Channel {}".format(
                db.format_frequency(freq), ch))
        else:
            print("{:>10s} -> Not a TV channel".format(
                db.format_frequency(freq)))
    
    # Test channel lookup
    print("\nTEST: Channel to Frequency Conversion")
    print("-" * 40)
    test_channels = [2, 7, 20, 44]
    for ch in test_channels:
        info = db.get_channel_info(ch)
        if info:
            print("Channel {:2d}: {} [{} - {}]".format(
                ch,
                db.format_frequency(info['center']),
                db.format_frequency(info['lower']),
                db.format_frequency(info['upper'])
            ))
    
    # Test range scan
    print("\nTEST: Channels in Range")
    print("-" * 40)
    channels = db.get_channels_in_range(470e6, 550e6)
    print("Channels between 470-550 MHz: {}".format(channels))
    
    # Save to JSON
    db.save_to_json('/tmp/tv_channels.json')
    print("\nJSON database saved to /tmp/tv_channels.json")


if __name__ == '__main__':
    main()
