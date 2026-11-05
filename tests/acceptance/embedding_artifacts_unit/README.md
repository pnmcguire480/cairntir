# Pinned embedding artifact tests

Carried from draft PR 125. They protect model-artifact identity, pinned loading,
legacy index handling and refusal without acquisition, using a synthetic model and
disposable folders. They never download a model.

`MANIFEST.json` and `SOURCES.json` in `plans/acceptance/alpha-portable-tests-20261105`
record each test's origin and every change made while carrying it across.
