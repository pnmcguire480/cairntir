# Actual PALADIN Python source controls

Three original methods retain five deliberate defect subtests and sixteen real
stage executions. Their unchanged shared fixture enforces 95% subject coverage,
60-second stages, 1 MiB output limits, new repair slots and old evidence bytes.
The ten generic text fixtures are byte-exact. INPUTS.json explicitly omits only
three generated private Ruff-cache artifacts from a new public input manifest;
old freezes and results remain unchanged.

Existing Q05 inputs contain only Python/Ruff/uv. Execution additionally requires
a fresh owned seven-tool PALADIN profile, stage-commands.json and qualified
current CI-extra RECORD closure. Local preparation has passed its six controls;
the portable entry point also prepares fresh inputs successfully. Hosted
execution remains open. The adapter neither installs tools
nor copies an entire environment.
Missing inputs fail explicitly, without skips or fabricated tool results.

After Q05 preparation, run with the same selected CI-extra environment:

```sh
python -I -B tests/acceptance/paladin_python_real_unit/prepare.py --output /absolute/fresh/python-tools --q05-platform /absolute/q05-tools/platform.json --repo /absolute/checkout
```

Set CAIRNTIR_PALADIN_PLATFORM to the resulting platform.json and retain
CAIRNTIR_Q05_PLATFORM. Preparation refuses an existing output directory.

The intended preparation reuses Q05's actual Python/Ruff/uv and six official
backend wheels plus the current platform's selected thirteen distributions
(fourteen on Windows). Current local packaging26.0 differs from uv.lock26.3;
local observations must state26.0 and never claim exact current-lock parity.
The adapter checks only input bindings and actual version/import origins. It
does not qualify the RECORD-copy closure or recheck Q05's complete shared
runtime. Those independent preparation/preservation checks remain required.
Expected versions come from current selected distribution metadata and an
independent prepared-interpreter origin/version probe, not product receipts.

The ordinary adapter temporarily rebinds shared fixture data location and
input-platform path during construction. Afterward, each fixture's own scratch
directories receive TEMP/TMP, HOME/USERPROFILE, LOCALAPPDATA/APPDATA and UV_CACHE_DIR.
The existing plan and live process share those same environment values; a
case-cleaned explicit environment patch restores the caller afterward. Actual
build temp/cache writes therefore remain outside the prepared input inventory.
Shared fixture source, original methods, text inputs and stage template stay unchanged.
For unit/integration commands, the adapter binds pytest's pythonpath to ../src,
relative to acceptance/pytest.ini. This avoids pytest's shell-style parsing of
native Windows backslashes while preserving the same snapshot source directory.
Nested subject tests are data excluded from outer collection/global lint; their
original lint/type/test commands still execute against the exact snapshots.
No old sealed qualification transfers. Source and static checks alone do not
qualify the unprepared tool profile or imply coverage/release readiness.
