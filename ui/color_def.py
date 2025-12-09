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
        # L1 band - blue series, but increase the difference    
        if suffix in ['C', 'S', 'A']: return '#1976D2'  # Standard blue - more saturated
        if suffix in ['W', 'P', 'Y']: return '#0D47A1'  # Deep blue - keep
        if suffix in ['L', 'X', 'Z']: return '#42A5F5'  # Light blue - brighter and more obvious
        if suffix in ['I']:           return '#90CAF9'  # Very light blue - obvious difference
        if suffix in ['B']:           return '#1565C0'  # Medium blue
        return '#2196F3'  # Default blue

    elif band == '2':
        # L2频段 - 红色/橙色系，增加明显差异
        if suffix in ['C', 'I']:      return '#E53935'  # 鲜红 - 更饱和
        if suffix in ['W', 'P', 'Y']: return '#B71C1C'  # 深红 - 保持
        if suffix in ['L', 'S', 'X']: return '#FF6F00'  # 橙色 - 更鲜明
        if suffix in ['Q']:           return '#FFB74D'  # 浅橙 - 明显区别
        if suffix in ['D']:           return '#D32F2F'  # 中红
        return '#F44336'  # 默认红

    elif band == '5':
        # L5频段 - 绿色系，增加明显差异
        if suffix in ['Q', 'X']:      return '#388E3C'  # 深绿 - 更饱和
        if suffix in ['I', 'D']:      return '#1B5E20'  # 很深的绿 - 保持
        if suffix in ['P']:           return '#66BB6A'  # 浅绿 - 更明显
        if suffix in ['A']:           return '#A5D6A7'  # 很浅的绿 - 明显区别
        return '#4CAF50'  # 默认绿

    elif band == '6':
        # L6频段 - 紫色系，增加不同频点的区分
        if suffix in ['I']:           return '#7B1FA2'  # 深紫
        if suffix in ['Q']:           return '#BA68C8'  # 浅紫
        if suffix in ['X']:           return '#9C27B0'  # 标准紫
        return '#9C27B0'  # 默认紫

    elif band == '7':
        # E7/E8频段 - 黄色/琥珀色系
        if suffix in ['Q']:           return '#F57C00'  # 深橙黄
        if suffix in ['I']:           return '#FFB300'  # 中黄
        if suffix in ['X']:           return '#FFC107'  # 标准黄
        if suffix in ['A', 'B']:      return '#FFD54F'  # 浅黄
        return '#FFC107'  # 默认黄

    return '#9E9E9E'  # 默认灰色
