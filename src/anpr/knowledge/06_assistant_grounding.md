# Assistant behaviour and grounding

## Two kinds of questions

The assistant handles **data questions** ("how many plates were read today?", "show me the failed readings") and **technical questions** ("why did this plate fail?", "what does CLAHE do?", "why is the OCR score not a probability?"). Data questions are answered by SQL queries against the local database. Technical questions use retrieval over the Markdown documents in this folder.

## Grounding rules

1. Never invent a count, plate number, filename, or score. If the database has no rows, say so and suggest uploading an image.
2. Quote the review status exactly: a reading that passed the gate is a **candidate** that passed a validation-selected rule, not a confirmed plate.
3. Call the OCR score an engine score or ranking signal, never a probability.
4. When explaining a specific plate, use its stored quality flags, retry reasons, candidate list and selection reason. Do not diagnose a cause that is not present in the record.
5. If the user asks for a plate that is not in the database, say it was not found and offer the closest text matches.
6. Distinguish live rows from demo rows. Demo rows are synthetic and labelled `source='demo'`.

## LLM mode

When `AUTOGUARD_LLM_API_KEY` is set (OpenAI-compatible endpoint) or an Ollama instance is connected (via `AUTOGUARD_OLLAMA_URL` or the assistant page's in-app detector), the assistant sends a compact context block to the model and asks it to rewrite or answer using only that block. The context contains aggregate numbers and at most a handful of matching plate rows, never the uploaded image. If the model call fails or times out, the deterministic local answer is returned and the response mode is marked as a fallback.

When no model is configured, the assistant still works: intent routing, SQL retrieval, and BM25 retrieval produce a grounded answer. This is intentional so the capstone can be demonstrated offline and so the LLM is an enhancement, not a single point of failure.

## Suggested questions

- How many vehicles were analysed today?
- Show me the plates that need manual review.
- Which readings had low OCR confidence?
- Show me the recovered plates.
- Why did plate 12 fail?
- What preprocessing was applied to the last failed reading?
- What is the review gate and how accurate is it?
- What are the most common failure reasons this month?
- Explain the difference between exact match and character error rate.
- What happens to my uploaded image?
