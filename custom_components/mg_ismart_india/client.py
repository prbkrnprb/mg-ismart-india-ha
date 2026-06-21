"""MG iSmart India cloud client."""

from __future__ import annotations

import asyncio
from binascii import unhexlify
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import httpx

from .bitcodec import BitReader, read_fixed_7bit_string, set_bits, set_fixed_7bit_string
from .const import (
    GATEWAY_BASE_URL,
    CONTROL_POLL_ATTEMPTS,
    CONTROL_POLL_DELAY,
    STATUS_POLL_ATTEMPTS,
    STATUS_POLL_DELAY,
    TAP_LOGIN_URL,
    TAP_STATUS_URL,
    USER_AGENT,
)
from .tap_codec import TapCodecError, decode_status_response, encode_status_request
from .tap_codec import (
    decode_control_response,
    decode_pin_verification_response,
    encode_control_request,
    encode_pin_verification_request,
)

LOGGER = logging.getLogger(__package__)

LOGIN_DISPATCHER_TEMPLATE_HEX = (
    "11005600882c60c183060c183060c183060c183060c183060c183060c183060c183060c183"
    "060c183060c183060c183060c1ab06200000000020200468acf134468acf1342468acf134"
    "2468acf1342000000000100a0"
)


class MgIndiaApiError(Exception):
    """Raised when the MG India API returns an error."""


@dataclass(frozen=True)
class MgIndiaVehicle:
    """Vehicle metadata returned by the India gateway."""

    vin: str
    brand_name: str | None = None
    model_name: str | None = None
    model_year: str | int | None = None
    series: str | None = None
    is_active: bool | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class MgIndiaGpsPosition:
    """GPS position from the TAP status response."""

    latitude: float | None
    longitude: float | None
    altitude: int | None
    heading: int | None
    speed: float | None
    gps_fix: str | None


@dataclass(frozen=True)
class MgIndiaVehicleStatus:
    """Normalized read-only telemetry returned by the TAP status API."""

    status_time: int | None
    last_vehicle_activity: int | None
    battery_percent: int | None
    range_km: float | None
    odometer_km: float | None
    auxiliary_battery_voltage: float | None
    interior_temperature: int | None
    exterior_temperature: int | None
    locked: bool | None
    driver_door_open: bool | None
    passenger_door_open: bool | None
    rear_left_door_open: bool | None
    rear_right_door_open: bool | None
    boot_open: bool | None
    bonnet_open: bool | None
    driver_window_open: bool | None
    passenger_window_open: bool | None
    rear_left_window_open: bool | None
    rear_right_window_open: bool | None
    climate_running: bool | None
    sunroof_open: bool | None
    can_bus_active: bool | None
    charging: bool | None
    engine_status: int | None
    power_mode: int | None
    gps: MgIndiaGpsPosition | None


@dataclass(frozen=True)
class MgIndiaSnapshot:
    """Read-only data used by Home Assistant entities."""

    vehicle: MgIndiaVehicle
    user_language: str | None
    platform: str | None
    features: list[dict[str, Any]]
    service_subscription: dict[str, Any] | None
    co2_info: dict[str, Any] | None
    co2_supplement: dict[str, Any] | None
    status: MgIndiaVehicleStatus | None
    last_update: float


