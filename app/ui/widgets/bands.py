"""
bands.py - Central Frequency Band Registry

Single source of truth for all frequency band definitions used across the EMF module.
Covers the RTL-SDR range of ~50 MHz to 2 GHz with full ITU/FCC allocation data.

Consumers:
    - demodulator.py       : demod mode, sample rate, bandwidth, gain, squelch
    - antenna_analysis.py  : name, start, end, color, alpha  (replaces local known_bands)
    - antenna_analysis_enhanced.py : same
    - frequency_selector.py: band label overlay on log-scale ruler
    - waterfall.py         : band name indicator for current center frequency

Band dict schema
----------------
    name         (str)   Short display name, e.g. "FM"
    full_name    (str)   Full display name, e.g. "FM Broadcast Radio"
    start        (float) Band start in MHz
    end          (float) Band end in MHz
    color        (tuple) RGB for visual highlights, (R, G, B) 0-255
    alpha        (int)   Transparency for overlay fills (0-255)
    description  (list)  3-line human-readable description (for demod info panel)
    demod_mode   (str|None)  rtl_fm -M parameter: 'fm', 'wbfm', 'am', or None (data-only)
    sample_rate  (int|None)  rtl_fm sample rate in Hz
    bandwidth    (int|None)  Demodulation bandwidth in Hz
    min_bandwidth(int|None)  Minimum clamped bandwidth to prevent rtl_fm crashes
    gain         (int|None)  SDR gain in dB, or None for auto
    squelch      (int)       rtl_fm squelch level (0 = disabled)

Bands are ordered by start frequency.  Where ranges overlap (e.g. Marine VHF
overlaps Public Safety VHF), the more specific / narrower band should come first
so that get_band_for_freq() returns the most relevant match.
"""

# ---------------------------------------------------------------------------
# Master Band Table
# ---------------------------------------------------------------------------

