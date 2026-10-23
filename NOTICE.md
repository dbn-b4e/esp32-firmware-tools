# Licensing and provenance

The shared build tools and the OTA modules are distributed under MIT (LICENSE).
The OTA subtree preserves the original MIT notice and full Git history from
https://github.com/dbn-b4e/esp32C6-OTA-Builder at b505188.
The build engine was extracted from the author’s B4E firmware tooling;
no SxS firmware, credentials or device configuration is included.

`ota/image_builder_tool.py` is the unchanged Espressif reference script under
Apache-2.0, with its original SPDX/copyright header. See ota/NOTICE.md and
ota/LICENSES/Apache-2.0.txt. It is optional, requires zigpy and is not used by
our full/differential packaging pipeline.

Pinned detools and esptool are installed dependencies, not vendored source.
The on-device delta decoder is not part of this repository.


The generic Z2M descriptor generator and C6 demonstration are independently
implemented in this repository under MIT. No OpenZigbee source or configuration
was copied. The Arduino demonstration uses the public Arduino ESP32 3.3.4
Zigbee API. Its core/library dependencies retain their own upstream licenses.

The JavaScript runtime tests use zigbee-herdsman-converters 26.115.1 and its
locked npm dependencies as installed dependencies, not vendored source.
Node is only required for these tests. Serial capture optionally depends on
pyserial 3.5. Dependencies retain their respective upstream licenses.
