# ESP32 Zigbee OTA Builder

Create and inspect full Zigbee OTA containers, or generate a verified differential
update between two exact ESP32-C6 application binaries.

- Full OTA container generation/inspection uses Python's standard library.
- Differential generation uses pinned `detools` and `esptool` versions.
- Every delta is applied independently on the host and compared byte for byte
  with the target before its package is accepted.
- Z2M indexes restrict a delta to its exact source version. The firmware must
  also check the exact source binary hash.

**A differential file requires compatible firmware already running on the
ESP32-C6.** This repository provides host tools and the protocol contract, not a
stock Arduino OTA client. Full OTA packaging is chip-agnostic; differential
image validation is currently ESP32-C6 only. No devices are contacted by these
commands.

## Installation

Python **3.10 or newer** is required.

```sh
git clone https://github.com/dbn-b4e/esp32C6-OTA-Builder.git
cd esp32C6-OTA-Builder
python3 zigbee_ota_generator.py --help
```

For differential updates, install dependencies in a local environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-delta.txt
```

On Windows use `.venv\Scripts\python.exe`. If a dependency has to compile from
source on macOS, install/use the Xcode command-line toolchain and matching SDK
headers for that Python architecture; do not change the pinned versions merely
to suppress a compiler error.

## Full Zigbee OTA image

Use an **application** `.bin`, not a merged flash dump, bootloader or filesystem
image. The container builder wraps bytes; only the delta pipeline validates ESP
application structure/checksums.

```sh
python3 zigbee_ota_generator.py create \
  --input firmware.bin --output firmware.ota \
  --manufacturer-code 0x1049 --image-type 0x0001 \
  --file-version 0x00000005 --header-string "Example C6" \
  --espressif-compatible

python3 zigbee_ota_generator.py parse firmware.ota
```

Match manufacturer, image type, hardware bounds and version to your device.
Output files must not exist, and input/output must be different. A successful
`parse` validates the OTA **container**, not the firmware's authenticity or its
suitability for your device.

Both padding modes now write the correct Total Image Size, including the whole
OTA header. `--espressif-compatible` preserves the zero-padded output used with
Espressif; omitting it uses `0xff` header text padding. Older releases incorrectly
excluded the header in the default mode; such files are now rejected rather
than called valid. See [migration notes](docs/migration.md).

## Differential update

Keep the **exact** application binary from every released build. Recompiling the
same source can produce a different binary and therefore an incompatible base.
A delta may go directly from version 1 to 5; versions 2, 3 and 4 are not required.

Copy and adapt [the example profile](examples/esp32c6-profile.json). Its values
are illustrative, not a universal ESP32 configuration. In particular:

- `model` and the eight-byte `magic_hex` must match the installed decoder.
- `min_base_version` is the first firmware version containing that decoder.
- `slot_size` must match the inactive application partition.
- Every application must include the compiled `<32sI` model/version marker
  described in [the decoder contract](docs/delta-format.md).
- OTA identity and hardware bounds must match the device's Zigbee OTA client.

```sh
.venv/bin/python delta_ota.py create \
  --profile examples/esp32c6-profile.json \
  --base firmware-v1.bin --base-version 0x00000001 \
  --target firmware-v5.bin --target-version 0x00000005 \
  --output build/v1-to-v5

.venv/bin/python delta_ota.py verify \
  --profile examples/esp32c6-profile.json \
  --base firmware-v1.bin --target firmware-v5.bin \
  --output build/v1-to-v5
```

The destination directory must not exist. Generated files are private by default
(directory mode `0700`, files `0600`, subject to platform permission semantics):

| File | Use |
|---|---|
| `*.delta.bin` | Custom decoder input, for example through a matching WiFi OTA endpoint |
| `*.delta.ota` | The same delta inside a Zigbee OTA container |
| `delta-manifest.json` | Base/target versions, sizes, SHA256, ESP digest, OTA SHA512 and profile |
| `z2m-index.json` | Exact source-version constraints (`minFileVersion == maxFileVersion`) |

Verification checks the complete base/target application hashes, ESP checksum
and digest, chip ID, model/version marker, envelope bounds, reserved fields,
patch format, exact reconstruction, manifest, OTA wrapper and index. A matching
version number alone does not establish compatibility. SHA hashes provide
integrity checks, **not a digital signature**.

### Zigbee2MQTT deployment

The generated index uses package-local filenames. For deployment, prepare a
**separate copy** of the index with each `url` changed to an accessible HTTP(S)
URL or a path resolved by your Z2M installation. Keep the original package for
`verify`, which deliberately requires unchanged metadata. Configure your custom
index following the [Z2M OTA documentation](https://www.zigbee2mqtt.io/guide/usage/ota_updates.html).

Keep a full OTA image available through a **separate full-image index** as a
fallback. Neither this tool nor Z2M automatically falls back from a failed delta,
computes a route across versions, or chains several updates. Do not put a delta
and a full image with ambiguous matching criteria into one deployment index.
Do not modify an image/index while an update is in progress.

## Validation and limits

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests generate synthetic ESP32-C6 binaries locally, cover corrupted inputs and
metadata, and do not need HA, a board or private firmware.

During extraction, the generated differential payload and OTA container were
also compared with a previously successful ESP32-C6 update: **byte-identical**.
The real streaming C decoder reconstructed the exact target with 1, 4, 50 and
1024-byte input blocks. These checks establish compatibility with that decoder;
they do not certify arbitrary firmware or power-loss recovery. No new physical
OTA was performed for this extraction. Private validation binaries are excluded
from Git.

## Files and licensing

- `zigbee_ota_generator.py`: full OTA builder/parser, MIT.
- `delta_ota.py`: differential builder/verifier, MIT.
- `image_builder_tool.py`: retained Espressif reference, Apache-2.0; requires
  `zigpy` separately and is not needed for the commands above.

See [LICENSE](LICENSE), [NOTICE.md](NOTICE.md) and
[the Apache license](LICENSES/Apache-2.0.txt). The old
`esp_zigbee_ota_file_tool.py` download contained only `404: Not Found` and has been
removed.
