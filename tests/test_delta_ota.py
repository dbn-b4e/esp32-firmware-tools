import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from esptool.bin_image import ESP32C6FirmwareImage, ImageSegment


class DeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path('tmp').mkdir(exist_ok=True)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('delta_ota'), 'Generic delta module is missing')
        return importlib.import_module('delta_ota')

    def profile(self, **changes):
        fields = dict(name='example', model='EXAMPLE_C6_V1', envelope_magic=b'ESPDLT1\0',
                      min_base_version=3, slot_size=0x1c0000, manufacturer_code=0x1049,
                      image_type=1)
        fields.update(changes)
        return self.api().DeltaProfile(**fields)

    def image(self, p, version, model='EXAMPLE_C6_V1'):
        image = ESP32C6FirmwareImage()
        image.chip_id = 13
        image.entrypoint = 0x40800000
        body = struct.pack('<32sI', model.encode(), version) + bytes(range(256)) * 20
        segment = ImageSegment(0x40800000, body)
        segment.name = '.data'
        image.segments = [segment]
        image.save(str(p))

    def pair(self, root):
        base, target = root / 'base.bin', root / 'target.bin'
        self.image(base, 3)
        self.image(target, 5)
        return base, target

    def make(self, root):
        base, target = self.pair(root)
        output = root / 'delta'
        m = self.api().make_delta(base, target, 3, 5, output, self.profile())
        return base, target, output, m

    def test_can_skip_versions_and_reconstruct_target(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            root = Path(tmp)
            base, target, output, m = self.make(root)
            verified = self.api().verify_delta(output, base, target, self.profile())
            self.assertEqual(verified, m)
            self.assertEqual(m['base_version'], 3)
            self.assertEqual(m['version'], 5)
            self.assertLess(m['size'], m['target_size'])
            self.assertEqual(m['target_sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
            idx = json.loads((output / 'z2m-index.json').read_text())[0]
            self.assertEqual((idx['minFileVersion'], idx['maxFileVersion']), (3, 3))

    def test_refuses_prebootstrap_and_reversed_versions_without_output(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            root = Path(tmp)
            base, target = self.pair(root)
            for bv, version in [(2, 5), (3, 3), (5, 3)]:
                with self.subTest(base=bv, target=version), self.assertRaises(ValueError):
                    self.api().make_delta(base, target, bv, version, root / 'delta', self.profile())
                self.assertFalse((root / 'delta').exists())

    def test_refuses_wrong_identity_checksum_chip_and_size(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            root = Path(tmp)
            base, target = self.pair(root)
            original = base.read_bytes()
            for offset in (0, 12, len(original) - 1):
                bad = bytearray(original)
                bad[offset] ^= 1
                base.write_bytes(bad)
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    self.api().make_delta(base, target, 3, 5, root / 'delta', self.profile())
                self.assertFalse((root / 'delta').exists())
            base.write_bytes(original)
            for profile in [self.profile(model='OTHER_MODEL'), self.profile(slot_size=256)]:
                with self.assertRaises(ValueError):
                    self.api().make_delta(base, target, 3, 5, root / 'delta', profile)
            with self.assertRaises(ValueError):
                self.api().make_delta(base, target, 4, 5, root / 'delta', self.profile())

    def test_refuses_existing_output_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            base, target, output, m = self.make(Path(tmp))
            before = (base.read_bytes(), target.read_bytes(), (output / m['delta_file']).read_bytes())
            with self.assertRaises((ValueError, FileExistsError)):
                self.api().make_delta(base, target, 3, 5, output, self.profile())
            self.assertEqual(before, (base.read_bytes(), target.read_bytes(), (output / m['delta_file']).read_bytes()))

    def test_rejects_all_envelope_and_patch_corruption(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            base, target, output, m = self.make(Path(tmp))
            patch = output / m['delta_file']
            original = patch.read_bytes()
            for offset in [0, 8, 40, 44, 48, 52, 56, 60, 64, 96, 128, 132, 164, 192, len(original) - 1]:
                bad = bytearray(original)
                bad[offset] ^= 1
                patch.write_bytes(bad)
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    self.api().verify_delta(output, base, target, self.profile())
            patch.write_bytes(original[:-1])
            with self.assertRaises(ValueError):
                self.api().verify_delta(output, base, target, self.profile())

    def test_rejects_manifest_index_ota_and_base_tampering(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            base, target, output, m = self.make(Path(tmp))
            for filename in ['delta-manifest.json', 'z2m-index.json', m['zigbee_file']]:
                p = output / filename
                old = p.read_bytes()
                if filename == 'delta-manifest.json':
                    data = json.loads(old)
                    data['delta_file'] = '../base.bin'
                    p.write_text(json.dumps(data))
                elif filename == 'z2m-index.json':
                    data = json.loads(old)
                    del data[0]['minFileVersion']
                    p.write_text(json.dumps(data))
                else:
                    p.write_bytes(old[:-1])
                with self.subTest(filename=filename), self.assertRaises(ValueError):
                    self.api().verify_delta(output, base, target, self.profile())
                p.write_bytes(old)
            other = Path(tmp) / 'other.bin'
            self.image(other, 3, model='OTHER_MODEL')
            with self.assertRaises(ValueError):
                self.api().verify_delta(output, other, target, self.profile())

    def test_profile_rejects_invalid_values(self):
        for changes in [dict(model='x'*33), dict(model='a\0b'), dict(envelope_magic=b'short'),
                        dict(name='../escape'), dict(image_type=65536), dict(slot_size=True),
                        dict(min_hardware_version=2, max_hardware_version=1)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.profile(**changes)

    def test_generic_envelope_matches_original_b4e_layout(self):
        import detools
        api = self.api()
        profile = self.profile(model='B4E_ZONE_NODE_C6_V1', envelope_magic=b'B4EDLT1\0',
                               min_base_version=0x10003, image_type=0xb4e1)
        base = bytes(range(256))*16
        target = base + b'changed'
        raw = io.BytesIO()
        detools.create_patch(io.BytesIO(base), io.BytesIO(target), raw, compression='heatshrink')
        official = struct.pack('<I', 0xfccdde10) + bytes(range(32)) + bytes(28) + raw.getvalue()
        expected = struct.pack('<8s32s6I32s32s', b'B4EDLT1\0', b'B4E_ZONE_NODE_C6_V1',
                               0x10004, 0x10003, len(base), len(target), len(official), 0,
                               hashlib.sha256(base).digest(), hashlib.sha256(target).digest()) + official
        self.assertEqual(api.envelope(base, target, 0x10003, 0x10004, official, profile), expected)
