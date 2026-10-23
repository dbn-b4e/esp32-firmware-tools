#!/usr/bin/env python3
"""Verified ESP32-C6 differential OTA packaging with an explicit device profile.

The 128-byte envelope is derived from the B4E firmware protocol. Stock ESP32
firmware cannot consume it: the matching streaming decoder must be installed.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct

from zigbee_ota_generator import build_ota, inspect_ota, require, uint

HEADER = struct.Struct('<8s32s6I32s32s')
ESP_PATCH_MAGIC = 0xFCCDDE10


@dataclass(frozen=True)
class DeltaProfile:
    name: str
    model: str
    envelope_magic: bytes
    min_base_version: int
    slot_size: int
    manufacturer_code: int
    image_type: int
    stack_version: int = 2
    min_hardware_version: int = 1
    max_hardware_version: int = 1

    def __post_init__(self):
        require(isinstance(self.name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', self.name), 'Invalid profile name')
        require(isinstance(self.model, str) and self.model.isascii() and
                1 <= len(self.model) <= 32 and all(32 <= ord(c) <= 126 for c in self.model),
                'Model must contain 1 to 32 printable ASCII bytes')
        require(isinstance(self.envelope_magic, bytes) and len(self.envelope_magic) == 8, 'Envelope magic must be exactly 8 bytes')
        for name in ('min_base_version', 'slot_size'):
            uint(getattr(self, name), 32, name)
        for name in ('manufacturer_code', 'image_type', 'stack_version', 'min_hardware_version', 'max_hardware_version'):
            uint(getattr(self, name), 16, name)
        require(self.min_base_version > 0 and self.slot_size >= 193, 'Invalid version floor or partition size')
        require(self.min_hardware_version <= self.max_hardware_version, 'Hardware version range is reversed')

    def as_json(self):
        result = asdict(self)
        result['magic_hex'] = result.pop('envelope_magic').hex()
        return result

    @classmethod
    def load(cls, filename):
        data = json.loads(Path(filename).read_text())
        require(isinstance(data, dict), 'Profile must be a JSON object')
        try:
            data['envelope_magic'] = bytes.fromhex(data.pop('magic_hex'))
            return cls(**data)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f'Invalid profile: {error}') from error


def parse_envelope(data, profile):
    require(len(data) >= 193, 'Truncated delta')
    magic, model, version, bv, bs, ts, ps, reserved, bh, th = HEADER.unpack_from(data)
    require(magic == profile.envelope_magic and model == profile.model.encode().ljust(32, b'\0') and reserved == 0,
            'Incorrect delta magic, model or reserved field')
    require(profile.min_base_version <= bv < version <= 0xffffffff, 'Base lacks delta support or versions are invalid')
    require(24 <= bs <= profile.slot_size and 24 <= ts <= profile.slot_size and
            65 <= ps <= profile.slot_size - 128 and len(data) == 128 + ps,
            'Incorrect delta sizes')
    require(data[128:132] == struct.pack('<I', ESP_PATCH_MAGIC) and not any(data[164:192]) and data[192] == 4,
            'Expected official Espressif sequential/heatshrink patch')
    return dict(version=version, base_version=bv, base_size=bs, target_size=ts,
                patch_size=ps, base_sha256=bh.hex(), target_sha256=th.hex(),
                esp_base_sha256=data[132:164].hex())


def envelope(base, target, base_version, version, patch, profile):
    uint(base_version, 32, 'base_version')
    uint(version, 32, 'version')
    data = HEADER.pack(profile.envelope_magic, profile.model.encode(), version, base_version,
                       len(base), len(target), len(patch), 0,
                       hashlib.sha256(base).digest(), hashlib.sha256(target).digest()) + patch
    parse_envelope(data, profile)
    return data


def esp_digest(data):
    from esptool.bin_image import ESP32C6FirmwareImage
    from esptool.util import FatalError
    require(len(data) >= 24 and data[0] == 0xe9 and struct.unpack_from('<H', data, 12)[0] == 13 and data[23] == 1,
            'Expected ESP32-C6 application image with appended digest')
    try:
        image = ESP32C6FirmwareImage(io.BytesIO(data))
        image.verify()
        require(image.append_digest and image.stored_digest == image.calc_digest, 'Invalid ESP SHA256 digest')
        require(image.checksum == image.calculate_checksum(), 'Invalid ESP checksum')
        # Reject bytes outside the valid image, not silently ignored by esptool.
        require(len(data) == image.data_length + 32, 'Trailing bytes after ESP digest')
        return image.stored_digest
    except (FatalError, ValueError, struct.error, EOFError, TypeError, IndexError) as error:
        raise ValueError(f'Invalid ESP application: {error}') from error


def validate_images(base, target, base_version, version, profile):
    uint(base_version, 32, 'base_version')
    uint(version, 32, 'version')
    require(profile.min_base_version <= base_version < version, 'Base lacks delta support or versions are invalid')
    for data, v in [(base, base_version), (target, version)]:
        require(24 <= len(data) <= profile.slot_size, 'Application exceeds partition bounds')
        require(struct.pack('<32sI', profile.model.encode(), v) in data, 'Compiled model/version identity marker is absent')
        esp_digest(data)


def reconstruct(base, payload):
    import detools
    require(len(payload) >= 193, 'Truncated delta')
    target_size = struct.unpack_from('<I', payload, 52)[0]

    class BoundedOutput(io.BytesIO):
        def write(self, data):
            require(self.tell() + len(data) <= target_size,
                    'Reconstructed application exceeds expected target size')
            return super().write(data)

    result = BoundedOutput()
    try:
        detools.apply_patch(io.BytesIO(base), io.BytesIO(payload[192:]), result)
    except Exception as error:
        raise ValueError(f'Delta reconstruction failed: {error}') from error
    return result.getvalue()


def filenames(profile, info):
    stem = f"{profile.name}-{info['base_version']:08x}-to-{info['version']:08x}"
    return stem + '.delta.bin', stem + '.delta.ota'


def manifest(payload, ota, profile):
    info = parse_envelope(payload, profile)
    delta_name, ota_name = filenames(profile, info)
    return dict(kind='delta', model=profile.model, profile=profile.as_json(), **info,
                size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                delta_file=delta_name, zigbee_file=ota_name,
                zigbee_sha512=hashlib.sha512(ota).hexdigest())


def index_for(m, profile):
    return [dict(fileVersion=m['version'], fileSize=66 + m['size'],
                 manufacturerCode=profile.manufacturer_code, imageType=profile.image_type,
                 minFileVersion=m['base_version'], maxFileVersion=m['base_version'],
                 sha512=m['zigbee_sha512'], url=m['zigbee_file'])]


def wrap(payload, profile, version):
    return build_ota(payload, manufacturer_code=profile.manufacturer_code,
                     image_type=profile.image_type, file_version=version,
                     header_string=profile.model, stack_version=profile.stack_version,
                     min_hardware_version=profile.min_hardware_version,
                     max_hardware_version=profile.max_hardware_version)


def file_at(root, name):
    require(isinstance(name, str) and name not in ('', '.', '..') and Path(name).name == name,
            'Expected a local artifact filename')
    p = root / name
    require(not p.is_symlink(), 'Artifact symlinks are not accepted')
    return p.read_bytes()


def verify_delta(root, base_file, target_file, profile):
    root = Path(root)
    m = json.loads((root / 'delta-manifest.json').read_text())
    require(isinstance(m, dict), 'Manifest must be an object')
    try:
        payload = file_at(root, m['delta_file'])
        info = parse_envelope(payload, profile)
        base, target = Path(base_file).read_bytes(), Path(target_file).read_bytes()
        validate_images(base, target, info['base_version'], info['version'], profile)
        require(info['base_size'] == len(base) and info['base_sha256'] == hashlib.sha256(base).hexdigest(), 'Exact base mismatch')
        require(info['target_size'] == len(target) and info['target_sha256'] == hashlib.sha256(target).hexdigest(), 'Exact target mismatch')
        require(info['esp_base_sha256'] == esp_digest(base).hex(), 'Espressif base digest mismatch')
        ota = file_at(root, m['zigbee_file'])
        inspect_ota(ota)
        require(ota == wrap(payload, profile, info['version']), 'Zigbee container or payload mismatch')
        require(m == manifest(payload, ota, profile), 'Manifest identity, sizes or hashes mismatch')
        require(json.loads((root / 'z2m-index.json').read_text()) == index_for(m, profile), 'Index must constrain the exact base version')
        require(reconstruct(base, payload) == target, 'Reconstructed application differs from target')
    except (KeyError, TypeError, struct.error) as error:
        raise ValueError(f'Invalid delta package: {error}') from error
    return m


def make_delta(base_file, target_file, base_version, version, output, profile):
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'Output already exists')
    base, target = Path(base_file).read_bytes(), Path(target_file).read_bytes()
    validate_images(base, target, base_version, version, profile)
    import detools
    raw = io.BytesIO()
    detools.create_patch(io.BytesIO(base), io.BytesIO(target), raw, compression='heatshrink')
    official = struct.pack('<I', ESP_PATCH_MAGIC) + esp_digest(base) + bytes(28) + raw.getvalue()
    payload = envelope(base, target, base_version, version, official, profile)
    require(reconstruct(base, payload) == target, 'Reconstructed application differs from target')
    ota = wrap(payload, profile, version)
    m = manifest(payload, ota, profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    artifacts = {m['delta_file']: payload, m['zigbee_file']: ota,
                 'delta-manifest.json': (json.dumps(m, indent=2) + '\n').encode(),
                 'z2m-index.json': (json.dumps(index_for(m, profile), indent=2) + '\n').encode()}
    for name, data in artifacts.items():
        with os.fdopen(os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
            f.write(data)
    verify_delta(output, base_file, target_file, profile)
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('create', 'verify'):
        p = sub.add_parser(name)
        for option in ('profile', 'base', 'target', 'output'):
            p.add_argument('--' + option, type=Path, required=True)
        if name == 'create':
            p.add_argument('--base-version', type=lambda x: int(x, 0), required=True)
            p.add_argument('--target-version', type=lambda x: int(x, 0), required=True)
    args = parser.parse_args()
    try:
        profile = DeltaProfile.load(args.profile)
        if args.command == 'create':
            result = make_delta(args.base, args.target, args.base_version, args.target_version, args.output, profile)
        else:
            result = verify_delta(args.output, args.base, args.target, profile)
    except (OSError, ValueError, TypeError, KeyError, struct.error) as error:
        parser.exit(1, f'Refused: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
