# Repository import classification

Version 1's frozen controls passed all 28 focused cases in 1.30 seconds, while
actual-repository lint identified one import-grouping error in the new control
file. Ruff invoked against the external packet had classified imports differently
from normal repository invocation. Version 2 only groups `test_recovery_outcomes`
with third-party imports and separates the first-party Cairntir block using the
actual repository configuration. No assertion, fixture input, test count, adapted
projection test or runtime changes. Original version-1 files, freeze and green
execution evidence remain under history/v1; this version is frozen before rerun.
