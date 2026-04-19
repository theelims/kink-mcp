"""BLE device support for Lovense vibration toys."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient, BLEDevice

logger = logging.getLogger(__name__)

LOVENSE_NAME_PREFIXES = ("LVS-", "LOVE-")

# Gen 2 — Nordic UART (most current devices: Domi, Hush 2, Lush 3, Ferri, …)
UART_SERVICE     = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
UART_NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Gen 1 — legacy UUID set (original Lush / Hush 1)
GEN1_SERVICE     = "0000fff0-0000-1000-8000-00805f9b34fb"
GEN1_WRITE_UUID  = "0000fff2-0000-1000-8000-00805f9b34fb"
GEN1_NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# Gen 3 — variable service UUID, constant suffix (Gush, newer devices)
# Pattern: XY300001-00ZW-4bd4-bbd5-a6920e4c5653
# TX (write):  XY300002-00ZW-4bd4-bbd5-a6920e4c5653
# RX (notify): XY300003-00ZW-4bd4-bbd5-a6920e4c5653
GEN3_UUID_SUFFIX = "4bd4-bbd5-a6920e4c5653"

VIBRATE_MAX = 20  # Lovense internal scale: 0–20


def is_lovense_name(name: str) -> bool:
    return any(name.startswith(p) for p in LOVENSE_NAME_PREFIXES)


def lovense_model(name: str) -> str:
    """Extract the model identifier from a Lovense BLE name (e.g. 'LVS-Domi' → 'Domi')."""
    for prefix in LOVENSE_NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


@dataclass
class LovenseState:
    connected: bool = False
    address: str = ""
    name: str = ""
    battery: int = -1
    strength: int = 0  # 0–100 %


class LovenseDevice:
    """Manages BLE connection and vibration control for Lovense toys."""

    def __init__(self) -> None:
        self.state = LovenseState()
        self._client: BleakClient | None = None
        self._write_uuid: str = UART_WRITE_UUID

    def _on_disconnect(self, _client: BleakClient) -> None:
        if self.state.connected:
            logger.warning("Lovense %s disconnected unexpectedly", self.state.name)
        self.state.connected = False

    async def connect(self, address: BLEDevice | str, name: str = "") -> None:
        """Connect to a Lovense device.

        Tries Gen 2 UART first; falls back to Gen 1 UUIDs if the service is absent.
        Pass a BLEDevice object (preferred on Windows) or a string address.
        """
        self._client = BleakClient(
            address,
            disconnected_callback=self._on_disconnect,
            timeout=15.0,
        )
        await self._client.connect()

        if not self._client.is_connected:
            raise RuntimeError(f"Failed to connect to {address}")

        # Determine which UUID set to use
        services = [str(s.uuid).lower() for s in self._client.services]
        gen3_svc = next((s for s in services if s.endswith(GEN3_UUID_SUFFIX)), None)
        if UART_SERVICE.lower() in services:
            self._write_uuid = UART_WRITE_UUID
            notify_uuid = UART_NOTIFY_UUID
            logger.debug("Lovense: Gen 2 (UART) detected")
        elif gen3_svc is not None:
            # Derive TX/RX from service UUID: position 7 changes 1→2 (TX) or 1→3 (RX)
            self._write_uuid = gen3_svc[:7] + "2" + gen3_svc[8:]
            notify_uuid      = gen3_svc[:7] + "3" + gen3_svc[8:]
            logger.debug("Lovense: Gen 3 detected (service=%s)", gen3_svc)
        elif GEN1_SERVICE.lower() in services:
            self._write_uuid = GEN1_WRITE_UUID
            notify_uuid = GEN1_NOTIFY_UUID
            logger.debug("Lovense: Gen 1 detected")
        else:
            logger.warning(
                "Lovense: No known service UUID found. Available services: %s. "
                "Defaulting to Gen 2 (UART).",
                services,
            )
            self._write_uuid = UART_WRITE_UUID
            notify_uuid = UART_NOTIFY_UUID

        try:
            await self._client.start_notify(notify_uuid, self._on_notify)
        except Exception as e:
            logger.warning("start_notify failed (%s); continuing without notifications", e)

        self.state.connected = True
        self.state.address = self._client.address
        self.state.name = name or self._client.address

        # Request battery level; response arrives asynchronously via _on_notify.
        # Poll for up to 2 s so the connect() response can report actual battery %.
        try:
            await self._send_raw("Battery;")
            for _ in range(20):
                await asyncio.sleep(0.1)
                if self.state.battery >= 0:
                    break
        except Exception:
            logger.debug("Could not request battery level")

        logger.info("Lovense connected to %s (%s)", self.state.name, address)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self.set_vibration(0)
            except Exception:
                pass
            await self._client.disconnect()
        self.state = LovenseState()
        self._client = None
        logger.info("Lovense disconnected")

    async def set_vibration(self, pct: int) -> None:
        """Set vibration intensity (0–100 %)."""
        pct = max(0, min(100, pct))
        level = round(pct * VIBRATE_MAX / 100)
        await self._send_raw(f"Vibrate:{level};")
        self.state.strength = pct

    def get_status(self) -> dict:
        return {
            "device_type": "lovense",
            "connected": self.state.connected,
            "address": self.state.address,
            "name": self.state.name,
            "battery": self.state.battery,
            "strength_pct": self.state.strength,
        }

    # --- Internal ---

    async def _send_raw(self, cmd: str) -> None:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected.")
        await self._client.write_gatt_char(
            self._write_uuid, cmd.encode(), response=False
        )
        logger.debug("Lovense TX: %s", cmd.rstrip())

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        msg = data.decode(errors="ignore").strip().rstrip(";")
        logger.debug("Lovense RX: %s", msg)
        if msg.isdigit():
            self.state.battery = int(msg)
