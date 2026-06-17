"""Vehicle capability discovery from MG India model configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MgIndiaCapabilities:
    """Remote controls supported by a specific vehicle."""

    climate: bool = False
    door_lock: bool = False
    find_my_car: bool = False
    tailgate: bool = False
    sunroof: bool = False
    heated_seats: bool = False
    window_param_ids: tuple[int, ...] = ()


def discover_capabilities(
    vehicle_raw: dict[str, Any], features: list[dict[str, Any]]
) -> MgIndiaCapabilities:
    """Build control capabilities from model configuration and feature flags."""

    configuration = {
        str(item.get("itemCode")): str(item.get("itemValue", ""))
        for item in vehicle_raw.get("vehicleModelConfiguration", [])
        if isinstance(item, dict) and item.get("itemCode")
    }
    feature_ids = {
        item.get("featureId")
        for item in features
        if isinstance(item, dict) and item.get("isSupported") is True
    }
    remote_control = _enabled(configuration.get("S61"))
    window_mask = configuration.get("WINDOW", "")
    window_param_ids = tuple(
        param_id
        for supported, param_id in zip(window_mask, (9, 10, 11, 12), strict=False)
        if supported == "1"
    )
    return MgIndiaCapabilities(
        climate=_enabled(configuration.get("T11")) or 2 in feature_ids,
        door_lock=remote_control,
        find_my_car=remote_control,
        tailgate=remote_control and _enabled(configuration.get("BOOT")),
        sunroof=remote_control and _enabled(configuration.get("S35")),
        heated_seats=remote_control and _enabled(configuration.get("HeatedSeat")),
        window_param_ids=window_param_ids if remote_control else (),
    )


def _enabled(value: str | None) -> bool:
    return value not in (None, "", "0")
