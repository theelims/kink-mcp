"""Tests for new DeviceManager methods."""

import pytest
from unittest.mock import AsyncMock


def _make_mock_device(address: str, connected: bool = True, battery: int = 80,
                      limit_a: int = 200, limit_b: int = 200):
    """Create a minimal mock of CoyoteDevice or LovenseDevice."""
    class MockState:
        pass

    state = MockState()
    state.address = address
    state.connected = connected
    state.battery = battery
    state.limit_a = limit_a
    state.limit_b = limit_b

    class MockDevice:
        pass

    dev = MockDevice()
    dev.state = state
    dev.disconnect = AsyncMock()
    return dev


def _make_manager():
    from kink_mcp.device import DeviceManager
    return DeviceManager()


# --- get_device_list ---

def test_get_device_list_empty():
    m = _make_manager()
    assert m.get_device_list() == []


def test_get_device_list_shows_connected_device():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC", connected=True, battery=75)
    m._devices.append(dev)
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 40,
    }
    result = m.get_device_list()
    assert len(result) == 1
    assert result[0]["connected"] is True
    assert result[0]["battery"] == 75
    assert result[0]["alias_a"] == "left"


def test_get_device_list_shows_offline_device():
    m = _make_manager()
    # No device in _devices, but meta exists (failed reconnect)
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 40,
    }
    result = m.get_device_list()
    assert len(result) == 1
    assert result[0]["connected"] is False
    assert result[0]["battery"] == -1
    assert result[0]["limit_a"] == 50


# --- add_offline_device ---

def test_add_offline_device():
    m = _make_manager()
    m.add_offline_device({
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 60, "limit_b_pct": 55,
    })
    assert "AA:BB:CC" in m._device_meta
    assert m._device_meta["AA:BB:CC"]["alias_a"] == "left"


def test_add_offline_device_does_not_duplicate():
    m = _make_manager()
    meta = {"address": "AA:BB:CC", "name": "X", "device_type": "coyote",
            "version": "v3", "alias_a": "a", "alias_b": "b",
            "limit_a_pct": 50, "limit_b_pct": 50}
    m.add_offline_device(meta)
    m.add_offline_device(meta)
    assert len(m._device_meta) == 1


# --- disconnect_one ---

@pytest.mark.asyncio
async def test_disconnect_one_removes_device_and_aliases():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC")
    m._devices.append(dev)
    m._alias_map["left"] = [(dev, "A")]
    m._alias_map["right"] = [(dev, "B")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }

    await m.disconnect_one("AA:BB:CC")

    dev.disconnect.assert_awaited_once()
    assert dev not in m._devices
    assert "AA:BB:CC" not in m._device_meta
    assert "left" not in m._alias_map
    assert "right" not in m._alias_map


@pytest.mark.asyncio
async def test_disconnect_one_unknown_address_raises():
    m = _make_manager()
    with pytest.raises(ValueError, match="No device"):
        await m.disconnect_one("FF:FF:FF")


@pytest.mark.asyncio
async def test_disconnect_one_keeps_shared_alias_for_other_device():
    """If two devices share an alias, disconnecting one device keeps the alias for the other."""
    m = _make_manager()
    dev1 = _make_mock_device("AA:BB:CC")
    dev2 = _make_mock_device("DD:EE:FF")
    m._devices.extend([dev1, dev2])
    m._alias_map["shared"] = [(dev1, "A"), (dev2, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3", "device_type": "coyote",
        "version": "v3", "alias_a": "shared", "alias_b": "other",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m._device_meta["DD:EE:FF"] = {
        "address": "DD:EE:FF", "name": "Coyote V3", "device_type": "coyote",
        "version": "v3", "alias_a": "shared", "alias_b": "other2",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }

    await m.disconnect_one("AA:BB:CC")

    assert "shared" in m._alias_map
    assert len(m._alias_map["shared"]) == 1
    assert m._alias_map["shared"][0][0] is dev2


# --- rename_alias ---

def test_rename_alias_updates_map_and_meta():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC")
    m._alias_map["old"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "X", "device_type": "coyote",
        "version": "v3", "alias_a": "old", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }

    m.rename_alias("old", "new_name")

    assert "new_name" in m._alias_map
    assert "old" not in m._alias_map
    assert m._device_meta["AA:BB:CC"]["alias_a"] == "new_name"


def test_rename_alias_noop_when_same():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC")
    m._alias_map["same"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "X", "device_type": "coyote",
        "version": "v3", "alias_a": "same", "alias_b": "b",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.rename_alias("same", "same")
    assert "same" in m._alias_map


def test_rename_alias_unknown_raises():
    m = _make_manager()
    with pytest.raises(ValueError, match="Unknown alias"):
        m.rename_alias("ghost", "new")


def test_rename_alias_transfers_activity_timestamp():
    from datetime import datetime
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC")
    m._alias_map["old"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "X", "device_type": "coyote",
        "version": "v3", "alias_a": "old", "alias_b": "b",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    ts = datetime(2026, 1, 1)
    m._alias_last_activity["old"] = ts

    m.rename_alias("old", "new_name")

    assert m._alias_last_activity.get("new_name") == ts
    assert "old" not in m._alias_last_activity


# --- forget_device ---

def test_forget_device_removes_meta():
    m = _make_manager()
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta


def test_forget_device_unknown_raises():
    m = _make_manager()
    with pytest.raises(ValueError, match="Unknown device"):
        m.forget_device("FF:FF:FF")


def test_forget_device_connected_raises():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC", connected=True)
    m._devices.append(dev)
    m._alias_map["left"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    with pytest.raises(ValueError, match="Cannot forget a connected"):
        m.forget_device("AA:BB:CC")


def test_forget_device_cleans_aliases():
    m = _make_manager()
    m._alias_map["left"] = []
    m._alias_map["right"] = []
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert "left" not in m._alias_map
    assert "right" not in m._alias_map


def test_forget_device_keeps_shared_alias_for_other_device():
    m = _make_manager()
    dev = _make_mock_device("DD:EE:FF", connected=True)
    m._devices.append(dev)
    m._alias_map["shared"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "shared", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m._device_meta["DD:EE:FF"] = {
        "address": "DD:EE:FF", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "shared", "alias_b": "other",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert "shared" in m._alias_map
    assert len(m._alias_map["shared"]) == 1


def test_forget_device_removes_disconnected_dev_object():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC", connected=False)
    m._devices.append(dev)
    m._alias_map["left"] = [(dev, "A")]
    m._alias_map["right"] = [(dev, "B")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert dev not in m._devices
    assert "left" not in m._alias_map
    assert "right" not in m._alias_map
