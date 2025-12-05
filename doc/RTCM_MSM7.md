# RTCM MSM7 观测值解析与计算 _handle_msm_obs


> **日期**：2025-12-01  
> **适用标准**：RTCM 10403.3 MSM7 (Message Types 1077, 1087, 1097, 1117, 1127, 1137)

---

## 1. 简介 (Introduction)

RTCM 3.x 中的 **MSM7** (Multiple Signal Message Type 7) 是目前精度最高、包含信息最全的 GNSS 观测值格式。相比于 MSM4/5，MSM7 通过增加扩展分辨率字段，能够提供极其精细的伪距和载波相位观测值，适用于高精度 RTK 和 PPP 解算。

本文档详细说明如何基于二进制流解析 DF (Data Field) 字段，并利用物理公式还原出伪距、载波相位、多普勒和信噪比。

---

## 2. 消息结构与系统映射

解析的第一步是根据 Message ID 确定卫星系统 (System) 和时间基准。

### 2.1 系统映射表

| MSM7 消息 ID | 卫星系统 | 缩写 | 时间字段 (Time DF) |
| :--- | :--- | :---: | :--- |
| **1077** | GPS | G | DF004 |
| **1087** | GLONASS | R | DF034 |
| **1097** | Galileo | E | DF248 |
| **1117** | QZSS | J | DF428 |
| **1127** | BeiDou (BDS) | C | DF427 |
| **1137** | NavIC (IRNSS) | I | DF546 |

### 2.2 解析流程概览

1.  **消息头解析**：获取系统 ID、时间戳。
2.  **掩码解析**：读取 `CELLPRN` 掩码，确定当前消息包含哪些卫星 (Sat) 和哪些信号通道 (Cell)。
3.  **卫星级数据**：提取所有卫星共用的粗略信息（粗伪距、粗多普勒）。
4.  **信号级数据**：提取每个频点的精细信息（精伪距、精相位、精多普勒、SNR）。
5.  **数据合成**：将“粗略值”与“精细值”组合，还原物理量。

---

## 3. 关键 DF 字段定义

根据 RTCM 标准及实现代码，关键字段定义如下：

### 3.1 卫星级字段 (Satellite Data)
*每颗卫星传输一次，提供观测值的“整数毫秒”及“粗略部分”。*

| DF 编号 | 位宽 | 类型 | 比例因子 (Scale) | 单位 | 物理含义 |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **DF397** | 8 | UINT | 1 | ms | **粗伪距整数部分** (Integer Milliseconds) |
| **DF398** | 10 | UINT | $2^{-10}$ | ms | **粗伪距小数部分** (Modulo 1ms) |
| **DF399** | 14 | INT | *见注1* | m/s | **粗相位距离变化率** (Rough Range Rate) |

> **注1**：RTCM 标准定义 DF399 比例为 1 m/s。但在本实现代码中，为了匹配特定的内部单位或硬件输出，使用了 **0.00025 m/s** 作为计算因子。

### 3.2 信号级字段 (Signal Data)
*每个信号通道 (Cell) 传输一次，提供相对于粗略值的“高精度增量”。*

| DF 编号 | 位宽 | 类型 | 比例因子 (Scale) | 单位 | 物理含义 |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **DF405** | 20 | INT | $2^{-29}$ | ms | **精伪距** (Fine Pseudorange, Extended) |
| **DF406** | 24 | INT | $2^{-31}$ | ms | **精载波相位** (Fine PhaseRange, Extended) |
| **DF404** | 15 | INT | $0.0001$ | m/s | **精相位距离变化率** (Fine Phase Range Rate) |
| **DF408** | 10 | UINT | $2^{-4}$ | dBHz | **高精度信噪比** (Extended SNR) |
| **DF407** | 10 | UINT | (Lookup) | - | **锁定时间指示** (Lock Time Indicator) |
| **DF420** | 1 | BIT | - | - | **半周模糊度** (Half-cycle Ambiguity) |

---

## 4. 观测值还原公式 (Reconstruction Formulas)

本节展示如何将上述 DF 字段转换为实际的物理观测值。

### 4.1 物理常量与因子

```python
CLIGHT   = 299792458.0          # 光速 (m/s)
RANGE_MS = CLIGHT / 1000.0      # 1毫秒光行距离 (~299792.458 m)

P2_10 = 1.0 / 1024.0            # 2^-10
P2_29 = 1.0 / 536870912.0       # 2^-29
P2_31 = 1.0 / 2147483648.0      # 2^-31
```

### 4.2 粗伪距计算 (Rough Range)

粗伪距是所有观测值的基础参考量。

$$
R_{\text{sat}} = \left( \text{DF397} \times \text{RANGE\_MS} \right) + \left( \text{DF398} \times 2^{-10} \times \text{RANGE\_MS} \right)
$$

*   **DF397**：整毫秒数
*   **DF398**：毫秒内的小数部分

### 4.3 完整伪距 (Pseudorange)

通过累加精伪距修正量得到最终伪距。

$$
\rho = R_{\text{sat}} + \left( \text{DF405} \times 2^{-29} \times \text{RANGE\_MS} \right)
$$

*   **单位**：米 (m)
*   **有效性**：若 `DF405 == -524288` (0x80000)，则该伪距无效。

### 4.4 载波相位 (Carrier Phase)

载波相位首先被还原为“相位距离”（单位：米），然后除以波长转换为“周”。

1.  **相位距离 (Phase Range in meters)**:
    $$
    D_{\phi} = R_{\text{sat}} + \left( \text{DF406} \times 2^{-31} \times \text{RANGE\_MS} \right)
    $$

