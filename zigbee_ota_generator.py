#!/usr/bin/env python3
"""Generate and strictly inspect Zigbee OTA containers (no third-party dependencies)."""

import argparse
import hashlib
from pathlib import Path
import struct

MAGIC = 0x0BEEF11E
BASIC_HEADER = struct.Struct('<IHHHHHIH32sI')
ELEMENT_HEADER = struct.Struct('<HI')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def uint(value, bits, name):
    require(type(value) is int and 0 <= value < 1 << bits, f'{name} must be an unsigned {bits}-bit integer')
    return value


def build_ota(payload, *, manufacturer_code, image_type, file_version,
              header_string='ESP32 Zigbee OTA', stack_version=2,
              min_hardware_version=1, max_hardware_version=1, espressif_compatible=True):
    """Wrap bytes in a 60-byte header and one upgrade-image subelement.

    Total Image Size always includes the entire OTA file. The compatibility
    option only selects zero rather than 0xff padding for the header string.
    """
    for name, value, bits in [('manufacturer_code', manufacturer_code, 16),
                              ('image_type', image_type, 16), ('file_version', file_version, 32),
                              ('stack_version', stack_version, 16),
                              ('min_hardware_version', min_hardware_version, 16),
                              ('max_hardware_version', max_hardware_version, 16)]:
        uint(value, bits, name)
    require(min_hardware_version <= max_hardware_version, 'Hardware version range is reversed')
    require(isinstance(payload, bytes) and payload, 'Nonempty payload bytes required')
    require(isinstance(header_string, str), 'Header string must be text')
    label = header_string.encode('utf-8')
    require(len(label) <= 32, 'Header string exceeds 32 UTF-8 bytes')
    label = label.ljust(32, b'\x00' if espressif_compatible else b'\xff')
    total = uint(66 + len(payload), 32, 'total size')
    header = BASIC_HEADER.pack(MAGIC, 0x100, 60, 4, manufacturer_code, image_type,
                               file_version, stack_version, label, total)
    return header + struct.pack('<HH', min_hardware_version, max_hardware_version) + ELEMENT_HEADER.pack(0, len(payload)) + payload


def inspect_ota(data):
    """Return header/elements or raise ValueError for malformed containers."""
    require(len(data) >= 56, 'File too small for a Zigbee OTA header')
    magic, version, length, flags, manufacturer, kind, file_version, stack, label, total = BASIC_HEADER.unpack_from(data)
    require(magic == MAGIC and version == 0x100, 'Invalid OTA magic or header version')
    require(flags & ~7 == 0, 'Unsupported header flags')
    expected = 56 + (1 if flags & 1 else 0) + (8 if flags & 2 else 0) + (4 if flags & 4 else 0)
    require(length == expected and length <= len(data), 'Invalid optional fields or header length')
    require(total == len(data), 'Total Image Size does not match the complete file')
    offset = 56
    if flags & 1:
        offset += 1
    if flags & 2:
        offset += 8
    hardware = None
    if flags & 4:
        hardware = struct.unpack_from('<HH', data, offset)
        require(hardware[0] <= hardware[1], 'Hardware version range is reversed')
    elements = []
    offset = length
    while offset < len(data):
        require(offset + 6 <= len(data), 'Truncated subelement header')
        tag, size = ELEMENT_HEADER.unpack_from(data, offset)
        offset += 6
        require(offset + size <= len(data), 'Truncated subelement payload')
        elements.append((tag, data[offset:offset + size]))
        offset += size
    upgrades = [body for tag, body in elements if tag == 0]
    require(len(upgrades) == 1 and bool(upgrades[0]),
            'Exactly one nonempty upgrade-image subelement required')
    return dict(manufacturer_code=manufacturer, image_type=kind, file_version=file_version,
                stack_version=stack, header_string=label, hardware=hardware,
                total_size=total, elements=elements)


class ZigbeeOTAGenerator:
    MAGIC_NUMBER = MAGIC
    HEADER_VERSION = 0x100
    HEADER_LENGTH_EXTENDED = 60
    TAG_UPGRADE_IMAGE = 0
    FIELD_CONTROL_HW_VERSION = 4

    def generate_ota_file(self, args):
        source, target = Path(args.input), Path(args.output)
        require(source.resolve() != target.resolve(), 'Input and output must be different files')
        data = build_ota(source.read_bytes(), manufacturer_code=args.manufacturer_code,
                         image_type=args.image_type, file_version=args.file_version,
                         header_string=args.header_string, stack_version=args.stack_version,
                         min_hardware_version=args.min_hardware_version,
                         max_hardware_version=args.max_hardware_version,
                         espressif_compatible=args.espressif_compatible)
        with target.open('xb') as f:
            f.write(data)
        print(f'OTA file generated: {target}\nSize: {len(data)} bytes\nSHA512: {hashlib.sha512(data).hexdigest()}')
        return True

    def parse_ota_file(self, filename):
        try:
            data = Path(filename).read_bytes()
            info = inspect_ota(data)
        except (OSError, ValueError, struct.error) as error:
            print(f'Invalid OTA: {error}')
            return False
        for key in ('manufacturer_code', 'image_type', 'file_version', 'stack_version', 'total_size'):
            print(f'{key}: {info[key]}')
        print('header_string:', info['header_string'].rstrip(b'\x00\xff').decode('utf-8', errors='replace'))
        print('hardware:', info['hardware'])
        for tag, payload in info['elements']:
            print(f'subelement: tag={tag}, size={len(payload)}')
        print('SHA512:', hashlib.sha512(data).hexdigest())
        print('OTA container is valid (payload authenticity/ESP validity are not checked here).')
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create', help='Wrap firmware bytes in a Zigbee OTA container')
    create.add_argument('-i', '--input', required=True, type=Path)
    create.add_argument('-o', '--output', required=True, type=Path)
    for option in ('manufacturer-code', 'image-type', 'file-version'):
        create.add_argument('--' + option, required=True, type=lambda x: int(x, 0))
    for option, default in [('stack-version', 2), ('min-hardware-version', 1), ('max-hardware-version', 1)]:
        create.add_argument('--' + option, default=default, type=lambda x: int(x, 0))
    create.add_argument('--header-string', default='ESP32 Zigbee OTA')
    create.add_argument('--espressif-compatible', action='store_true', help='Use zero-padded header text')
    parse = sub.add_parser('parse', help='Strictly inspect a Zigbee OTA container')
    parse.add_argument('filename', type=Path)
    args = parser.parse_args()
    try:
        generator = ZigbeeOTAGenerator()
        ok = generator.generate_ota_file(args) if args.command == 'create' else generator.parse_ota_file(args.filename)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'Refused: {error}\n')
    if not ok:
        parser.exit(1)


if __name__ == '__main__':
    main()
