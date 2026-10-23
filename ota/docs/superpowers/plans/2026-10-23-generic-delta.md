# Generic differential OTA implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add reusable, verified ESP32-C6 differential OTA generation without changing the B4E device protocol.
**Architecture:** Existing full OTA generator plus generic profile-driven delta module/CLI; synthetic tests and private byte-level compatibility verification.
**Tech Stack:** Python 3.10+, unittest, detools 0.53.0, esptool 5.2.0.
**Spec:** docs/superpowers/specs/2026-10-23-generic-delta-design.md

## Global Constraints
- Preserve all safety checks and byte format documented in the spec.
- No private binaries, credentials, production changes or push.
- Use an isolated worktree. Do one verified change at a time.

## Review Focus
- Malformed/truncated containers must fail, including optional header fields.
- Same version but wrong binary/model/chip must fail.
- Outputs must not replace inputs or existing releases.
- Tampered manifest/index/patch must fail independent verification.
- B4E format, bounds, identity marker and source-version constraints must survive extraction.

## Task 1: Validate full OTA containers
- [x] Add failing tests for standard total size, truncated element, mismatched size, header bounds and overwrite protection; run `python3 -m unittest discover -s tests -v`. Expected: failures expose the old behavior.
- [x] Correct generator/parser while retaining CLI and the Espressif-compatible byte output; rerun full suite. Expected: pass.
- [x] Commit the tested fix.

## Task 2: Extract profile-driven differential tools
**Interfaces:** `delta_ota.py` exports `DeltaProfile`, `parse_envelope(data, profile)`, `envelope(base, target, base_version, version, patch, profile)`, `make_delta(base, target, base_version, version, output, profile)`, `verify_delta(root, base, target, profile)`. CLI `create` and `verify` receive `--profile`, `--base`, `--target`, `--output`; create also requires versions. A profile defines name/model/magic/minimum base/slot size/OTA identity/hardware bounds.
- [x] Add failing tests using synthetic valid ESP32-C6 images and corruption/parameter cases; run suite. Expected: missing implementation fails.
- [x] Implement preserved binary protocol, checks, reconstruction and constrained index; pin delta dependencies. Expected: suite passes using the existing B4E venv.
- [x] Verify generated B4E .delta.bin and .ota against archived v1.0.3→v1.0.4 files locally; exercise real firmware C decoder. No private input is committed.
- [x] Commit extraction.

## Task 3: Document public use and review fidelity
- [x] Replace inaccurate README with tested full/delta commands, profile contract and limitations; remove 404 file, clarify MIT/Apache licensing, add synthetic CI.
- [x] Run full suite and CLI help/examples. Expected: pass; no firmware or device dependency in ordinary tests.
- [x] Ask independent reviewer to compare old B4E and new generic functions for every guard, simplification and validation. Resolve important findings via RED→GREEN tests.
- [x] Commit final review/docs; leave a clean local feature branch ready for user review before publication.
