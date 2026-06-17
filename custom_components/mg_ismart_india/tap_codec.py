"""TAP v2.1 protocol codec for the India application protocol 513."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import time
from typing import Any

import asn1tools

TAP_PROTOCOL_VERSION = 33
TAP_RESERVED_SIZE = 16
STATUS_APPLICATION_ID = "511"
STATUS_APPLICATION_PROTOCOL = 513
CONTROL_APPLICATION_ID = "510"
CONTROL_APPLICATION_PROTOCOL = 513
PIN_APPLICATION_ID = "313"
PIN_APPLICATION_PROTOCOL = 513
V11_PROTOCOL_VERSION = 17
V11_SIM_INFO = "1234567890987654321"
V11_ICC_ID = "12345678901234567890"


class TapCodecError(ValueError):
    """Raised when a TAP status message cannot be encoded or decoded."""


@lru_cache(maxsize=1)
def _codec() -> Any:
    return asn1tools.compile_files(
        str(Path(__file__).with_name("tap_v21_513.asn1")), "uper"
    )


@lru_cache(maxsize=1)
def _codec_v11() -> Any:
    return asn1tools.compile_files(
        str(Path(__file__).with_name("tap_v11_513.asn1")), "uper"
    )


def encode_status_request(uid: str, token: str, vin: str, event_id: int) -> str:
    """Encode a read-only vehicle status request."""

    app = _codec().encode("OTARVMVehicleStatusReq", {"vehStatusReqType": 2})
    return _encode_v21_request(
        uid,
        token,
        vin,
        event_id,
        STATUS_APPLICATION_ID,
        STATUS_APPLICATION_PROTOCOL,
        app,
    )


def encode_control_request(
    uid: str,
    token: str,
    vin: str,
    event_id: int,
    request_type: int,
    params: list[tuple[int, bytes]],
) -> str:
    """Encode a remote vehicle control request."""

    app = _codec().encode(
        "OTARVCReq",
        {
            "rvcReqType": bytes((request_type,)),
            "rvcParams": [
                {"paramId": param_id, "paramValue": value} for param_id, value in params
            ],
        },
    )
    return _encode_v21_request(
        uid,
        token,
        vin,
        event_id,
        CONTROL_APPLICATION_ID,
        CONTROL_APPLICATION_PROTOCOL,
        app,
    )


def _encode_v21_request(
    uid: str,
    token: str,
    vin: str,
    event_id: int,
    application_id: str,
    application_protocol: int,
    app: bytes,
) -> str:
    body = _codec().encode(
        "MPDispatcherBody",
        {
            "uid": uid,
            "token": token,
            "applicationID": application_id,
            "vin": vin,
            "messageID": 1,
            "eventCreationTime": int(time.time()),
            "eventID": event_id,
            "ulMessageCounter": 0,
            "dlMessageCounter": 0,
            "ackMessageCounter": 0,
            "ackRequired": False,
            "applicationDataLength": len(app),
            "applicationDataEncoding": "perUnaligned",
            "applicationDataProtocolVersion": application_protocol,
            "testFlag": 2,
            "result": 0,
        },
    )
    dispatcher_length = len(body) + 3
    if dispatcher_length > 255:
        raise TapCodecError("TAP dispatcher is too large")
    payload = (
        bytes((TAP_PROTOCOL_VERSION, dispatcher_length, 0))
        + bytes(TAP_RESERVED_SIZE)
        + body
        + app
    )
    return "1" + f"{len(payload) + 3:04X}" + payload.hex().upper()


def encode_pin_verification_request(
    uid: str, token: str, vin: str, pin_hash: str
) -> str:
    """Encode a protocol-513 control PIN verification request."""

    app = _codec_v11().encode("PINVerificationReq", {"pin": pin_hash})
    body = _codec_v11().encode(
        "MPDispatcherBodyV11",
        {
            "uid": uid,
            "token": token,
            "applicationID": PIN_APPLICATION_ID,
            "vin": vin,
            "eventCreationTime": int(time.time()),
            "messageID": 1,
            "messageCounter": {"uplinkCounter": 1, "downlinkCounter": 0},
            "simInfo": V11_SIM_INFO,
            "iccID": V11_ICC_ID,
            "applicationDataLength": len(app),
            "applicationDataEncoding": "perUnaligned",
            "applicationDataProtocolVersion": PIN_APPLICATION_PROTOCOL,
            "testFlag": 2,
        },
    )
    dispatcher_length = len(body) + 4
    if dispatcher_length > 255:
        raise TapCodecError("TAP PIN dispatcher is too large")
    payload = bytes((V11_PROTOCOL_VERSION, 0, dispatcher_length, 0)) + body + app
    return f"{len(payload) * 2 + 5:04X}1" + payload.hex().upper()


def decode_status_response(raw: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Decode the dispatcher and optional vehicle status application data."""

    dispatcher, app = _decode_v21_response(raw)
    if app is None:
        return dispatcher, None
    try:
        status = _codec().decode("OTARVMVehicleStatusResp513", app)
    except Exception as err:
        raise TapCodecError("Unable to decode TAP vehicle status") from err
    return dispatcher, status


def decode_control_response(raw: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Decode a dispatcher and optional remote control result."""

    dispatcher, app = _decode_v21_response(raw)
    if app is None:
        return dispatcher, None
    try:
        control = _codec().decode("OTARVCStatus513", app)
    except Exception as err:
        raise TapCodecError("Unable to decode TAP control result") from err
    return dispatcher, control


def _decode_v21_response(raw: str) -> tuple[dict[str, Any], bytes | None]:
    if len(raw) < 5 or raw[0] != "1":
        raise TapCodecError("Unexpected TAP v2.1 response framing")
    try:
        payload = bytes.fromhex(raw[5:])
    except ValueError as err:
        raise TapCodecError("TAP v2.1 response is not hexadecimal") from err
    if len(payload) < 19:
        raise TapCodecError("TAP v2.1 response is too short")

    dispatcher_length = payload[1]
    dispatcher_end = TAP_RESERVED_SIZE + dispatcher_length
    if dispatcher_length < 3 or dispatcher_end > len(payload):
        raise TapCodecError("Invalid TAP v2.1 dispatcher length")
    try:
        dispatcher = _codec().decode("MPDispatcherBody", payload[19:dispatcher_end])
    except Exception as err:
        raise TapCodecError("Unable to decode TAP v2.1 dispatcher") from err

    app_length = dispatcher.get("applicationDataLength", 0)
    if not app_length:
        return dispatcher, None
    app = payload[dispatcher_end : dispatcher_end + app_length]
    if len(app) != app_length:
        raise TapCodecError("Truncated TAP v2.1 application data")
    return dispatcher, app


def decode_pin_verification_response(raw: str) -> dict[str, Any]:
    """Decode a protocol v1.1 PIN verification response dispatcher."""

    if len(raw) < 5 or raw[4] != "1":
        raise TapCodecError("Unexpected TAP PIN response framing")
    try:
        payload = bytes.fromhex(raw[5:])
    except ValueError as err:
        raise TapCodecError("TAP PIN response is not hexadecimal") from err
    if len(payload) < 4:
        raise TapCodecError("TAP PIN response is too short")
    dispatcher_length = payload[2]
    if dispatcher_length < 4 or dispatcher_length > len(payload):
        raise TapCodecError("Invalid TAP PIN dispatcher length")
    try:
        return _codec_v11().decode("MPDispatcherBodyV11", payload[4:dispatcher_length])
    except Exception as err:
        raise TapCodecError("Unable to decode TAP PIN dispatcher") from err
