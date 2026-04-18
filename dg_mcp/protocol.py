"""DG-Lab Coyote 3.0 V3 BLE protocol constants and helpers."""

# BLE UUIDs (base: 0000xxxx-0000-1000-8000-00805f9b34fb)
SERVICE_UUID = "0000180c-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000150a-0000-1000-8000-00805f9b34fb"   # B0/BF commands
NOTIFY_UUID = "0000150b-0000-1000-8000-00805f9b34fb"   # B1 responses
BATTERY_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
BATTERY_UUID = "00001500-0000-1000-8000-00805f9b34fb"

# Device name prefix
DEVICE_NAME_PREFIX = "47L121"

# Strength range
STRENGTH_MIN = 0
STRENGTH_MAX = 200

# Wave frequency range (input: 10~1000, encoded: 10~240)
WAVE_FREQ_MIN = 10
WAVE_FREQ_MAX = 1000
WAVE_FREQ_ENCODED_MIN = 10
WAVE_FREQ_ENCODED_MAX = 240

# Wave intensity range
WAVE_INTENSITY_MIN = 0
WAVE_INTENSITY_MAX = 100

# Strength interpretation modes (2 bits per channel)
STRENGTH_NONE = 0b00      # no change
STRENGTH_INCREASE = 0b01  # relative increase
STRENGTH_DECREASE = 0b10  # relative decrease
STRENGTH_ABSOLUTE = 0b11  # absolute set


def encode_frequency(freq_ms: int) -> int:
    """Convert frequency in ms (10~1000) to encoded value (10~240).

    Uses the V3 compression algorithm from the SDK.
    """
    if freq_ms < 10 or freq_ms > 1000:
        return 10
    if freq_ms <= 100:
        return freq_ms
    if freq_ms <= 600:
        return (freq_ms - 100) // 5 + 100
    return (freq_ms - 600) // 10 + 200


def build_b0(
    seq: int,
    strength_mode: int,
    strength_a: int,
    strength_b: int,
    wave_freq_a: tuple[int, int, int, int],
    wave_int_a: tuple[int, int, int, int],
    wave_freq_b: tuple[int, int, int, int],
    wave_int_b: tuple[int, int, int, int],
) -> bytes:
    """Build a 20-byte B0 instruction.

    Args:
        seq: Sequence number (0~15, 4 bits)
        strength_mode: Strength interpretation (4 bits: high 2 = A, low 2 = B)
        strength_a: A channel strength setting (0~200)
        strength_b: B channel strength setting (0~200)
        wave_freq_a: A channel wave frequencies x4 (encoded 10~240)
        wave_int_a: A channel wave intensities x4 (0~100)
        wave_freq_b: B channel wave frequencies x4 (encoded 10~240)
        wave_int_b: B channel wave intensities x4 (0~100)
    """
    header = 0xB0
    seq_and_mode = ((seq & 0x0F) << 4) | (strength_mode & 0x0F)

    data = bytearray(20)
    data[0] = header
    data[1] = seq_and_mode
    data[2] = min(max(strength_a, 0), 200)
    data[3] = min(max(strength_b, 0), 200)

    for i in range(4):
        data[4 + i] = min(max(wave_freq_a[i], 0), 255)
        data[8 + i] = min(max(wave_int_a[i], 0), 255)
        data[12 + i] = min(max(wave_freq_b[i], 0), 255)
        data[16 + i] = min(max(wave_int_b[i], 0), 255)

    return bytes(data)


def build_bf(
    limit_a: int,
    limit_b: int,
    balance_freq_a: int = 160,
    balance_freq_b: int = 160,
    balance_int_a: int = 0,
    balance_int_b: int = 0,
) -> bytes:
    """Build a 7-byte BF instruction.

    Args:
        limit_a: A channel pain endurance limit (0~200)
        limit_b: B channel pain endurance limit (0~200)
        balance_freq_a: A channel frequency balance param (0~255)
        balance_freq_b: B channel frequency balance param (0~255)
        balance_int_a: A channel intensity balance param (0~255)
        balance_int_b: B channel intensity balance param (0~255)
    """
    return bytes([
        0xBF,
        min(max(limit_a, 0), 200),
        min(max(limit_b, 0), 200),
        min(max(balance_freq_a, 0), 255),
        min(max(balance_freq_b, 0), 255),
        min(max(balance_int_a, 0), 255),
        min(max(balance_int_b, 0), 255),
    ])


