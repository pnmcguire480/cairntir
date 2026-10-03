# Same invalid-bootstrap finding in a recognized Hub layout

One finite repair-delta control applies the already-frozen no-invalid-acquisition assertion to a recognized Hub snapshot instead of the original fallback layout. Its positive phase loads the complete selected snapshot with exact pinned/local-only construction. Its negative phase removes the selected model file and makes tokenizer.json a directory, then uses the original unchanged `refuse_without_acquisition` assertion. The mock cache resolver models the real Hub contract: an absent model cache entry returns None. No network or actual inference is used.

This tests the same missing-file-masks-invalid-file pattern reported before repair, whose initial review explicitly required consistency across Hub snapshots and fallback layouts. It adds no new product behavior or broad gate. Freeze before execution and any second repair; preserve the initial repair1 failure if reproduced.
