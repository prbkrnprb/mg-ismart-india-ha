# MG iSmart India

Home Assistant custom integration for MG iSmart India connected vehicles.

It authenticates against the India MG iSmart cloud, lists vehicles, decodes the
India-specific TAP protocol 513 vehicle status response, and exposes remote
controls supported by each vehicle's model configuration.

## Current Entities

- Model
- Series
- Model year
- Platform
- Supported feature count
- Last update
- Vehicle status time
- Last vehicle activity
- Activation status
- AC support
- Battery level
- Remaining range
- Odometer
- Auxiliary battery voltage
- Interior and exterior temperature
- Lock state
- Door, boot, bonnet, and window state
- Remote climate and CAN bus activity
- Climate on/off
- Door lock/unlock
- Supported windows
- Sunroof when fitted
- Find-my-car horn and lights
- Tailgate release when supported
- Front heated-seat levels when fitted

## Installation

Copy `custom_components/mg_ismart_india` into your Home Assistant
`custom_components` directory, restart Home Assistant, then add the integration
from **Settings > Devices & services**.

## Notes

- Use the 10-digit India mobile number associated with the MG iSmart account.
- Remote controls require the vehicle-control PIN. New installations verify it
  during setup. Existing installations can add or replace it using the
  integration's **Configure** action. Only a one-way hash is stored.
- Control entities are created dynamically from the vehicle's reported model
  configuration; unsupported hardware is not exposed.
- Vehicle location is intentionally not exposed.
- Tyre pressure and charging details remain unavailable until their separate
  India encodings are validated.
- This project is independent from the generic MG SAIC integration because the
  India cloud uses a different TAP login and gateway signing flow.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for ASN.1 schema
attribution.
