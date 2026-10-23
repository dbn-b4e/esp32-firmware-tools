# Licensing and provenance

- `zigbee_ota_generator.py`, `delta_ota.py`, tests, examples and documentation
  are distributed under the repository's MIT license (`LICENSE`). The delta
  packaging/checks were extracted from the author's B4E ESP32-C6 firmware tools.
- `image_builder_tool.py` is the retained Espressif reference script. Its original
  copyright and SPDX headers remain intact:
  Copyright 2025 Espressif Systems (Shanghai) CO LTD, Apache-2.0.
  The Apache license text is in `LICENSES/Apache-2.0.txt`.
  Upstream project: https://github.com/espressif/esp-zigbee-sdk/tree/main/tools/image_builder_tool
  It depends on `zigpy` and is not used by our standalone CLI or delta pipeline.
- `detools` and `esptool` are installed dependencies, not vendored source. Their
  respective distributions include their own licenses. The official Espressif
  patch framing is documented in `docs/delta-format.md`; the on-device decoder
  is not bundled or relicensed by this project.

This repository does not contain device firmware binaries or credentials.