class MgIndiaClient:
    """Client for MG iSmart India TAP login and gateway APIs."""

    def __init__(
        self,
        phone: str,
        password: str,
        *,
        vin: str | None = None,
        pin_hash: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._phone = normalize_phone(phone)
        self._password = password
        self._vin = vin
        self._pin_hash = pin_hash
        self._http = http_client or httpx.AsyncClient(timeout=30)
        self._owns_http = http_client is None
        self._token: str | None = None
        self._user_id: str | None = None
        self._device_id = make_device_id(self._phone)
        self._last_vehicle_status: MgIndiaVehicleStatus | None = None
        self._heated_seat_levels = {"driver": 0, "passenger": 0}

    @property
    def vin(self) -> str | None:
        return self._vin

    @property
    def has_control_pin(self) -> bool:
        return self._pin_hash is not None

    def heated_seat_level(self, side: str) -> int:
        """Return the last requested heated-seat level."""

        return self._heated_seat_levels[side]

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def login(self) -> None:
        """Authenticate and store a fresh gateway token/user id."""

        body = self._build_login_body()
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "text/plain",
            "Accept": "*/*",
            "Accept-Language": "en-US;q=1",
            "APP-SIGNATURE": tap_signature(body),
            "SIGNATURE": "1",
        }
        response = await self._http.post(TAP_LOGIN_URL, content=body, headers=headers)
        response.raise_for_status()
        dispatcher, app = decode_tap_response(response.text)
        if not app:
            raise MgIndiaApiError("Login did not return a token payload")
        self._token = decode_login_token(app)
        user_id = read_fixed_7bit_string(dispatcher, bit_offset=300, char_count=14)
        self._user_id = user_id.rjust(50, "0")

    async def vehicles(self) -> list[MgIndiaVehicle]:
        await self._ensure_login()
        payload = await self.gateway_get("/vehicle/userVinList")
        vin_list = payload.get("data", {}).get("vinList", [])
        vehicles = [parse_vehicle(item) for item in vin_list if isinstance(item, dict)]
        if self._vin is None and vehicles:
            self._vin = vehicles[0].vin
        return vehicles

    async def snapshot(self) -> MgIndiaSnapshot:
        await self._ensure_login()
        vehicles = await self.vehicles()
        vehicle = self._select_vehicle(vehicles)
        user_info = await self.gateway_get("/user/account/userInfo")
        feature_resp = await self.gateway_get(
            "/vehicle/feature/list",
            {"vin": hashlib.sha256(vehicle.vin.encode()).hexdigest()},
        )
        service_subscription = await self._gateway_get_optional(
            "/vehicle/service/subscription", {"vin": vehicle.vin}
        )
        co2_info = await self._gateway_get_optional(
            "/navi/vehicle/co2info", {"vin": vehicle.vin}
        )
        co2_supplement = await self._gateway_get_optional(
            "/navi/vehicle/co2info/supplementInfo", {"vin": vehicle.vin}
        )
        try:
            status = await self.vehicle_status(vehicle.vin)
            self._last_vehicle_status = status
        except (MgIndiaApiError, httpx.HTTPError) as err:
            LOGGER.warning("Unable to refresh MG vehicle telemetry: %s", err)
            status = self._last_vehicle_status
        data = feature_resp.get("data", {})
        return MgIndiaSnapshot(
            vehicle=vehicle,
            user_language=user_info.get("data", {}).get("userLanguageType"),
            platform=data.get("platform"),
            features=data.get("featureList", []) if isinstance(data, dict) else [],
            service_subscription=service_subscription,
            co2_info=co2_info,
            co2_supplement=co2_supplement,
            status=status,
            last_update=time.time(),
        )

    async def vehicle_status(self, vin: str) -> MgIndiaVehicleStatus:
        """Request current read-only vehicle telemetry from TAP."""

        await self._ensure_login()
        for login_attempt in range(2):
            event_id = 0
            for attempt in range(STATUS_POLL_ATTEMPTS):
                dispatcher, status = await self._status_request(vin, event_id)
                result = dispatcher.get("result", 0)
                if result == 2:
                    if login_attempt == 0:
                        await self.login()
                        break
                    raise MgIndiaApiError("TAP status session is invalid")
                if status is not None:
                    return parse_vehicle_status(status)
                if result not in (0, 4, 6):
                    message = dispatcher.get("errorMessage")
                    if isinstance(message, bytes):
                        message = message.decode(errors="replace")
                    raise MgIndiaApiError(message or f"TAP status error code {result}")
                event_id = dispatcher.get("eventID", event_id)
                if attempt + 1 < STATUS_POLL_ATTEMPTS:
                    await asyncio.sleep(STATUS_POLL_DELAY)
            else:
                raise MgIndiaApiError("Vehicle status was not ready after polling")
        raise MgIndiaApiError("Unable to refresh TAP status session")

    async def verify_control_pin(self, pin_hash: str | None = None) -> None:
        """Verify the locally hashed vehicle-control PIN."""

        await self._ensure_login()
        selected_hash = pin_hash or self._pin_hash
        if selected_hash is None:
            raise MgIndiaApiError("A vehicle-control PIN has not been configured")
        if not re.fullmatch(r"[0-9A-F]{32}", selected_hash):
            raise MgIndiaApiError("Invalid vehicle-control PIN hash")
        if self._token is None or self._user_id is None or self._vin is None:
            raise MgIndiaApiError("Vehicle-control session is incomplete")
        try:
            body = await asyncio.to_thread(
                encode_pin_verification_request,
                self._user_id,
                self._token,
                self._vin,
                selected_hash,
            )
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err
        response = await self._http.post(
            TAP_LOGIN_URL, content=body, headers=tap_headers(body)
        )
        response.raise_for_status()
        try:
            dispatcher = decode_pin_verification_response(response.text)
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err
        result = dispatcher.get("result", 0)
        if result != 0:
            message = dispatcher.get("errorMessage")
            if isinstance(message, bytes):
                message = message.decode(errors="replace")
            raise MgIndiaApiError(message or f"PIN verification failed ({result})")

    async def control_climate(self, *, turn_on: bool) -> None:
        """Turn the remote climate system on or off."""

        params = (
            [(19, b"\x03"), (20, b"\x03"), (255, b"\x00")]
            if turn_on
            else [(19, b"\x00"), (20, b"\x00"), (255, b"\x00")]
        )
        await self._execute_control("Climate", 6, params)

    async def control_door_lock(self, *, lock: bool) -> None:
        """Lock or unlock all vehicle doors."""

        params = (
            None
            if lock
            else [
                (4, b"\x00"),
                (5, b"\x00"),
                (6, b"\x00"),
                (7, b"\x03"),
                (255, b"\x00"),
            ]
        )
        await self._execute_control("Door lock", 1 if lock else 2, params)

    async def release_tailgate(self) -> None:
        """Release the vehicle tailgate."""

        await self._execute_control(
            "Tailgate",
            2,
            [(4, b"\x00"), (5, b"\x00"), (6, b"\x00"), (7, b"\x02"), (255, b"\x00")],
        )

    async def control_windows(
        self, *, open_windows: bool, window_param_ids: tuple[int, ...]
    ) -> None:
        """Open or close the model-supported windows."""

        selected = set(window_param_ids)
        params = [
            (param_id, b"\x01" if param_id in selected else b"\x00")
            for param_id in (8, 9, 10, 11, 12)
        ]
        params.append((13, b"\x03" if open_windows else b"\x00"))
        await self._execute_control("Windows", 3, params)

    async def control_sunroof(self, *, open_sunroof: bool) -> None:
        """Open or close the sunroof."""

        params = [
            (8, b"\x01"),
            (9, b"\x00"),
            (10, b"\x00"),
            (11, b"\x00"),
            (12, b"\x00"),
            (13, b"\x03" if open_sunroof else b"\x00"),
        ]
        await self._execute_control("Sunroof", 3, params)

    async def find_my_car(self, *, stop: bool = False) -> None:
        """Start or stop the vehicle horn-and-lights locator."""

        enabled = b"\x00" if stop else b"\x01"
        await self._execute_control(
            "Find my car",
            0,
            [(1, enabled), (2, enabled), (3, enabled), (255, b"\x00")],
        )

    async def control_heated_seats(
        self, *, driver_level: int, passenger_level: int
    ) -> None:
        """Set front heated-seat levels."""

        if driver_level not in range(4) or passenger_level not in range(4):
            raise MgIndiaApiError("Heated-seat levels must be between 0 and 3")
        await self._execute_control(
            "Heated seats",
            5,
            [
                (17, bytes((driver_level,))),
                (18, bytes((passenger_level,))),
                (255, b"\x00"),
            ],
        )
        self._heated_seat_levels.update(driver=driver_level, passenger=passenger_level)

    async def _execute_control(
        self,
        action: str,
        request_type: int,
        params: list[tuple[int, bytes]] | None,
    ) -> None:
        """Verify the PIN and poll a remote-control command to completion."""

        if self._vin is None:
            await self.vehicles()
        await self.verify_control_pin()
        if self._vin is None:
            raise MgIndiaApiError("No vehicle selected")
        event_id = 0
        for attempt in range(CONTROL_POLL_ATTEMPTS):
            dispatcher, control = await self._control_request(
                self._vin, event_id, request_type, params or []
            )
            result = dispatcher.get("result", 0)
            if control is not None:
                if control.get("rvcReqSts") != b"\x02":
                    failure = control.get("failureType")
                    raise MgIndiaApiError(f"{action} command failed ({failure})")
                return
            if result not in (0, 4, 6):
                message = dispatcher.get("errorMessage")
                if isinstance(message, bytes):
                    message = message.decode(errors="replace")
                raise MgIndiaApiError(
                    message or f"{action} command error code {result}"
                )
            event_id = dispatcher.get("eventID", event_id)
            if attempt + 1 < CONTROL_POLL_ATTEMPTS:
                await asyncio.sleep(CONTROL_POLL_DELAY)
        raise MgIndiaApiError(f"{action} command did not complete after polling")

    async def _control_request(
        self,
        vin: str,
        event_id: int,
        request_type: int,
        params: list[tuple[int, bytes]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if self._token is None or self._user_id is None:
            raise MgIndiaApiError("Not logged in")
        try:
            body = await asyncio.to_thread(
                encode_control_request,
                self._user_id,
                self._token,
                vin,
                event_id,
                request_type,
                params,
            )
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err
        response = await self._http.post(
            TAP_STATUS_URL, content=body, headers=tap_headers(body)
        )
        response.raise_for_status()
        try:
            return decode_control_response(response.text)
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err

    async def _status_request(
        self, vin: str, event_id: int
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if self._token is None or self._user_id is None:
            raise MgIndiaApiError("Not logged in")
        try:
            body = await asyncio.to_thread(
                encode_status_request, self._user_id, self._token, vin, event_id
            )
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err
        response = await self._http.post(
            TAP_STATUS_URL, content=body, headers=tap_headers(body)
        )
        response.raise_for_status()
        try:
            return decode_status_response(response.text)
        except TapCodecError as err:
            raise MgIndiaApiError(str(err)) from err

    async def gateway_get(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        await self._ensure_login()
        response = await self._gateway_get_raw(path, params or {})
        parsed = json.loads(decrypt_gateway_body(response.text, response.headers))
        code = parsed.get("code")
        if code == 7:
            await self.login()
            response = await self._gateway_get_raw(path, params or {})
            parsed = json.loads(decrypt_gateway_body(response.text, response.headers))
            code = parsed.get("code")
        if code != 0:
            raise MgIndiaApiError(parsed.get("message", f"Gateway error code {code}"))
        return parsed

    async def _gateway_get_optional(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        try:
            return await self.gateway_get(path, params)
        except MgIndiaApiError:
            return None

    async def _gateway_get_raw(
        self, path: str, params: dict[str, str]
    ) -> httpx.Response:
        if self._token is None or self._user_id is None:
            raise MgIndiaApiError("Not logged in")
        clean_path = "/" + path.lstrip("/")
        query = urlencode(params)
        signing_path = clean_path + (f"?{query}" if query else "")
        timestamp = str(int(time.time() * 1000))
        content_type = "application/json"
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": content_type,
            "APP-CONTENT-ENCRYPTED": "1",
            "APP-LANGUAGE-TYPE": "en-us",
            "APP-LOGIN-TOKEN": self._token,
            "APP-USER-ID": self._user_id,
            "APP-SEND-DATE": timestamp,
            "APP-VERIFICATION-STRING": gateway_signature(
                signing_path, timestamp, content_type
            ),
            "ORIGINAL-CONTENT-TYPE": content_type,
        }
        response = await self._http.get(
            f"{GATEWAY_BASE_URL}{clean_path}", params=params, headers=headers
        )
        response.raise_for_status()
        return response

    async def _ensure_login(self) -> None:
        if self._token is None or self._user_id is None:
            await self.login()

    def _build_login_body(self) -> str:
        dispatcher = bytearray.fromhex(LOGIN_DISPATCHER_TEMPLATE_HEX)
        app = encode_login_app(self._password, self._device_id)
        set_fixed_7bit_string(dispatcher, 48, self._phone.rjust(50, "0"))
        set_bits(dispatcher, 419, 32, int(time.time()))
        dispatcher[-7:-3] = (len(app) * 2).to_bytes(4, "big")
        dispatcher[-3] = 1
        dispatcher[-2:] = (160).to_bytes(2, "big")
        payload = bytes(dispatcher) + app
        raw_without_prefix = "1" + payload.hex().upper()
        return f"{len(raw_without_prefix) + 4:04X}{raw_without_prefix}"

    def _select_vehicle(self, vehicles: list[MgIndiaVehicle]) -> MgIndiaVehicle:
        if not vehicles:
            raise MgIndiaApiError("No vehicles returned by account")
        if self._vin is None:
            self._vin = vehicles[0].vin
            return vehicles[0]
        for vehicle in vehicles:
            if vehicle.vin == self._vin:
                return vehicle
        raise MgIndiaApiError("Configured VIN was not returned by account")


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone)
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) != 10:
        raise MgIndiaApiError("Phone must contain a 10-digit India mobile number")
    return digits


def make_device_id(phone: str) -> str:
    seed = hashlib.sha256(f"mg-ismart-india:{phone}".encode()).hexdigest()
    return (f"haos-mg-ismart-india-{seed}" + "0" * 120)[:103]


def encode_login_app(password: str, device_id: str) -> bytes:
    from .bitcodec import BitWriter

    writer = BitWriter()
    writer.write_bits(1, 1)
    writer.write_7bit_string(password, 6, 30)
    writer.write_7bit_string(device_id, 1, 200)
    return writer.to_bytes()


def decode_tap_response(raw: str) -> tuple[bytes, bytes]:
    if len(raw) < 5 or raw[4] != "1":
        raise MgIndiaApiError("Unexpected TAP response framing")
    payload = bytes.fromhex(raw[5:])
    if len(payload) < 4:
        raise MgIndiaApiError("TAP response payload is too short")
    dispatcher_len = payload[2] + (payload[3] << 8)
    return payload[:dispatcher_len], payload[dispatcher_len:]


def decode_login_token(app: bytes) -> str:
    reader = BitReader(app)
    reader.read_bits(6)
    token = reader.read_7bit_string(40, 40)
    refresh = reader.read_7bit_string(40, 40)
    if token != refresh:
        raise MgIndiaApiError("Login token and refresh token differ")
    return token


def tap_signature(body: str) -> str:
    key_material = body[1 : len(body) // 2]
    hmac_key = hashlib.md5(key_material.encode()).hexdigest()
    return hmac.new(hmac_key.encode(), body.encode(), hashlib.sha256).hexdigest()


def tap_headers(body: str) -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Content-Type": "text/plain",
        "Accept": "*/*",
        "Accept-Language": "en-US;q=1",
        "APP-SIGNATURE": tap_signature(body),
        "SIGNATURE": "1",
    }


def hash_control_pin(pin: str) -> str:
    """Hash a numeric control PIN in the format expected by MG India."""

    if not re.fullmatch(r"\d{4,8}", pin):
        raise MgIndiaApiError("Control PIN must contain 4 to 8 digits")
    normalized_pin = pin if len(pin) == 6 else f"{pin}00"
    return hashlib.md5(normalized_pin.encode()).hexdigest().upper()


def gateway_signature(signing_path: str, current_ts: str, content_type: str) -> str:
    key_part_one = md5_hex_digest(signing_path)
    encrypt_key = md5_hex_digest(key_part_one + current_ts + "1" + content_type)
    hmac_value = signing_path + current_ts + "1" + content_type
    hmac_key = md5_hex_digest(encrypt_key + current_ts)
    return hmac.new(
        hmac_key.encode(), msg=hmac_value.encode(), digestmod=hashlib.sha256
    ).hexdigest()


def decrypt_gateway_body(encrypted: str, headers: httpx.Headers) -> str:
    key = md5_hex_digest(
        headers["APP-SEND-DATE"] + "1" + headers["ORIGINAL-CONTENT-TYPE"]
    )
    iv = md5_hex_digest(headers["APP-SEND-DATE"])
    cipher = AES.new(unhexlify(key), AES.MODE_CBC, unhexlify(iv))
    return unpad(cipher.decrypt(unhexlify(encrypted)), AES.block_size).decode("utf-8")


def md5_hex_digest(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()


def parse_vehicle(raw: dict[str, Any]) -> MgIndiaVehicle:
    return MgIndiaVehicle(
        vin=raw["vin"],
        brand_name=raw.get("brandName"),
        model_name=raw.get("modelName"),
        model_year=raw.get("modelYear"),
        series=raw.get("series"),
        is_active=raw.get("isActivate"),
        raw=raw,
    )


def parse_vehicle_status(raw: dict[str, Any]) -> MgIndiaVehicleStatus:
    """Normalize protocol-513 status values into Home Assistant units."""

    basic = raw.get("basicVehicleStatus", {})
    gps = parse_gps_position(raw.get("gpsPosition"))
    engine_status = basic.get("engineStatus")
    power_mode = basic.get("powerMode")
    # engineStatus == 1 indicates the HV battery is being charged
    charging = engine_status == 1 if isinstance(engine_status, int) else None
    return MgIndiaVehicleStatus(
        status_time=positive_int(raw.get("statusTime")),
        last_vehicle_activity=positive_int(basic.get("timeOfLastCANBUSActivity")),
        battery_percent=bounded_int(basic.get("fuelLevelPrc"), 0, 100),
        range_km=tenths(basic.get("fuelRange")),
        odometer_km=tenths(basic.get("mileage")),
        auxiliary_battery_voltage=tenths(basic.get("batteryVoltage")),
        interior_temperature=valid_temperature(basic.get("interiorTemperature")),
        exterior_temperature=valid_temperature(basic.get("exteriorTemperature")),
        locked=optional_bool(basic.get("lockStatus")),
        driver_door_open=optional_bool(basic.get("driverDoor")),
        passenger_door_open=optional_bool(basic.get("passengerDoor")),
        rear_left_door_open=optional_bool(basic.get("rearLeftDoor")),
        rear_right_door_open=optional_bool(basic.get("rearRightDoor")),
        boot_open=optional_bool(basic.get("bootStatus")),
        bonnet_open=optional_bool(basic.get("bonnetStatus")),
        driver_window_open=optional_bool(basic.get("driverWindow")),
        passenger_window_open=optional_bool(basic.get("passengerWindow")),
        rear_left_window_open=optional_bool(basic.get("rearLeftWindow")),
        rear_right_window_open=optional_bool(basic.get("rearRightWindow")),
        climate_running=(basic.get("remoteClimateStatus") in (2, 3))
        if basic.get("remoteClimateStatus") is not None
        else None,
        sunroof_open=optional_bool(basic.get("sunroofStatus")),
        can_bus_active=optional_bool(basic.get("canBusActive")),
        charging=charging,
        engine_status=engine_status if isinstance(engine_status, int) else None,
        power_mode=power_mode if isinstance(power_mode, int) else None,
        gps=gps,
    )


def parse_gps_position(raw: dict[str, Any] | None) -> MgIndiaGpsPosition | None:
    """Parse the gpsPosition block from a TAP status response."""

    if not raw or not isinstance(raw, dict):
        return None
    waypoint = raw.get("wayPoint", {})
    position = waypoint.get("position", {})
    lat_raw = position.get("latitude")
    lng_raw = position.get("longitude")
    # Coordinates are in units of 1e-6 degrees
    latitude = lat_raw / 1_000_000 if isinstance(lat_raw, int) else None
    longitude = lng_raw / 1_000_000 if isinstance(lng_raw, int) else None
    # Filter out zero/zero which means no fix
    if latitude == 0.0 and longitude == 0.0:
        latitude = None
        longitude = None
    altitude = position.get("altitude") if isinstance(position.get("altitude"), int) else None
    heading = waypoint.get("heading") if isinstance(waypoint.get("heading"), int) else None
    speed_raw = waypoint.get("speed")
    speed = speed_raw / 10 if isinstance(speed_raw, int) and speed_raw >= 0 else None
    gps_status = raw.get("gpsStatus")
    gps_fix_map = {0: "no_signal", 1: "time_fix", 2: "2d_fix", 3: "3d_fix"}
    gps_fix = gps_fix_map.get(gps_status) if isinstance(gps_status, (int, str)) else None
    return MgIndiaGpsPosition(
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        heading=heading,
        speed=speed,
        gps_fix=gps_fix,
    )


def positive_int(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    ):
        return value
    return None


def tenths(value: Any) -> float | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return round(value / 10, 1)


def valid_temperature(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value in (-128, -40):
        return None
    return value if -50 <= value <= 80 else None


def optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
