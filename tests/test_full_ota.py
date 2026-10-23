import contextlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

from zigbee_ota_generator import ZigbeeOTAGenerator


class FullOTATests(unittest.TestCase):
    def generate(self, root, compatible=False):
        source = root / 'firmware.bin'
        source.write_bytes(bytes(range(256)))
        target = root / 'firmware.ota'
        args = SimpleNamespace(input=source, output=target, header_string='Example C6',
                               espressif_compatible=compatible, manufacturer_code=0x1049,
                               image_type=1, file_version=2, stack_version=2,
                               min_hardware_version=1, max_hardware_version=1)
        with contextlib.redirect_stdout(io.StringIO()):
            ZigbeeOTAGenerator().generate_ota_file(args)
        return args, target.read_bytes()

    def parse(self, data, root):
        p = root / 'parse.ota'
        p.write_bytes(data)
        with contextlib.redirect_stdout(io.StringIO()):
            return ZigbeeOTAGenerator().parse_ota_file(p)

    def test_default_total_includes_header(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            _, data = self.generate(Path(tmp))
            self.assertEqual(struct.unpack_from('<I', data, 52)[0], len(data))

    def test_espressif_compatible_bytes_remain_stable(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            _, data = self.generate(Path(tmp), True)
            expected = struct.pack('<IHHHHHIH32sIHHHI', 0x0beef11e, 0x100, 60, 4,
                                   0x1049, 1, 2, 2, b'Example C6', 322, 1, 1, 0, 256)
            self.assertEqual(data, expected + bytes(range(256)))
            self.assertTrue(self.parse(data, Path(tmp)))

    def test_rejects_truncated_payload(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            _, data = self.generate(Path(tmp), True)
            self.assertFalse(self.parse(data[:-1], Path(tmp)))

    def test_rejects_false_total_and_header_length(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            _, data = self.generate(Path(tmp), True)
            for offset, fmt, value in [(52, '<I', 1), (6, '<H', 65535), (8, '<H', 0)]:
                with self.subTest(offset=offset):
                    bad = bytearray(data)
                    struct.pack_into(fmt, bad, offset, value)
                    self.assertFalse(self.parse(bad, Path(tmp)))

    def test_rejects_empty_duplicate_upgrade_element(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            _, data = self.generate(Path(tmp), True)
            for offset in (60, len(data)):
                bad = bytearray(data[:offset] + struct.pack('<HI', 0, 0) + data[offset:])
                struct.pack_into('<I', bad, 52, len(bad))
                with self.subTest(offset=offset):
                    self.assertFalse(self.parse(bad, Path(tmp)))

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            args, data = self.generate(Path(tmp), True)
            with self.assertRaises((ValueError, FileExistsError)):
                ZigbeeOTAGenerator().generate_ota_file(args)
            self.assertEqual(args.output.read_bytes(), data)

    def test_refuses_input_as_output(self):
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            args, _ = self.generate(Path(tmp), True)
            before = args.input.read_bytes()
            args.output = args.input
            with self.assertRaises((ValueError, FileExistsError)):
                ZigbeeOTAGenerator().generate_ota_file(args)
            self.assertEqual(args.input.read_bytes(), before)

    @classmethod
    def setUpClass(cls):
        Path('tmp').mkdir(exist_ok=True)
