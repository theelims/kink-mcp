"""BLE device manager for DG-Lab Coyote (V2 and V3) and Lovense vibration toys."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import humanize
from bleak import BleakClient, BleakScanner

from .lovense import LovenseDevice, is_lovense_name, LOVENSE_NAME_PREFIXES
from .protocol import (
    BATTERY_UUID,
    DEVICE_NAME_PREFIX,
    NOTIFY_UUID,
    STRENGTH_ABSOLUTE,
    STRENGTH_DECREASE,
    STRENGTH_INCREASE,
    STRENGTH_MAX,
    STRENGTH_MIN,
    STRENGTH_NONE,
    WAVE_FREQ_ZERO,
    WAVE_INACTIVE,
    WRITE_UUID,
    V2_BATTERY_UUID,
    V2_DEVICE_NAME,
    V2_PWM_A34_UUID,
    V2_PWM_AB2_UUID,
    V2_PWM_B34_UUID,
    build_b0,
    build_bf,
    build_v2_pwm_ab2,
    build_v2_pwm_wave,
    encode_frequency,
    parse_b1,
    parse_v2_pwm_ab2,
    v2_strength_from_user,
    v2_strength_to_user,
)
from .waves import WaveFrame

logger = logging.getLogger(__name__)


def _pct_to_raw(pct: int) -> int:
    """Convert 0–100% to internal 0–200 range."""
    return round(max(0, min(100, pct)) * 2)


def _raw_to_pct(raw: int) -> int:
    """Convert internal 0–200 range to 0–100%."""
    return round(raw / 2)


@dataclass
class DeviceState:
    """Current device state."""
    connected: bool = False
    address: str = ""
    name: str = ""
    version: str = "v3"   # "v2" or "v3"
    strength_a: int = 0
    strength_b: int = 0
    limit_a: int = 200
    limit_b: int = 200
    battery: int = -1

    # Pending strength changes (accumulated between write loop ticks)
    _pending_strength_a: int = 0
    _pending_strength_b: int = 0
    _absolute_a: int | None = None
    _absolute_b: int | None = None

    # Wave playback state per channel
    # loop: 0 = infinite, N > 0 = N full cycles remaining
    wave_a: list[WaveFrame] = field(default_factory=list)
    wave_b: list[WaveFrame] = field(default_factory=list)
    wave_a_index: int = 0
    wave_b_index: int = 0
    wave_a_loop: int = 0
    wave_b_loop: int = 0

    # V3 sequence tracking
    _seq: int = 0
    _awaiting_seq: int | None = None


class CoyoteDevice:
    """Manages BLE connection and communication with Coyote V2 and V3."""

    def __init__(self) -> None:
        self.state = DeviceState()
        self._client: BleakClient | None = None
        self._loop_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def scan(self, timeout: float = 5.0) -> list[dict]:
        """Scan for nearby Coyote devices (V2 and V3).

        Returns list of {name, address, version} dicts.
        """
        devices = await BleakScanner.discover(timeout=timeout)
        results = []
        for d in devices:
            name = d.name or ""
            if name.startswith(DEVICE_NAME_PREFIX):
                results.append({"name": name, "address": d.address, "version": "v3"})
            elif name == V2_DEVICE_NAME:
                results.append({"name": name, "address": d.address, "version": "v2"})
        return results

    async def connect(self, address: str, version: str = "v3") -> None:
        """Connect to a Coyote device by address.

        Args:
            address: BLE device address from scan results.
            version: Device protocol version — "v2" or "v3" (default "v3").
        """
        if version not in ("v2", "v3"):
            raise ValueError(f"Unknown version '{version}'. Must be 'v2' or 'v3'.")
        if self.state.connected:
            raise RuntimeError("Already connected. Disconnect first.")

        self._client = BleakClient(address)
        await self._client.connect()

        if not self._client.is_connected:
            raise RuntimeError(f"Failed to connect to {address}")

        self.state.connected = True
        self.state.address = address
        self.state.version = version

        # Read battery level
        battery_uuid = BATTERY_UUID if version == "v3" else V2_BATTERY_UUID
        try:
            battery_data = await self._client.read_gatt_char(battery_uuid)
            if battery_data:
                self.state.battery = battery_data[0]
        except Exception:
            logger.debug("Could not read battery level")

        self._stop_event.clear()

        if version == "v3":
            await self._client.start_notify(NOTIFY_UUID, self._on_notify)
            await self._write_bf()
            self._loop_task = asyncio.create_task(self._b0_loop())
        else:  # v2
            await self._client.start_notify(V2_PWM_AB2_UUID, self._on_notify_v2)
            self._loop_task = asyncio.create_task(self._v2_loop())

        logger.info("Connected to %s (%s)", address, version)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._loop_task:
            self._stop_event.set()
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        if self._client and self._client.is_connected:
            await self._client.disconnect()

        self.state = DeviceState()
        self._client = None
        logger.info("Disconnected")

    # --- Strength control ---

    def set_strength(self, channel: str, value: int) -> None:
        """Set absolute strength for a channel (0~200)."""
        value = max(STRENGTH_MIN, min(STRENGTH_MAX, value))
        if channel.upper() == "A":
            self.state._absolute_a = value
        elif channel.upper() == "B":
            self.state._absolute_b = value
        else:
            raise ValueError(f"Invalid channel: {channel}")

    def add_strength(self, channel: str, delta: int) -> None:
        """Add/subtract strength for a channel."""
        if channel.upper() == "A":
            self.state._absolute_a = None  # cancel any pending absolute
            self.state._pending_strength_a += delta
        elif channel.upper() == "B":
            self.state._absolute_b = None
            self.state._pending_strength_b += delta
        else:
            raise ValueError(f"Invalid channel: {channel}")

    async def set_strength_limit(self, limit_a: int, limit_b: int) -> None:
        """Set strength soft limits.

        V3: persisted on device via BF command.
        V2: software-enforced cap applied in the write loop.
        """
        self.state.limit_a = max(0, min(200, limit_a))
        self.state.limit_b = max(0, min(200, limit_b))
        if self.state.version == "v3":
            await self._write_bf()

    # --- Wave control ---

    def send_wave(
        self,
        channel: str,
        frames: list[WaveFrame],
        loop: int = 0,
    ) -> None:
        """Start playing waveform frames on a channel.

        Args:
            loop: 0 = infinite, N > 0 = play N full cycles then stop.
        """
        if channel.upper() == "A":
            self.state.wave_a = frames
            self.state.wave_a_index = 0
            self.state.wave_a_loop = loop
        elif channel.upper() == "B":
            self.state.wave_b = frames
            self.state.wave_b_index = 0
            self.state.wave_b_loop = loop
        else:
            raise ValueError(f"Invalid channel: {channel}")

    def stop_wave(self, channel: str | None = None) -> None:
        """Stop waveform on a channel (or both if None)."""
        if channel is None or channel.upper() == "A":
            self.state.wave_a = []
            self.state.wave_a_index = 0
        if channel is None or channel.upper() == "B":
            self.state.wave_b = []
            self.state.wave_b_index = 0

    # --- V3 internal ---

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        """Handle B1 notifications from a V3 device."""
        result = parse_b1(bytes(data))
        if result:
            self.state.strength_a = result["strength_a"]
            self.state.strength_b = result["strength_b"]
            if (
                self.state._awaiting_seq is not None
                and result["seq"] == self.state._awaiting_seq
            ):
                self.state._awaiting_seq = None
            logger.debug(
                "B1: seq=%d A=%d B=%d",
                result["seq"],
                result["strength_a"],
                result["strength_b"],
            )

    async def _write_bf(self) -> None:
        """Write BF instruction to set limits and balance params (V3 only)."""
        if not self._client or not self._client.is_connected:
            return
        data = build_bf(self.state.limit_a, self.state.limit_b)
        await self._client.write_gatt_char(WRITE_UUID, data)
        logger.debug("BF written: limit_a=%d limit_b=%d", self.state.limit_a, self.state.limit_b)

    def _advance_wave(
        self,
        wave: list[WaveFrame],
        idx: int,
        loop: int,
    ) -> tuple[list[WaveFrame], int, int]:
        """Advance wave index, handling end-of-cycle loop logic.

        Returns (wave, next_idx, next_loop).
        """
        next_idx = idx + 1
        if next_idx < len(wave):
            return wave, next_idx, loop

        # End of cycle
        if loop == 0:
            return wave, 0, 0          # infinite: restart
        elif loop == 1:
            return [], 0, 0            # last cycle done: clear
        else:
            return wave, 0, loop - 1   # decrement remaining cycles

    def _build_next_b0(self) -> bytes:
        """Build the next B0 instruction from current state (V3)."""
        seq = 0
        strength_mode = 0
        sa = 0
        sb = 0

        # Handle strength changes (only if not awaiting response)
        if self.state._awaiting_seq is None:
            # A channel
            if self.state._absolute_a is not None:
                mode_a = STRENGTH_ABSOLUTE
                sa = self.state._absolute_a
                self.state._absolute_a = None
                self.state._seq = (self.state._seq % 15) + 1
                seq = self.state._seq
            elif self.state._pending_strength_a != 0:
                delta = self.state._pending_strength_a
                if delta > 0:
                    mode_a = STRENGTH_INCREASE
                    sa = delta
                else:
                    mode_a = STRENGTH_DECREASE
                    sa = -delta
                self.state._pending_strength_a = 0
                self.state._seq = (self.state._seq % 15) + 1
                seq = self.state._seq
            else:
                mode_a = STRENGTH_NONE

            # B channel
            if self.state._absolute_b is not None:
                mode_b = STRENGTH_ABSOLUTE
                sb = self.state._absolute_b
                self.state._absolute_b = None
                if seq == 0:
                    self.state._seq = (self.state._seq % 15) + 1
                    seq = self.state._seq
            elif self.state._pending_strength_b != 0:
                delta = self.state._pending_strength_b
                if delta > 0:
                    mode_b = STRENGTH_INCREASE
                    sb = delta
                else:
                    mode_b = STRENGTH_DECREASE
                    sb = -delta
                self.state._pending_strength_b = 0
                if seq == 0:
                    self.state._seq = (self.state._seq % 15) + 1
                    seq = self.state._seq
            else:
                mode_b = STRENGTH_NONE

            strength_mode = (mode_a << 2) | mode_b

            if seq > 0:
                self.state._awaiting_seq = seq
        else:
            mode_a = STRENGTH_NONE
            mode_b = STRENGTH_NONE

        # Wave data for A channel
        if self.state.wave_a:
            idx = self.state.wave_a_index
            frame = self.state.wave_a[idx]
            wave_freq_a = tuple(encode_frequency(f) for f in frame.freq)
            wave_int_a = frame.intensity
            self.state.wave_a, self.state.wave_a_index, self.state.wave_a_loop = (
                self._advance_wave(self.state.wave_a, idx, self.state.wave_a_loop)
            )
        else:
            wave_freq_a = WAVE_FREQ_ZERO
            wave_int_a = WAVE_INACTIVE

        # Wave data for B channel
        if self.state.wave_b:
            idx = self.state.wave_b_index
            frame = self.state.wave_b[idx]
            wave_freq_b = tuple(encode_frequency(f) for f in frame.freq)
            wave_int_b = frame.intensity
            self.state.wave_b, self.state.wave_b_index, self.state.wave_b_loop = (
                self._advance_wave(self.state.wave_b, idx, self.state.wave_b_loop)
            )
        else:
            wave_freq_b = WAVE_FREQ_ZERO
            wave_int_b = WAVE_INACTIVE

        return build_b0(
            seq=seq,
            strength_mode=strength_mode,
            strength_a=sa,
            strength_b=sb,
            wave_freq_a=wave_freq_a,
            wave_int_a=wave_int_a,
            wave_freq_b=wave_freq_b,
            wave_int_b=wave_int_b,
        )

    async def _b0_loop(self) -> None:
        """100ms periodic loop to send B0 instructions (V3)."""
        while not self._stop_event.is_set():
            try:
                if self._client and self._client.is_connected:
                    data = self._build_next_b0()
                    await self._client.write_gatt_char(WRITE_UUID, data)
                else:
                    break
            except Exception as e:
                logger.error("B0 loop error: %s", e)
                break
            await asyncio.sleep(0.1)

        if self.state.connected:
            self.state.connected = False
            logger.warning("Connection lost in B0 loop")

    # --- V2 internal ---

    def _on_notify_v2(self, _sender: int, data: bytearray) -> None:
        """Handle PWM_AB2 notifications from a V2 device."""
        result = parse_v2_pwm_ab2(bytes(data))
        if result:
            self.state.strength_a = v2_strength_to_user(result["strength_a"])
            self.state.strength_b = v2_strength_to_user(result["strength_b"])
            logger.debug(
                "V2 AB2 notify: A=%d B=%d (raw)",
                result["strength_a"],
                result["strength_b"],
            )

    def _resolve_v2_strength(self, channel: str) -> int:
        """Compute effective user-facing strength for a V2 channel, consuming pending changes."""
        if channel == "A":
            limit = self.state.limit_a
            if self.state._absolute_a is not None:
                target = self.state._absolute_a
                self.state._absolute_a = None
            else:
                target = self.state.strength_a + self.state._pending_strength_a
                self.state._pending_strength_a = 0
        else:
            limit = self.state.limit_b
            if self.state._absolute_b is not None:
                target = self.state._absolute_b
                self.state._absolute_b = None
            else:
                target = self.state.strength_b + self.state._pending_strength_b
                self.state._pending_strength_b = 0
        return max(STRENGTH_MIN, min(limit, target))

    def _get_v2_wave_bytes(self, channel: str) -> bytes:
        """Get the 3-byte V2 waveform packet for the current frame of a channel."""
        if channel == "A":
            wave = self.state.wave_a
        else:
            wave = self.state.wave_b

        if not wave:
            return build_v2_pwm_wave(10, 0)  # zero-intensity: no stimulation

        if channel == "A":
            idx = self.state.wave_a_index
            loop = self.state.wave_a_loop
        else:
            idx = self.state.wave_b_index
            loop = self.state.wave_b_loop

        frame = wave[idx]
        period_ms = frame.freq[0]
        intensity_pct = frame.intensity[0]

        new_wave, new_idx, new_loop = self._advance_wave(wave, idx, loop)
        if channel == "A":
            self.state.wave_a = new_wave
            self.state.wave_a_index = new_idx
            self.state.wave_a_loop = new_loop
        else:
            self.state.wave_b = new_wave
            self.state.wave_b_index = new_idx
            self.state.wave_b_loop = new_loop

        return build_v2_pwm_wave(period_ms, intensity_pct)

    async def _v2_write_once(self) -> None:
        """Write one tick of V2 control data (strength + waveforms)."""
        sa_user = self._resolve_v2_strength("A")
        sb_user = self._resolve_v2_strength("B")

        ab2 = build_v2_pwm_ab2(
            v2_strength_from_user(sa_user),
            v2_strength_from_user(sb_user),
        )
        await self._client.write_gatt_char(V2_PWM_AB2_UUID, ab2)

        # PWM_B34 carries channel A waveform; PWM_A34 carries channel B waveform
        await self._client.write_gatt_char(V2_PWM_B34_UUID, self._get_v2_wave_bytes("A"))
        await self._client.write_gatt_char(V2_PWM_A34_UUID, self._get_v2_wave_bytes("B"))

    async def _v2_loop(self) -> None:
        """100ms periodic loop to send V2 control packets."""
        while not self._stop_event.is_set():
            try:
                if self._client and self._client.is_connected:
                    await self._v2_write_once()
                else:
                    break
            except Exception as e:
                logger.error("V2 loop error: %s", e)
                break
            await asyncio.sleep(0.1)

        if self.state.connected:
            self.state.connected = False
            logger.warning("Connection lost in V2 loop")

    # --- Status ---

    def get_status(self) -> dict:
        """Get current device status."""
        return {
            "connected": self.state.connected,
            "version": self.state.version,
            "address": self.state.address,
            "strength_a": self.state.strength_a,
            "strength_b": self.state.strength_b,
            "limit_a": self.state.limit_a,
            "limit_b": self.state.limit_b,
            "battery": self.state.battery,
            "wave_a_active": len(self.state.wave_a) > 0,
            "wave_b_active": len(self.state.wave_b) > 0,
        }


class DeviceManager:
    """Manages multiple concurrent device connections (Coyote and Lovense) via aliases."""

    def __init__(self) -> None:
        self._devices: list[CoyoteDevice | LovenseDevice] = []
        self._alias_map: dict[str, list[tuple[CoyoteDevice | LovenseDevice, str]]] = {}
        self._session_start: datetime | None = None
        self._alias_last_activity: dict[str, datetime] = {}

    async def scan(self, timeout: float = 5.0) -> list[dict]:
        """Scan for nearby Coyote (V2/V3) and Lovense devices.

        Returns list of dicts with name, address, and version/type.
        """
        devices = await BleakScanner.discover(timeout=timeout)
        results = []
        for d in devices:
            name = d.name or ""
            if name.startswith(DEVICE_NAME_PREFIX):
                results.append({"name": name, "address": d.address, "version": "v3"})
            elif name == V2_DEVICE_NAME:
                results.append({"name": name, "address": d.address, "version": "v2"})
            elif is_lovense_name(name):
                results.append({"name": name, "address": d.address, "type": "lovense"})
        return results

    async def connect(
        self, address: str, alias_a: str, alias_b: str | None = None
    ) -> tuple[str, str | None]:
        """Connect to a Coyote or Lovense device and assign channel alias(es).

        Args:
            address: BLE address from scan results.
            alias_a: Alias for channel A (Coyote) or the single vibration channel (Lovense).
            alias_b: Alias for channel B — required for Coyote, ignored for Lovense.

        Returns:
            (alias_a, alias_b) — alias_b is None for Lovense devices.
        """
        if not alias_a:
            raise ValueError("alias_a must be a non-empty string.")

        ble_device = await BleakScanner.find_device_by_address(address, timeout=10.0)
        if ble_device is None:
            raise ValueError(f"Device {address} not found. Make sure it is powered on.")

        name = ble_device.name or ""

        if is_lovense_name(name):
            dev = LovenseDevice()
            await dev.connect(address, name=name)
            self._devices.append(dev)
            self._alias_map.setdefault(alias_a, []).append((dev, "V"))
            logger.info("Registered Lovense alias '%s' for %s", alias_a, address)
            return alias_a, None

        # Coyote path
        if not alias_b:
            raise ValueError("alias_b is required for Coyote devices (two channels).")
        if name.startswith(DEVICE_NAME_PREFIX):
            version = "v3"
        elif name == V2_DEVICE_NAME:
            version = "v2"
        else:
            raise ValueError(
                f"Unrecognised device name '{name}' at {address}. "
                "Expected a DG-Lab Coyote or Lovense device."
            )

        dev = CoyoteDevice()
        await dev.connect(address, version=version)

        self._devices.append(dev)
        self._alias_map.setdefault(alias_a, []).append((dev, "A"))
        self._alias_map.setdefault(alias_b, []).append((dev, "B"))

        logger.info("Registered aliases '%s' (A) and '%s' (B) for %s", alias_a, alias_b, address)
        return alias_a, alias_b

    async def disconnect_all(self) -> None:
        """Disconnect all connected devices and clear all aliases."""
        await asyncio.gather(
            *[dev.disconnect() for dev in self._devices],
            return_exceptions=True,
        )
        self._devices.clear()
        self._alias_map.clear()
        self._session_start = None
        self._alias_last_activity.clear()

    def _resolve(self, alias: str) -> list[tuple[CoyoteDevice | LovenseDevice, str]]:
        """Resolve an alias to a list of (device, channel) pairs.

        Raises ValueError if the alias is unknown or all matching devices are disconnected.
        """
        entries = self._alias_map.get(alias)
        if not entries:
            known = list(self._alias_map.keys())
            raise ValueError(
                f"Unknown alias '{alias}'. "
                f"Connected aliases: {known if known else 'none'}"
            )
        active = [
            (dev, ch) for dev, ch in entries
            if (dev.state.connected if isinstance(dev, (CoyoteDevice, LovenseDevice)) else False)
        ]
        if not active:
            raise ValueError(f"Alias '{alias}' exists but all its devices are disconnected.")
        return active

    def _update_activity(self, alias: str) -> None:
        now = datetime.now()
        if self._session_start is None:
            self._session_start = now
        self._alias_last_activity[alias] = now

    def set_strength(self, alias: str, pct: int) -> None:
        """Set absolute strength for all Coyote channels with this alias (0–100%)."""
        entries = self._resolve(alias)
        coyote_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, CoyoteDevice)]
        if not coyote_pairs:
            raise ValueError(f"Alias '{alias}' has no connected Coyote device. Use vibrate() for Lovense.")
        raw = _pct_to_raw(pct)
        for dev, ch in coyote_pairs:
            dev.set_strength(ch, raw)

    def adjust_strength(self, alias: str, delta_pct: int) -> None:
        """Increase or decrease strength for all Coyote channels with this alias (delta in %)."""
        entries = self._resolve(alias)
        coyote_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, CoyoteDevice)]
        if not coyote_pairs:
            raise ValueError(f"Alias '{alias}' has no connected Coyote device. Use vibrate() for Lovense.")
        raw_delta = delta_pct * 2
        for dev, ch in coyote_pairs:
            dev.add_strength(ch, raw_delta)

    async def set_strength_limit(self, alias: str, limit_pct: int) -> None:
        """Set strength soft limit for all Coyote channels with this alias (0–100%)."""
        entries = self._resolve(alias)
        coyote_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, CoyoteDevice)]
        if not coyote_pairs:
            raise ValueError(f"Alias '{alias}' has no connected Coyote device.")
        raw = _pct_to_raw(limit_pct)
        for dev, ch in coyote_pairs:
            if ch == "A":
                await dev.set_strength_limit(raw, dev.state.limit_b)
            else:
                await dev.set_strength_limit(dev.state.limit_a, raw)

    def send_wave(self, alias: str, frames: list[WaveFrame], loop: int = 0) -> None:
        """Send waveform frames to all Coyote channels with this alias."""
        entries = self._resolve(alias)
        coyote_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, CoyoteDevice)]
        if not coyote_pairs:
            raise ValueError(f"Alias '{alias}' has no connected Coyote device. Use vibrate() for Lovense.")
        for dev, ch in coyote_pairs:
            dev.send_wave(ch, frames, loop=loop)
        self._update_activity(alias)

    def stop_wave(self, alias: str | None = None) -> None:
        """Stop waveform on Coyote channels matching alias, or all channels if alias is None."""
        if alias is None:
            for dev in self._devices:
                if isinstance(dev, CoyoteDevice):
                    dev.stop_wave(None)
        else:
            entries = self._resolve(alias)
            coyote_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, CoyoteDevice)]
            if not coyote_pairs:
                raise ValueError(f"Alias '{alias}' has no connected Coyote device.")
            for dev, ch in coyote_pairs:
                dev.stop_wave(ch)

    async def vibrate(self, alias: str, pct: int) -> None:
        """Set vibration strength on all Lovense devices with this alias (0–100%)."""
        entries = self._resolve(alias)
        lovense_pairs = [(dev, ch) for dev, ch in entries if isinstance(dev, LovenseDevice)]
        if not lovense_pairs:
            raise ValueError(f"Alias '{alias}' has no connected Lovense device.")
        for dev, _ in lovense_pairs:
            await dev.set_vibration(pct)
        self._update_activity(alias)

    def get_all_status(self) -> dict:
        """Return alias-keyed status for all connected channels."""
        aliases: dict[str, list[dict]] = {}
        for alias, entries in self._alias_map.items():
            last_act = self._alias_last_activity.get(alias)
            last_activity = humanize.naturaltime(last_act) if last_act else None
            channel_statuses = []
            for dev, ch in entries:
                if isinstance(dev, LovenseDevice):
                    channel_statuses.append({
                        "device_type": "lovense",
                        "strength_pct": dev.state.strength,
                        "battery": dev.state.battery,
                        "connected": dev.state.connected,
                        "last_activity": last_activity,
                    })
                else:
                    s = dev.state
                    if ch == "A":
                        strength_raw = s.strength_a
                        limit_raw = s.limit_a
                        wave_active = len(s.wave_a) > 0
                    else:
                        strength_raw = s.strength_b
                        limit_raw = s.limit_b
                        wave_active = len(s.wave_b) > 0
                    channel_statuses.append({
                        "device_type": "coyote",
                        "strength_pct": _raw_to_pct(strength_raw),
                        "limit_pct": _raw_to_pct(limit_raw),
                        "wave_active": wave_active,
                        "battery": s.battery,
                        "connected": s.connected,
                        "last_activity": last_activity,
                    })
            aliases[alias] = channel_statuses

        return {
            "connected_devices": sum(1 for d in self._devices if d.state.connected),
            "aliases": aliases,
            "session": {
                "running_since": humanize.naturaltime(self._session_start) if self._session_start else None,
            },
        }
