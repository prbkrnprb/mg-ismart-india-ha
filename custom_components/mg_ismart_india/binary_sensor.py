"""Binary sensors for MG iSmart India."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import MgIndiaSnapshot
from .const import DOMAIN
from .coordinator import MgIndiaDataUpdateCoordinator
from .entity import MgIndiaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up MG iSmart India binary sensors."""

    coordinator: MgIndiaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        [
            MgIndiaBinarySensor(
                coordinator,
                "active",
                "Activated",
                lambda data: data.vehicle.is_active,
                device_class=BinarySensorDeviceClass.CONNECTIVITY,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "ac_supported",
                "AC Supported",
                lambda data: feature_supported(data, "AC Setting"),
            ),
            MgIndiaBinarySensor(
                coordinator,
                "lock",
                "Lock",
                lock_is_unlocked,
                device_class=BinarySensorDeviceClass.LOCK,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "driver_door",
                "Driver Door",
                lambda data: status_value(data, "driver_door_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "passenger_door",
                "Passenger Door",
                lambda data: status_value(data, "passenger_door_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "rear_left_door",
                "Rear Left Door",
                lambda data: status_value(data, "rear_left_door_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "rear_right_door",
                "Rear Right Door",
                lambda data: status_value(data, "rear_right_door_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "boot",
                "Boot",
                lambda data: status_value(data, "boot_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "bonnet",
                "Bonnet",
                lambda data: status_value(data, "bonnet_open"),
                device_class=BinarySensorDeviceClass.DOOR,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "driver_window",
                "Driver Window",
                lambda data: status_value(data, "driver_window_open"),
                device_class=BinarySensorDeviceClass.WINDOW,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "passenger_window",
                "Passenger Window",
                lambda data: status_value(data, "passenger_window_open"),
                device_class=BinarySensorDeviceClass.WINDOW,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "rear_left_window",
                "Rear Left Window",
                lambda data: status_value(data, "rear_left_window_open"),
                device_class=BinarySensorDeviceClass.WINDOW,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "rear_right_window",
                "Rear Right Window",
                lambda data: status_value(data, "rear_right_window_open"),
                device_class=BinarySensorDeviceClass.WINDOW,
            ),
            MgIndiaBinarySensor(
                coordinator,
                "climate_running",
                "Climate Running",
                lambda data: status_value(data, "climate_running"),
            ),
            MgIndiaBinarySensor(
                coordinator,
                "can_bus_active",
                "CAN Bus Active",
                lambda data: status_value(data, "can_bus_active"),
            ),
            MgIndiaBinarySensor(
                coordinator,
                "charging",
                "Charging",
                lambda data: status_value(data, "charging"),
                device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
            ),
        ]
    )


class MgIndiaBinarySensor(MgIndiaEntity, BinarySensorEntity):
    """Generic MG iSmart India binary sensor."""

    def __init__(
        self,
        coordinator: MgIndiaDataUpdateCoordinator,
        key: str,
        name: str,
        value_fn: Callable[[MgIndiaSnapshot], bool | None],
        *,
        device_class: BinarySensorDeviceClass | None = None,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._value_fn = value_fn
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        return self._value_fn(self.coordinator.data)


def feature_supported(data: MgIndiaSnapshot, feature_name: str) -> bool | None:
    for feature in data.features:
        if feature.get("featureName") == feature_name:
            return bool(feature.get("isSupported"))
    return None


def status_value(data: MgIndiaSnapshot, attribute: str) -> bool | None:
    return getattr(data.status, attribute) if data.status is not None else None


def lock_is_unlocked(data: MgIndiaSnapshot) -> bool | None:
    locked = status_value(data, "locked")
    return not locked if locked is not None else None
