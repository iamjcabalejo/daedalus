# Probe testdata (synthetic)

Everything in this folder is **synthetic**. It was built from made-up payloads by the real `redact.py` and `observe.py` pipeline, never captured from a host. The host version `0.0.0-synthetic` marks it as such. `scripts/test-probes.sh` uses these files to check:
- the fixture and result formats against `bench/schema/probe-fixture.schema.json` and `bench/schema/probe-result.schema.json`;
- the leak scan, which runs over this folder as well as `../fixtures/`.

- `fixtures/claude-0.0.0-synthetic/A1/script/*.json`: a redacted A1 capture (prompt, spawn, subagent start and stop, Read, Bash, Stop).
- `results/claude-0.0.0-synthetic.json`: the matching `daedalus.probe-result/1` file. Its status is `confirmed` because the synthetic capture was built to satisfy A1.

Raw (unredacted) synthetic inputs are never stored here. Tests that need them build them in memory, so this folder always passes the leak scan.
