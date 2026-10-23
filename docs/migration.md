# Migration from the original OTA Builder

The existing `zigbee_ota_generator.py create/parse` command names and parameters
remain. There are intentional safety changes:

- Both modes include the entire OTA header in Total Image Size. Earlier default
  output with a payload-only total must be regenerated.
- Existing output files are never overwritten; choose a new path or explicitly
  remove the old file after checking it is safe.
- Invalid/truncated headers, payloads, totals and hardware ranges are rejected.
- Header labels longer than 32 UTF-8 bytes are rejected, not silently truncated.
- Python 3.10+ is required; the former Python 3.6 claim no longer applies.
- `parse` checks container structure and does not claim firmware authenticity.

Differential tooling takes exact base/target application binaries plus an
explicit JSON profile. It does not consume B4E release manifests, validate
LittleFS, or prepare HA-specific deployment bundles. Those checks stay in the
firmware project's release workflow. The B4E firmware/release pipeline has not
been switched to this repository by this extraction; a pinned submodule can be
wired after the generic tools are reviewed and published.

Do not copy firmware archives into this public repository. Full application
images may contain network credentials even when their source repository does
not. Preserve exact release binaries separately in private storage.
