# Probe fixtures

Redacted hook payloads captured by `scripts/probes/run-probes.sh`. Real fixtures arrive with the live runs in P0b. Until then this folder holds only this file. Synthetic samples live in `../testdata/`.

- **Layout:** `<host>-<version>/<case>[.<variant>]/<install>/<event>-<n>.json`, in the `daedalus.probe-fixture/1` format (`bench/schema/probe-fixture.schema.json`). `n` counts per event; `seq` inside the file is the capture-wide order.
- **How they get here:** written only by `redact.py`, then copied by the runner after the post-run isolation check and the leak scan pass. Never hand-edit a fixture, and never copy a raw `out/raw/*.jsonl` file here.
- **Guard:** `scripts/test-probes.sh` scans this folder on every run (and in CI) and fails on any of these:
  - a home path, a macOS temp path, an email or a UUID;
  - unredacted prompt, message or tool text;
  - command text past the first word;
  - an id that isn't a placeholder;
  - any `.jsonl` file.
  It also validates every fixture against the schema.
- **Consumers:** P1 and P2 guard tests read these payloads as the host's real shapes. Placeholders (`<SESSION-1>`, `<AGENT-2>`) are stable within one capture, so equality checks still work.
