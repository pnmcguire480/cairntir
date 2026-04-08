---
description: Think through a question using memory-backed retrieval.
---

Use Cairntir's `reason` skill to think about the user's question with the help of stored memory.

1. Call `cairntir_session_start` to load the 4-layer context for the current wing
2. Call `cairntir_recall` to retrieve memories specifically relevant to the question
3. Reason out loud with the retrieved memories in view — cite drawer ids inline
4. Propose an answer, and flag any assumptions that should be stress-tested by `cairntir_crucible`

$ARGUMENTS
