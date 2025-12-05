def get_sys_color(sys_char):
    """
    Return a predefined color (hex string) based on satellite system identifier.

    Parameters
    ----------
    sys_char : str
        Single-character system identifier:
        'G' = GPS, 'R' = GLONASS, 'E' = Galileo,
        'C' = BeiDou, 'J' = QZSS, 'S' = SBAS.

    Returns
    -------
    str
        Hex color code associated with the satellite system.
    """
    colors = {
        'G': '#4CAF50', # GPS - Green
        'R': '#F44336', # GLONASS - Red
        'E': '#2196F3', # Galileo - Blue
        'C': '#9C27B0', # BeiDou - Purple
        'J': '#FF9800', # QZSS - Orange
        'S': '#9E9E9E'  # SBAS - Grey
    }
    return colors.get(sys_char, '#000000')


def get_signal_color(sig_code):
    """
    Determine display color for a GNSS signal based on its frequency band
    and signal suffix (e.g., L1C, L2P, E5aQ).

    Parameters
    ----------
    sig_code : str or int
        Signal code containing frequency-band information (1, 2, 5, 6, 7/8)
        and a suffix letter identifying the modulation (e.g., C, P, Q, X).

    Logic
    -----
    - Extract the frequency band by checking digits (1/2/5/6/7/8).
    - Extract the first alphabetic character as the signal suffix.
    - Assign color based on band–suffix combinations commonly used in GNSS:
        L1 / B1 / E1
        L2 / G2 / E2
        L5 / E5 / B2
        L6 / B3
        E7 / E8 / B2a / B2b, etc.

    Returns
    -------
    str
        Hex color code representing this signal type for visualization.
    """
    code = str(sig_code).upper()
    band = '1'
    suffix = ''

    # Determine frequency band
    if '1' in code: band = '1'
    elif '2' in code: band = '2'
    elif '5' in code: band = '5'
    elif '6' in code: band = '6'
    elif '7' in code or '8' in code: band = '7'

    # Extract first alphabetic character as suffix
    for char in code:
        if char.isalpha():
            suffix = char
            break

    # Assign color by band + suffix combination
    if band == '1':
        if suffix in ['C', 'S', 'A']: return '#2196F3'
        if suffix in ['W', 'P', 'Y']: return '#0D47A1'
        if suffix in ['L', 'X', 'Z']: return '#00BCD4'
        if suffix in ['I']:           return '#64B5F6'
        return '#2196F3'

    elif band == '2':
        if suffix in ['C', 'I']:      return '#FF5722'
        if suffix in ['W', 'P', 'Y']: return '#B71C1C'
        if suffix in ['L', 'S', 'X']: return '#FF9800'
        if suffix in ['Q']:           return '#FFCC80'
        return '#F44336'

    elif band == '5':
        if suffix in ['Q', 'X']:      return '#4CAF50'
        if suffix in ['I', 'D']:      return '#1B5E20'
        if suffix in ['P']:           return '#8BC34A'
        return '#4CAF50'

    elif band == '6':
        return '#9C27B0'

    elif band == '7':
        return '#FFC107'

    return '#9E9E9E'
