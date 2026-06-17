"""Small bit-level helpers for MG India TAP payloads."""

from __future__ import annotations

import math


class BitReader:
    """MSB-first bit reader."""

    def __init__(self, data: bytes | bytearray) -> None:
        self._data = data
        self._offset = 0

    @property
    def bit_offset(self) -> int:
        return self._offset

    def read_bits(self, bit_count: int) -> int:
        value = 0
        for _ in range(bit_count):
            byte_index = self._offset // 8
            bit_index = 7 - (self._offset % 8)
            value = (value << 1) | ((self._data[byte_index] >> bit_index) & 1)
            self._offset += 1
        return value

    def read_7bit_string(self, minimum: int, maximum: int) -> str:
        length = self.read_constrained_length(minimum, maximum)
        return "".join(chr(self.read_bits(7)) for _ in range(length))

    def read_constrained_length(self, minimum: int, maximum: int) -> int:
        span = maximum - minimum
        if span == 0:
            return minimum
        return minimum + self.read_bits(math.ceil(math.log2(span + 1)))


class BitWriter:
    """MSB-first bit writer."""

    def __init__(self) -> None:
        self._bits: list[int] = []

    def write_bits(self, value: int, bit_count: int) -> None:
        if value < 0 or value >= (1 << bit_count):
            raise ValueError(f"value does not fit in {bit_count} bits")
        for shift in range(bit_count - 1, -1, -1):
            self._bits.append((value >> shift) & 1)

    def write_7bit_string(self, value: str, minimum: int, maximum: int) -> None:
        self.write_constrained_length(len(value), minimum, maximum)
        for char in value:
            self.write_bits(ord(char), 7)

    def write_constrained_length(self, length: int, minimum: int, maximum: int) -> None:
        if not minimum <= length <= maximum:
            raise ValueError(f"length {length} outside {minimum}..{maximum}")
        span = maximum - minimum
        if span:
            self.write_bits(length - minimum, math.ceil(math.log2(span + 1)))

    def to_bytes(self) -> bytes:
        out = bytearray()
        for offset in range(0, len(self._bits), 8):
            value = 0
            chunk = self._bits[offset : offset + 8]
            for bit in chunk:
                value = (value << 1) | bit
            value <<= 8 - len(chunk)
            out.append(value)
        return bytes(out)


def read_bits(data: bytes | bytearray, bit_offset: int, bit_count: int) -> int:
    """Read a MSB-first integer at an absolute bit offset."""

    value = 0
    for index in range(bit_count):
        absolute = bit_offset + index
        byte_index = absolute // 8
        bit_index = 7 - (absolute % 8)
        value = (value << 1) | ((data[byte_index] >> bit_index) & 1)
    return value


def set_bits(data: bytearray, bit_offset: int, bit_count: int, value: int) -> None:
    """Write a MSB-first integer at an absolute bit offset."""

    if value < 0 or value >= (1 << bit_count):
        raise ValueError(f"value {value} does not fit in {bit_count} bits")
    for index in range(bit_count):
        bit = (value >> (bit_count - 1 - index)) & 1
        absolute = bit_offset + index
        byte_index = absolute // 8
        bit_index = 7 - (absolute % 8)
        if bit:
            data[byte_index] |= 1 << bit_index
        else:
            data[byte_index] &= ~(1 << bit_index)


def read_fixed_7bit_string(
    data: bytes | bytearray, bit_offset: int, char_count: int
) -> str:
    """Read a fixed-length 7-bit string at an absolute bit offset."""

    return "".join(
        chr(read_bits(data, bit_offset + index * 7, 7)) for index in range(char_count)
    )


def set_fixed_7bit_string(data: bytearray, bit_offset: int, value: str) -> None:
    """Write a fixed-length 7-bit string at an absolute bit offset."""

    for index, char in enumerate(value):
        set_bits(data, bit_offset + index * 7, 7, ord(char))
