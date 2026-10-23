# Generic delta OTA extraction review

## Result

The profile-driven extraction preserves the previous B4E envelope byte layout and safety checks. Full OTA and differential CLI paths are separate. The B4E firmware repository, production devices and HA/Z2M configuration were not modified. No push or publication was performed.

## Validation

- 19 local unittest cases pass, including invalid ESP images, duplicate upgrade elements, base version/identity/partition guards, overwritten outputs, corrupted envelope/manifest/index/container, independent reconstruction with refreshed malicious metadata, and bounded decompression.
- Full CLI create/parse and differential CLI create/verify exercised with generated synthetic ESP32-C6 images and the public example profile.
- Extraction recreated the archived successful B4E v1.0.3→v1.0.4 differential payload (24695 bytes) and Zigbee OTA container (24761 bytes) byte for byte. Real streaming C decoder reconstructed the exact target with 1/4/50/1024-byte input blocks. Firmware images remain private, ignored artifacts.
- No new physical OTA/power-loss test was performed. The checked-in CI configuration has not yet run remotely; Python 3.10 was inspected for syntax compatibility but not executed locally (local tests use Python 3.13).
- A targeted scan of historical Git blobs found no GitHub token, private key, AWS access key or JWT pattern. This is not a guarantee that every possible secret has been detected. No firmware binaries or private validation artifacts are tracked.

## Independent fidelity audit

Old functions were compared against the new profile-driven implementation. Preserved: magic/model/version floor and order, application/patch/partition bounds, reserved fields, heatshrink format, full base/target hashes, stored ESP digest and checksum, compiled model/version identity, reconstruction equality, exact OTA wrapper and SHA512, exact-source-version Z2M index constraints.

The generic API accepts application binaries directly. Existing B4E release-manifest/full-OTA/LittleFS checks remain the B4E adapter's responsibility, and that adapter has not yet been changed. A future pinned-submodule migration must keep verify_release before delegating generation.

No internal threads or global mutable configuration: frozen profile and per-call buffers. Global os.umask mutation was removed. Exclusive file/directory creation prevents replacing existing artifacts. An I/O error may leave an incomplete new output directory; only publish artifacts after successful verification.

## Independent final review and fixes

Two additional cases were found. They were graded important for a strict public verifier and fixed with failing-then-passing regression tests:

1. Bound reconstruction to the declared, validated target size before allocating the output (previously a hostile compressed patch could exceed the limit before final comparison).
2. Reject duplicate upgrade-image tags even when one payload is empty.

Earlier fidelity review also led to exact ESP image-length validation (including a repeated-digest suffix case), clean rejection of esptool truncation errors, and a test proving independent reconstruction remains enforced after metadata is refreshed.

## Scope and local workflow decisions

A project-local ignored Git worktree was used because the native task worktree API was attached to another checkout. The final feature branch is made available in the canonical project checkout. Private validation output is retained under the project's ignored tmp directory. No existing B4E release files were moved or changed.

Deferred minor findings: none. Remaining integration work is explicit scope: review/push this feature branch, then wire the B4E adapter to a pinned public commit without losing release checks. Automatic delta chains, automatic full fallback, decoder firmware distribution, signing and other chips are not implemented.