2.  **转换为周 (Cycles)**:
    $$
    L = \frac{D_{\phi}}{\lambda} = \frac{D_{\phi} \times f}{c}
    $$

*   **$f$**：当前信号的频率 (Hz)
*   **$c$**：光速
*   **有效性**：若 `DF406 == -8388608` (0x800000)，则该相位无效。

### 4.5 多普勒频移 (Doppler)

多普勒由“粗变化率”和“精变化率”合成。RTCM 传输的是 **Range Rate** (距离变化率)，符号与多普勒频率相反（卫星远离，距离增加，Doppler 为负）。

1.  **粗变化率 (Rough Rate)**:
    $$
    V_{\text{rough}} = \text{DF399} \times 0.00025 \quad (\text{m/s})
    $$
    *(注：此处系数 0.00025 源自代码实现)*

2.  **精变化率 (Fine Rate)**:
    $$
    V_{\text{fine}} = \text{DF404} \times 0.0001 \quad (\text{m/s})
    $$

3.  **多普勒 (Hz)**:
    $$
    \text{Doppler} = - \frac{(V_{\text{rough}} + V_{\text{fine}}) \times f}{c}
    $$

*   **有效性**：若 `DF399 == -8192` 或 `DF404 == -16384`，则多普勒无效。

### 4.6 信噪比 (SNR)

MSM7 使用扩展分辨率，使得 SNR 精度达到 $1/16$ dB-Hz。

$$
\text{SNR} = \text{DF408} \times 2^{-4} \quad (\text{dB-Hz})
$$

---

## 5. 参考实现代码

以下 Python 代码展示了上述公式的实际编程实现。

```python
def _handle_msm_obs(self, msg):
    """
    Parse RTCM 3.2 MSM7 observation message.
    Extracts high-precision Pseudorange, Phase, and Doppler using Extended Resolution fields.
    """
    # ------------------------------- Constants --------------------------------
    P2_10 = 1.0 / 1024.0
    P2_29 = 1.0 / (2 ** 29)
    P2_31 = 1.0 / (2 ** 31)
    CLIGHT = 299792458.0
    RANGE_MS = CLIGHT / 1000.0  # Range in 1 ms

    # Identify System and Time (Header Parsing)
    # ... (System ID mapping logic omitted for brevity, refer to full code) ...
    
    # ------------------------ Satellite-level data -------------------------
    # Cached per PRN
    rough_range = 0.0
    rough_rate = 0.0

    # DF397: Integer ms, DF398: Fractional ms
    rng_int = getattr(msg, f"DF397_{sat_idx}", None)
    rng_mod = getattr(msg, f"DF398_{sat_idx}", 0)
    
    # DF399: Rough Range Rate
    rate_rough = getattr(msg, f"DF399_{sat_idx}", None)

    # 1. Calculate Rough Range (Base for PR and Phase)
    if rng_int is not None and rng_int != 255:
        rough_range = rng_int * RANGE_MS
        rough_range += rng_mod * P2_10 * RANGE_MS

    # 2. Calculate Rough Rate (Base for Doppler)
    if rate_rough is not None and rate_rough != -8192:
        rough_rate = rate_rough * 0.00025  # Implementation specific scale

    # ------------------------- Signal-level data --------------------------
    # DF405: Fine Pseudorange (20 bits)
    pr_fine = getattr(msg, f"DF405_{idx}", None)
    pseudorange = 0.0
    if rough_range != 0.0 and pr_fine is not None and pr_fine != -524288:
        # Formula: Rough + Fine * 2^-29 * RANGE_MS
        pseudorange = rough_range + pr_fine * P2_29 * RANGE_MS

    # DF406: Fine Carrier Phase (24 bits)
    cp_fine = getattr(msg, f"DF406_{idx}", None)
    carrier_phase = 0.0
    if rough_range != 0.0 and cp_fine is not None and cp_fine != -8388608:
        # Formula: (Rough + Fine * 2^-31 * RANGE_MS) * freq / c
        ph_m = rough_range + cp_fine * P2_31 * RANGE_MS
        if freq > 0:
            carrier_phase = ph_m * freq / CLIGHT

    # DF404: Fine Doppler (15 bits)
    rr_fine = getattr(msg, f"DF404_{idx}", None)
    doppler = 0.0
    if rough_rate != -8192 and rr_fine is not None and rr_fine != -16384:
        # Formula: -(RoughRate + FineRate * 0.0001) * freq / c
        total_rate = rough_rate + rr_fine * 0.0001
        if freq > 0:
            doppler = -total_rate * freq / CLIGHT

    # DF408: Extended SNR (10 bits)
    snr_raw = getattr(msg, f"DF408_{idx}", 0)
    snr = snr_raw * (2 ** -4)  # Scale: 0.0625

    return {
        "pseudorange": pseudorange,
        "phase": carrier_phase,
        "doppler": doppler,
        "snr": snr
    }
```

---

## 6. 异常值速查表

在数据处理中，必须过滤以下无效值：

| 字段 | HEX | DEC | 含义 |
| :--- | :--- | :--- | :--- |
| **DF397** | `0xFF` | 255 | 粗伪距无效 |
| **DF399** | `0x2000` | -8192 | 粗变化率无效 |
| **DF405** | `0x80000` | -524288 | 精伪距无效 |
| **DF406** | `0x800000` | -8388608 | 精相位无效 |
| **DF404** | `0x4000` | -16384 | 精变化率无效 |