def parse_b1(data: bytes) -> dict:
    """Parse a B1 notification response.

    Returns dict with seq, strength_a, strength_b.
    """
    if len(data) < 4 or data[0] != 0xB1:
        return {}
    return {
        "seq": data[1],
        "strength_a": data[2],
        "strength_b": data[3],
    }


# Inactive wave data: intensity > 100 causes channel to be ignored
WAVE_INACTIVE = (0, 0, 0, 101)
WAVE_FREQ_ZERO = (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# V2 Protocol (DG-Lab Coyote V2 / "D-LAB ESTIM01")
# ---------------------------------------------------------------------------

V2_DEVICE_NAME = "D-LAB ESTIM01"

# BLE UUIDs (base: 955Axxxx-0FE2-F5AA-A094-84B8D4F3E8AD)
V2_BATTERY_SERVICE_UUID = "955A180A-0FE2-F5AA-A094-84B8D4F3E8AD"
V2_BATTERY_UUID         = "955A1500-0FE2-F5AA-A094-84B8D4F3E8AD"
V2_PWM_SERVICE_UUID     = "955A180B-0FE2-F5AA-A094-84B8D4F3E8AD"
V2_PWM_AB2_UUID         = "955A1504-0FE2-F5AA-A094-84B8D4F3E8AD"  # strength (R/W/Notify)
V2_PWM_A34_UUID         = "955A1505-0FE2-F5AA-A094-84B8D4F3E8AD"  # channel B waveform (R/W)
V2_PWM_B34_UUID         = "955A1506-0FE2-F5AA-A094-84B8D4F3E8AD"  # channel A waveform (R/W)

# V2 internal strength range (wire units)
V2_STRENGTH_MAX = 2047


def build_v2_pwm_ab2(strength_a: int, strength_b: int) -> bytes:
    """Build a 3-byte PWM_AB2 strength packet.

    Args:
        strength_a: Channel A internal strength (0-2047)
        strength_b: Channel B internal strength (0-2047)

    Returns:
        3-byte little-endian bit-packed strength packet.
        Bit layout: bits 23-22 reserved, bits 21-11 = A, bits 10-0 = B.
    """
    a = max(0, min(2047, strength_a))
    b = max(0, min(2047, strength_b))
    packed = ((a & 0x7FF) << 11) | (b & 0x7FF)
    return bytes([packed & 0xFF, (packed >> 8) & 0xFF, (packed >> 16) & 0xFF])


def build_v2_pwm_wave(period_ms: int, intensity_pct: int) -> bytes:
    """Build a 3-byte PWM_A34/B34 waveform packet.

    Args:
        period_ms: Waveform period in ms (10-1000).
        intensity_pct: Intensity 0-100.

    Returns:
        3-byte packet encoding X (pulse count), Y (gap interval), Z (pulse width).

    Byte layout (verified against official example hex):
        byte[0] bits 4-0 = X (0-31)
        byte[0] bits 7-5 + byte[1] bits 6-0 = Y (0-1023)
        byte[2] = Z (0-31)
    """
    period_ms = max(10, min(1000, period_ms))
    x = round((period_ms / 1000) ** 0.5 * 15)
    x = max(0, min(31, x))
    y = max(0, min(1023, period_ms - x))
    z = max(0, min(31, round(intensity_pct * 31 / 100)))
    byte0 = (x & 0x1F) | ((y & 0x07) << 5)
    byte1 = (y >> 3) & 0x7F
    byte2 = z & 0x1F
    return bytes([byte0, byte1, byte2])


def parse_v2_pwm_ab2(data: bytes) -> dict:
    """Parse a 3-byte PWM_AB2 notification into internal strength values.

    Returns:
        Dict with 'strength_a' and 'strength_b' (0-2047), or empty dict on error.
    """
    if len(data) < 3:
        return {}
    packed = data[0] | (data[1] << 8) | (data[2] << 16)
    return {
        "strength_b": packed & 0x7FF,
        "strength_a": (packed >> 11) & 0x7FF,
    }


def v2_strength_to_user(internal: int) -> int:
    """Convert V2 internal strength (0-2047) to user-facing value (0-200)."""
    return round(internal * 200 / 2047)


def v2_strength_from_user(user: int) -> int:
    """Convert user-facing strength (0-200) to V2 internal value (0-2047)."""
    return round(max(0, min(200, user)) * 2047 / 200)
