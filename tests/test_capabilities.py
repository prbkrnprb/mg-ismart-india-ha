"""Tests for vehicle model capability discovery."""

from mg_ismart_india.capabilities import discover_capabilities


def test_discovers_windsor_controls_from_model_configuration() -> None:
    raw = {
        "vehicleModelConfiguration": [
            {"itemCode": "S61", "itemValue": "1"},
            {"itemCode": "T11", "itemValue": "1"},
            {"itemCode": "S35", "itemValue": "0"},
            {"itemCode": "BOOT", "itemValue": "1"},
            {"itemCode": "WINDOW", "itemValue": "1100"},
            {"itemCode": "HeatedSeat", "itemValue": "0"},
        ]
    }

    capabilities = discover_capabilities(raw, [])

    assert capabilities.climate is True
    assert capabilities.door_lock is True
    assert capabilities.find_my_car is True
    assert capabilities.tailgate is True
    assert capabilities.window_param_ids == (9, 10)
    assert capabilities.sunroof is False
    assert capabilities.heated_seats is False


def test_feature_flags_can_enable_climate_without_model_flag() -> None:
    capabilities = discover_capabilities(
        {"vehicleModelConfiguration": []},
        [{"featureId": 2, "featureName": "AC Setting", "isSupported": True}],
    )

    assert capabilities.climate is True
