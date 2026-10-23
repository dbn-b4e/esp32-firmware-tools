# Differential decoder contract (format version 1)

The generic tool preserves the format used by the B4E ESP32-C6 decoder. Profile
configuration changes identities and limits, not the binary layout. A device
must already implement the entire contract before any differential is offered.
The example profile does not install or configure a decoder.

## Envelope: 128 bytes, little-endian

| Offset | Size | Field |
|---|---:|---|
| 0 | 8 | Exact profile magic |
| 8 | 32 | ASCII model, zero-padded |
| 40 | 4 | Target OTA file version |
| 44 | 4 | Exact base OTA file version |
| 48 | 4 | Entire base application size |
| 52 | 4 | Entire target application size |
| 56 | 4 | Espressif patch size, including its 64-byte header |
| 60 | 4 | Reserved, zero |
| 64 | 32 | SHA256 of entire base application |
| 96 | 32 | SHA256 of entire target application |

The patch follows immediately. Its header contains `0xfccdde10` as uint32,
then the 32-byte **stored ESP digest** of the base and 28 zero bytes. The stored
ESP digest is different from the SHA256 of the complete application file.
At offset 192 begins the unmodified detools sequential patch using heatshrink
(compression type 4). Compatible versions are pinned in requirements-delta.txt.

Base/target application sizes are at least 24 and at most `slot_size`. Espressif
patch size is at least 65 and at most `slot_size - 128`. Envelope size must be
exactly `128 + patch_size`. Base version is at least `min_base_version`; target
version must be strictly greater. Versions are unsigned 32-bit values.

Every input must be an ESP32-C6 application (ESP magic `0xe9`, chip ID 13,
appended digest enabled) with valid ESP checksum and digest. The compiled image
must contain `struct.pack('<32sI', model.encode('ascii'), version)`. The tool
checks that marker along with the application hash and version. A firmware that
uses a different identification mechanism needs an explicitly reviewed adapter,
not disabled identity checks.

## Required on-device protections

A compatible receiver must independently verify the running base version,
model, full SHA256, size and ESP digest; stream reconstruction only into the
inactive OTA partition; enforce target/patch/partition bounds; check target
identity/version/SHA256 and ESP validity before selecting it for boot. Preserve
transport authentication, exclusive OTA ownership, timeouts/abort and the
platform's boot validation/rollback policy. Never trust index constraints alone.
This repository supplies no firmware decoder or transport implementation.

The Zigbee wrapper is 60 header bytes plus a 6-byte upgrade-image subelement
header followed by the envelope. Header Total Image Size includes all bytes.

References:
- https://components.espressif.com/components/espressif/esp_delta_ota
- https://github.com/eerimoq/detools
- https://github.com/espressif/esp-zigbee-sdk/tree/main/tools/image_builder_tool
- https://github.com/Koenkk/zigbee-OTA#allowed-fields
