# Bootstrap refusals before tool dispatch

These seven existing Q07 cases use temporary project copies, the original public
requirements lock, the current interpreter and available uv executable. Their
wheel directory is intentionally empty: they must refuse invalid inputs before
reading a valid wheel set or launching any tool. Subprocess and network calls
are forbidden by the local fixture. The nested clean-project tests are input
data, so only the package's fixture directory is excluded from collection.

The first local source run passed all seven cases. It transfers no earlier
acceptance result and proves no installation, real-wheel, replay or subject
test-execution capability. Those checks live in `bootstrap_real_unit`.
