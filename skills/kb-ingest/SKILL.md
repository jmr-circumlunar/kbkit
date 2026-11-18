---
name: kb-ingest
description: Turn authorized files into source-linked Markdown knowledge pages.
kbkit-api-version: v1
---

# kbkit file ingestion

Use this Skill when the user provides files or an authorized directory and asks to create knowledge from them.

1. Confirm the source path, file types, destination vault, generated-content area and retention policy on first use. Reuse the saved scope for later scheduled runs.
2. Build a source manifest containing relative path, file hash, size, modification time and extraction status. Never treat the generated page as the source of truth.
3. Read supported text formats directly, including Markdown, plain text, JSON, YAML, CSV and source code. For PDF, office and image files, use the Agent host's authorized extractor and record the extractor and source hash.
4. Classify each source before writing. Preserve source files outside the vault unless the user explicitly asks to copy them.
5. Generate one or more concise Markdown pages in the configured generated area. Each page must include source references, source hash, extraction method, generated time, confidence and a link to the original file or repository location.
6. Keep code bodies, secrets, binaries and large logs out of the knowledge page. For code repositories, generate project structure, module responsibilities, public interfaces, setup and deployment steps, ADR and decision summaries, test and CI status, dependency and license facts, and change summaries.
7. Create new generated pages directly when generated-content mode is enabled. Do not overwrite an existing canonical page. A changed source creates a new diff or revision and marks the old generated page stale.
8. Run indexing and lint after ingestion. Report created, updated, skipped, stale and conflicted sources with their hashes.