BANDS = [
    # ------------------------------------------------------------------
    # 6m Ham Radio: 50–54 MHz
    # ------------------------------------------------------------------
    {
        'name':         '6m Ham',
        'full_name':    '6m Ham Radio (VHF)',
        'start':        50.0,
        'end':          54.0,
        'color':        (0, 200, 128),
        'alpha':        40,
        'description':  ['Amateur radio VHF,', 'sporadic-E and', 'meteor scatter'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # TV VHF Low Band: 54–88 MHz  (channels 2–6)
    # ------------------------------------------------------------------
    {
        'name':         'TV VHF-Lo',
        'full_name':    'TV VHF Low Band (Ch 2-6)',
        'start':        54.0,
        'end':          88.0,
        'color':        (100, 150, 255),
        'alpha':        45,
        'description':  ['Over-the-air ATSC', 'digital TV channels', '2 through 6'],
        'demod_mode':   None,   # ATSC data — not easily demodulated by rtl_fm
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # FM Broadcast: 88–108 MHz
    # ------------------------------------------------------------------
    {
        'name':         'FM',
        'full_name':    'FM Broadcast Radio',
        'start':        88.0,
        'end':          108.0,
        'color':        (255, 165, 0),
        'alpha':        40,
        'description':  ['Commercial radio', 'stations with music', 'and talk programming'],
        'demod_mode':   'wbfm',
        'sample_rate':  200000,
        'bandwidth':    200000,
        'min_bandwidth':150000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Aeronautical Navigation (VOR/ILS/NDB): 108–118 MHz
    # ------------------------------------------------------------------
    {
        'name':         'VOR/ILS',
        'full_name':    'Aeronautical Navigation (VOR/ILS)',
        'start':        108.0,
        'end':          118.0,
        'color':        (200, 200, 100),
        'alpha':        35,
        'description':  ['VOR/ILS navigation', 'aids for instrument', 'flight approaches'],
        'demod_mode':   'am',
        'sample_rate':  12000,
        'bandwidth':    10000,
        'min_bandwidth':8000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Aviation Voice: 118–137 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Air',
        'full_name':    'Aviation Band',
        'start':        118.0,
        'end':          137.0,
        'color':        (255, 255, 0),
        'alpha':        40,
        'description':  ['Air traffic control,', 'pilot communications,', 'and ATIS broadcasts'],
        'demod_mode':   'am',
        'sample_rate':  12000,
        'bandwidth':    10000,
        'min_bandwidth':8000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # NOAA Weather Satellites (APT/LRPT downlink): 137–138 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Wx Sat',
        'full_name':    'NOAA Weather Satellites',
        'start':        137.0,
        'end':          138.0,
        'color':        (0, 255, 255),
        'alpha':        50,
        'description':  ['NOAA POES satellite', 'APT/LRPT image', 'downlink (data)'],
        'demod_mode':   None,   # Requires dedicated APT decoder, not rtl_fm
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Military / Government: 138–144 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Gov/Mil',
        'full_name':    'Government / Military VHF',
        'start':        138.0,
        'end':          144.0,
        'color':        (180, 60, 60),
        'alpha':        35,
        'description':  ['US Government and', 'military voice and', 'data operations'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # 2m Ham Radio: 144–148 MHz
    # ------------------------------------------------------------------
    {
        'name':         '2m Ham',
        'full_name':    '2m Ham Radio (VHF)',
        'start':        144.0,
        'end':          148.0,
        'color':        (255, 0, 255),
        'alpha':        40,
        'description':  ['Amateur radio', 'repeaters and', 'simplex operations'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # NOAA Weather Radio (voice): 162–163 MHz
    # Listed before Marine/Public Safety so it gets priority in lookup
    # ------------------------------------------------------------------
    {
        'name':         'NOAA Wx',
        'full_name':    'NOAA Weather Radio',
        'start':        162.0,
        'end':          163.0,
        'color':        (0, 200, 255),
        'alpha':        50,
        'description':  ['Continuous weather', 'broadcasts, warnings,', 'and forecasts'],
        'demod_mode':   'fm',
        'sample_rate':  48000,
        'bandwidth':    40000,
        'min_bandwidth':15000,
        'gain':         40,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Marine VHF: 156–162 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Marine',
        'full_name':    'Marine VHF Radio',
        'start':        156.0,
        'end':          162.0,
        'color':        (0, 180, 220),
        'alpha':        40,
        'description':  ['Ship-to-ship and', 'ship-to-shore', 'communications'],
        'demod_mode':   'fm',
        'sample_rate':  12000,
        'bandwidth':    12500,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Public Safety VHF: 154–158 MHz
    # ------------------------------------------------------------------
    {
        'name':         'PS VHF',
        'full_name':    'Public Safety VHF',
        'start':        154.0,
        'end':          158.0,
        'color':        (255, 80, 80),
        'alpha':        40,
        'description':  ['Police, fire, EMS', 'and emergency', 'services (analog)'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # TV VHF High Band: 174–216 MHz  (channels 7–13)
    # ------------------------------------------------------------------
    {
        'name':         'TV VHF-Hi',
        'full_name':    'TV VHF High Band (Ch 7-13)',
        'start':        174.0,
        'end':          216.0,
        'color':        (150, 100, 255),
        'alpha':        45,
        'description':  ['Over-the-air ATSC', 'digital TV channels', '7 through 13'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # 1.25m Ham Radio: 220–225 MHz
    # ------------------------------------------------------------------
    {
        'name':         '1.25m Ham',
        'full_name':    '1.25m Ham Radio',
        'start':        220.0,
        'end':          225.0,
        'color':        (180, 0, 255),
        'alpha':        40,
        'description':  ['Amateur radio 222', 'MHz band — repeaters', 'and simplex'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Government / Military UHF: 225–400 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Mil UHF',
        'full_name':    'Military / Government UHF',
        'start':        225.0,
        'end':          400.0,
        'color':        (180, 60, 60),
        'alpha':        30,
        'description':  ['US Military UHF', 'voice, data, and', 'satellite uplinks'],
        'demod_mode':   'am',   # Military aviation uses AM in this range
        'sample_rate':  12000,
        'bandwidth':    10000,
        'min_bandwidth':8000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # 70cm Ham Radio: 420–450 MHz
    # ------------------------------------------------------------------
    {
        'name':         '70cm',
        'full_name':    '70cm Ham Radio (UHF)',
        'start':        420.0,
        'end':          450.0,
        'color':        (0, 100, 255),
        'alpha':        40,
        'description':  ['Amateur radio UHF', 'repeaters and', 'satellite operations'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # PMR446 / FRS / GMRS: 446–467 MHz
    # ------------------------------------------------------------------
    {
        'name':         'PMR/FRS',
        'full_name':    'PMR446 / FRS / GMRS',
        'start':        446.0,
        'end':          467.0,
        'color':        (255, 200, 50),
        'alpha':        40,
        'description':  ['Personal mobile radio,', 'family radio service,', 'and walkie-talkies'],
        'demod_mode':   'fm',
        'sample_rate':  12000,
        'bandwidth':    12500,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Public Safety UHF: 453–470 MHz
    # ------------------------------------------------------------------
    {
        'name':         'PS UHF',
        'full_name':    'Public Safety UHF',
        'start':        453.0,
        'end':          470.0,
        'color':        (255, 80, 80),
        'alpha':        40,
        'description':  ['Police, fire, EMS,', 'business band,', 'taxis and security'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    16000,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # TV UHF Primary: 470–608 MHz  (channels 14–36)
    # ------------------------------------------------------------------
    {
        'name':         'TV UHF',
        'full_name':    'TV UHF Band (Ch 14-36)',
        'start':        470.0,
        'end':          608.0,
        'color':        (255, 150, 100),
        'alpha':        45,
        'description':  ['Over-the-air ATSC', 'digital TV channels', '14 through 36'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Radio Astronomy: 608–614 MHz  (ITU protected band)
    # ------------------------------------------------------------------
    {
        'name':         'Radio Astro',
        'full_name':    'Radio Astronomy (Protected)',
        'start':        608.0,
        'end':          614.0,
        'color':        (80, 255, 180),
        'alpha':        50,
        'description':  ['ITU protected band', 'for radio astronomy', 'observations'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # TV UHF High: 614–698 MHz  (channels 37–49)
    # ------------------------------------------------------------------
    {
        'name':         'TV UHF-Hi',
        'full_name':    'TV UHF High Band (Ch 37-49)',
        'start':        614.0,
        'end':          698.0,
        'color':        (255, 200, 100),
        'alpha':        45,
        'description':  ['Over-the-air ATSC', 'digital TV channels', '37 through 49'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # LTE 700 MHz Band: 698–806 MHz
    # ------------------------------------------------------------------
    {
        'name':         'LTE 700',
        'full_name':    'LTE Cellular (700 MHz)',
        'start':        698.0,
        'end':          806.0,
        'color':        (100, 255, 100),
        'alpha':        35,
        'description':  ['4G LTE cellular', 'downlink band —', 'digital data only'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Cellular 800 MHz / Public Safety 800: 806–869 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Cell 800',
        'full_name':    'Cellular / Public Safety 800 MHz',
        'start':        806.0,
        'end':          869.0,
        'color':        (100, 200, 100),
        'alpha':        35,
        'description':  ['800 MHz cellular,', 'P25 public safety,', 'and trunked systems'],
        'demod_mode':   'fm',
        'sample_rate':  16000,
        'bandwidth':    12500,
        'min_bandwidth':10000,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # GSM 900 / CDMA Cellular: 869–960 MHz
    # ------------------------------------------------------------------
    {
        'name':         'GSM 900',
        'full_name':    'GSM / CDMA Cellular (900 MHz)',
        'start':        869.0,
        'end':          960.0,
        'color':        (80, 180, 80),
        'alpha':        35,
        'description':  ['GSM 900 and CDMA', 'cellular downlink —', 'digital voice/data'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Aeronautical DME / TACAN: 960–1215 MHz
    # ------------------------------------------------------------------
    {
        'name':         'DME/TACAN',
        'full_name':    'Aeronautical DME / TACAN',
        'start':        960.0,
        'end':          1215.0,
        'color':        (220, 220, 80),
        'alpha':        35,
        'description':  ['Distance measuring', 'equipment and TACAN', 'aviation navigation'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # ADS-B Aircraft Transponders: 1090 MHz  (point band)
    # ------------------------------------------------------------------
    {
        'name':         'ADS-B',
        'full_name':    'ADS-B Aircraft Tracking',
        'start':        1085.0,
        'end':          1095.0,
        'color':        (0, 200, 0),
        'alpha':        50,
        'description':  ['ADS-B aircraft', 'transponder data at', '1090 MHz (Mode S)'],
        'demod_mode':   None,   # Requires dedicated ADS-B decoder (e.g. dump1090)
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # GPS L2 / GLONASS: 1215–1300 MHz
    # ------------------------------------------------------------------
    {
        'name':         'GPS L2',
        'full_name':    'GPS L2 / GLONASS',
        'start':        1215.0,
        'end':          1300.0,
        'color':        (0, 220, 180),
        'alpha':        35,
        'description':  ['GPS L2 and GLONASS', 'satellite navigation', 'signals (data)'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # Mobile Satellite (Inmarsat): 1525–1559 MHz
    # ------------------------------------------------------------------
    {
        'name':         'Inmarsat',
        'full_name':    'Mobile Satellite (Inmarsat)',
        'start':        1525.0,
        'end':          1559.0,
        'color':        (0, 180, 220),
        'alpha':        35,
        'description':  ['Inmarsat satellite', 'voice/data — maritime', 'and aviation use'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # GPS L1 / Galileo / GLONASS: 1559–1610 MHz
    # ------------------------------------------------------------------
    {
        'name':         'GPS L1',
        'full_name':    'GPS L1 / Galileo / GLONASS',
        'start':        1559.0,
        'end':          1610.0,
        'color':        (0, 255, 200),
        'alpha':        40,
        'description':  ['GPS L1, Galileo,', 'and GLONASS satellite', 'navigation signals'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # LTE 1700 / AWS Band: 1710–1880 MHz
    # ------------------------------------------------------------------
    {
        'name':         'LTE 1700',
        'full_name':    'LTE / UMTS Cellular (1700/1800 MHz)',
        'start':        1710.0,
        'end':          1880.0,
        'color':        (100, 255, 150),
        'alpha':        35,
        'description':  ['4G LTE AWS band,', 'UMTS cellular', 'downlink signals'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # DECT Cordless Phones: 1880–1900 MHz
    # ------------------------------------------------------------------
    {
        'name':         'DECT',
        'full_name':    'DECT Cordless Phones',
        'start':        1880.0,
        'end':          1900.0,
        'color':        (255, 180, 255),
        'alpha':        40,
        'description':  ['DECT digital', 'cordless telephone', 'systems (6.0 Plus)'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },

    # ------------------------------------------------------------------
    # PCS Cellular 1900 MHz: 1900–1990 MHz
    # ------------------------------------------------------------------
    {
        'name':         'PCS 1900',
        'full_name':    'PCS Cellular (1900 MHz)',
        'start':        1900.0,
        'end':          1990.0,
        'color':        (80, 255, 120),
        'alpha':        35,
        'description':  ['PCS 1900 MHz band,', 'GSM/LTE cellular', 'downlink signals'],
        'demod_mode':   None,
        'sample_rate':  None,
        'bandwidth':    None,
        'min_bandwidth':None,
        'gain':         None,
        'squelch':      0,
    },
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_band_for_freq(freq_mhz):
    """
    Return the best-matching band dict for a frequency in MHz, or None.

    Priority: the first band in BANDS whose [start, end] range contains
    freq_mhz.  Because NOAA Weather Radio (162–163 MHz) is listed before the
    broader Marine VHF (156–162 MHz) and Public Safety VHF (154–158 MHz)
    entries, the more specific allocation wins for overlapping regions.

    Args:
        freq_mhz (float): Frequency in MHz

    Returns:
        dict | None: Matching band dict, or None if outside all known bands.
    """
    for band in BANDS:
        if band['start'] <= freq_mhz <= band['end']:
            return band
    return None


def get_band_for_freq_hz(freq_hz):
    """
    Convenience wrapper — accepts frequency in Hz.

    Args:
        freq_hz (float): Frequency in Hz

    Returns:
        dict | None
    """
    return get_band_for_freq(freq_hz / 1e6)


def get_demod_params(freq_mhz):
    """
    Return demodulation parameters for a frequency, falling back to a
    sensible NBFM default if the frequency is unknown or data-only.

    Args:
        freq_mhz (float): Frequency in MHz

    Returns:
        dict with keys: mode, sample_rate, bandwidth, min_bandwidth,
                        gain, squelch, mode_name, band_name, band_description
    """
    band = get_band_for_freq(freq_mhz)

    if band and band['demod_mode'] is not None:
        return {
            'mode':           band['demod_mode'],
            'sample_rate':    band['sample_rate'],
            'bandwidth':      band['bandwidth'],
            'min_bandwidth':  band['min_bandwidth'],
            'gain':           band['gain'],
            'squelch':        band['squelch'],
            'mode_name':      '{} ({})'.format(
                                  band['demod_mode'].upper(),
                                  band['full_name']),
            'band_name':      band['full_name'],
            'band_description': band['description'],
        }

    # Fallback: generic NBFM
    band_name = band['full_name'] if band else 'Unknown Band'
    band_desc  = band['description'] if band else [
        'Unknown frequency', 'range — using', 'default NBFM mode'
    ]
    return {
        'mode':           'fm',
        'sample_rate':    12000,
        'bandwidth':      12500,
        'min_bandwidth':  10000,
        'gain':           None,
        'squelch':        0,
        'mode_name':      'NBFM (Default)',
        'band_name':      band_name,
        'band_description': band_desc,
    }
