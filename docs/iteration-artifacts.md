# Iteration artifacts

The unpublished candidate can attach producer-supplied STL and G-code files to an existing remembered iteration. Complete bytes, an immutable reference, their SHA-256, size and saved date live in the same SQLite database. The original drawer content and access metadata are preserved.

Use `IterationArtifactBook(store)` from `cairntir.iteration_artifacts`. Call `attach(iteration_id, Path(...), kind="stl")` or `kind="gcode"`, then retain its `artifact_id`. `list_for_iteration(iteration_id)` returns saved references; `read(iteration_id, artifact_id)` returns the reference and verified `data` bytes. Labels are simple filenames whose extension matches the declared kind. Producer paths are not retained.

Files must be nonempty regular local files, at most 64 MiB. A caller can set a smaller positive `max_bytes`. Linked paths and files changed during reading are refused. Identical parent/kind/label/bytes reuse the original reference; different bytes under that key return `ATTACHMENT_CONFLICT`. Choose a new label for a distinct artifact.

Deleting the producer file does not remove the saved bytes. Missing saved bytes raise `ARTIFACT_MISSING`; bytes that no longer match the saved size and hash raise `ARTIFACT_CORRUPT`. The parent and reference remain available. A wrong parent/artifact pair returns `ARTIFACT_NOT_FOUND`.

The reference and BLOB commit atomically. Attachment tables are created only by an explicit successful writable attach. Read-only access never creates tables or updates access counters. A scoped store requires read and write authority for attachment, and read authority for listing or retrieval; its live grant is checked at the boundary.

A full SQLite online backup retains the attachment tables and complete bytes. Portable JSON bundles do not include these attachments. This Python API does not add automatic Blender capture, slicer execution, a new CLI/MCP tool, or proof of a physical print.
