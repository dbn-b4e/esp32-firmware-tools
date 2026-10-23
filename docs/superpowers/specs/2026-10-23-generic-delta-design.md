# Generic differential OTA tools

Approved scope: bring the validated B4E differential generator into OTA-Builder as reusable tooling. Keep the existing firmware protocol byte-compatible. Do not flash devices, access HA, move private firmware into Git, push, or wire a submodule yet.

## Approach
Extract the generation/verification logic into a standalone Python CLI and importable module, with an explicit JSON device profile instead of B4E constants. Direct base/target binary inputs avoid importing private release layout. Preserve the 128-byte envelope, official Espressif patch header and heatshrink payload, exact base/target hashes, version floor/order, partition bounds, compiled model/version marker, ESP checksum/digest/chip checks, independent reconstruction and exact-base Z2M min/max constraints. Other approaches (copying the B4E scripts unchanged or rewriting the firmware protocol) leave hardcoded identities or require a new device bootstrap and are excluded.

Full OTA and differential OTA remain separate commands. A neutral example profile documents the required decoder contract; it does not claim stock Arduino supports this envelope. Only ESP32-C6 differential images are validated initially. No automatic chained updates or automatic full-image fallback.

Correct the full-image container/parsing checks needed by the new generator. Remove the bogus downloaded 404 file. Preserve Apache-2.0 copyright and add the corresponding license for the upstream Espressif script, distinct from our MIT code. Tests and CI use synthetic images; real private B4E binaries are local validation inputs only. The B4E repository and runtime remain untouched.
