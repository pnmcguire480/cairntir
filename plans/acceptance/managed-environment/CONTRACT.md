# Managed executable invocation environment: finite independent acceptance

Frozen before implementation of this amendment, 2026-10-04. Three tests, no new
feature or routing/provider change. Existing crash/no-replay acceptance remains
unchanged. Existing frozen files and coverage thresholds must remain unchanged.

1. Keep the operator-configured complete argv, including its executable invocation
   path, byte-for-byte; do not mutate the input configuration. Separately bind the
   executable's canonical target identity and existing byte hash into internal
   configuration. Two different canonical targets with identical bytes must
   produce different normalized configurations. No particular new field name is
   mandated.
2. After actual synthetic capture, fresh brief and acknowledgement, retargeting
   an executable alias to another canonical target with identical bytes must
   produce a typed ManagedRuntimeError before any Popen call or durable write.
   Both inert alias controls run cross-platform with one narrowly mocked
   Path.resolve mapping; no real executable is launched by those controls.
3. On hosted POSIX runners, create an isolated temporary venv using the standard
   library with_pip=False and symlinks=True; write one uniquely named pure Python
   module into that temporary venv only. A direct interpreter invocation must
   report the expected prefix and module origin/token. Invoking the canonical
   target must fail to find this module (negative control). A real managed child
   must match the direct configured invocation's prefix, origin and token.
   No packages, models, network, host configuration or production stores involved.

Run the two inert tests locally with the existing dev interpreter and candidate
src on PYTHONPATH, serially. Windows explicitly skips only the POSIX test. Hosted
Linux/macOS must run all three without skips; symlink fixture failure is a test
failure there, not a reason to silently skip environment proof. Use isolated
HOME/config/cache and PYTHONDONTWRITEBYTECODE=1. No full local suite is authorized
by this contract. Baseline should fail invocation preservation; its same-byte
retarget guard should already pass. A naive argv-preservation-only repair must
still fail the canonical-target binding/retarget controls.

These controls address environment correctness, not full-product coverage.
No fixture-only normalization, timeout relaxation, changed old expectations,
new package installation, or reduced coverage threshold is an acceptable repair.
Preserve baseline and candidate results and test hashes; changed hashes invalidate
the run. Qualification requires all existing no-replay tests and hosted gates as
well as this finite amendment. One implementation plus at most two repair rounds;
retain at least 25 percent verification effort.
