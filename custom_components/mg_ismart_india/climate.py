"""Remote climate control for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import MgIndiaClient
from .capabilities import discover_capabilities
from .const import DOMAIN
from .coordinator import MgIndiaDataUpdateCoordinator
from .entity import MgIndiaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the MG iSmart India climate entity."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    capabilities = discover_capabilities(
        coordinator.data.vehicle.raw, coordinator.data.features
    )
    if capabilities.climate:
        async_add_entities([MgIndiaClimate(coordinator, data["client"])])


class MgIndiaClimate(MgIndiaEntity, ClimateEntity):
    """Remote vehicle climate limited to validated on/off commands."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature = 22

    def __init__(
        self, coordinator: MgIndiaDataUpdateCoordinator, client: MgIndiaClient
    ) -> None:
        super().__init__(coordinator, "climate", "Climate")
        self._client = client

    @property
    def available(self) -> bool:
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        return (
            super().available and self._client.has_control_pin and capabilities.climate
        )

    @property
    def current_temperature(self) -> int | None:
        status = self.coordinator.data.status
        return status.interior_temperature if status is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        status = self.coordinator.data.status
        if status is not None and status.climate_running:
            return HVACMode.COOL
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self._attr_hvac_modes:
            return
        await self._client.control_climate(turn_on=hvac_mode == HVACMode.COOL)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
