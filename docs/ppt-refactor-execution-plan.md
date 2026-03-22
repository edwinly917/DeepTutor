# DeepTutor-1 PPT Refactor Execution Plan

## Context

- Repo: `DeepTutor-1`
- Base branch: `codex/ppt-image-semantic-generation`
- Execution branch: `codex/ppt-refactor-execution-plan`
- Execution worktree: `/Users/bytedance/DeepTutor-1-ppt-refactor-execution`
- Goal: execute the PPT refactor in a way that preserves current branch contracts while closing the remaining spec gaps.

## Locked Decisions

- Baseline branch stays `codex/ppt-image-semantic-generation`.
- Do not preserve legacy `idea` / `outline` / `descriptions` PPT creation modes.
- Do not preserve the old `markdown -> PPTGenerator` PPT generation path.
- Centralize PPT prompts in a dedicated prompt manager, borrowing the organizational pattern from `banana-slides`.
- `from_sources` uses a create-time frozen snapshot. Do not make report content depend on runtime re-fetch by default.
- `source_refs` is expanded to:

```ts
type SourceRef = {
  type: "report" | "web" | "kb" | "paper" | "file";
  title: string;
  url?: string;
  source_key?: string;
  content?: string;
};
```

- For `report`, `content` is required and must be frozen at project creation time.
- For `web` and `kb`, `content` is optional in this phase.
- `paper` and `file` stay unsupported in this phase and must surface user-visible warnings.
- Do not introduce `OUTLINE_READY` in this phase.
- After page edits, the canonical page state is `is_dirty=true` and `status="DRAFT"` until regeneration finishes.
- `SlideEditor.chat()` is the auto-regeneration path.
- `PUT /projects/{id}/pages/{page_id}` remains a low-level patch API. It updates fields and marks the page dirty, but does not silently trigger regeneration.
- Unsupported sources must be returned through a frontend-visible warnings channel, not only server logs.
- `SourcesExtractor` output is LLM-synthesized markdown, not raw source text.
- `from_sources` always reads the project-frozen `source_refs`. It must not re-read the live left-sidebar selection during generation, retry, or recovery.
- SSRF protection for `web` source fetching is in scope for this refactor and should be implemented in the fetch path, not deferred.
- Concurrency control stays lightweight in this phase: guard with active task checks, not new DB lock/version fields.

## Required Spec Changes

### 1. Source Snapshot Contract

- Update the spec so `source_refs` explicitly includes `content` for `report`.
- Define create-time freeze rules:
  - `report`: persist `content`
  - `web`/`kb`: persist reference snapshot, optionally content later
- State explicitly that `createProject` freezes the currently selected sources into `project.source_refs`.
- State explicitly that later generation/retry/recovery reads only `project.source_refs`, never the current sidebar selection.
- Update cache invalidation rules to compare the full stored source snapshot shape, not only `type + url`.
- Include `topic` in the effective cache key for `from_sources`.

### 2. Dirty State and Page Status Machine

- Remove `OUTLINE_READY` from the document.
- Add a page state transition table covering:
  - `DRAFT`
  - `DESCRIPTION_QUEUED`
  - `DESCRIPTION_GENERATING`
  - `DESCRIPTION_READY`
  - `IMAGE_QUEUED`
  - `IMAGE_GENERATING`
  - `IMAGE_READY`
  - `FAILED`
  - `is_dirty=true` overlay semantics
- Define dirty-page behavior:
  - Preview: show the last available image with a dirty/regenerating overlay
  - Export: blocked while any page is dirty or actively regenerating
  - Ready counts: dirty pages do not count as fully ready

### 3. Editing Contract

- Keep two explicit editing paths:
  - Chat edit: classification + automatic regeneration
  - Manual patch edit through `PUT /pages/{page_id}`: dirty only, no implicit regeneration
- Document regeneration rules:
  - `outline_edit` -> regenerate `description + image_prompt + image`
  - `description_edit` -> regenerate `description + image_prompt + image`
  - `image_edit` -> regenerate `image`
- State that manual patch editing must set `is_dirty=true` and `status="DRAFT"` so export blocking and preview overlays remain consistent.

### 4. Warning Propagation

- Map `skipped_sources` into task-visible warnings.
- Show warnings in progress UI as toast or inline notices.
- Document the exact warning contract for unsupported source types.

### 5. `from_sources` Semantic Clarification

- Clarify that `SourcesExtractor` uses `SourceReportGenerator.generate()`.
- Clarify that the resulting `normalized_content` is a synthesized markdown report, not a raw source bundle.
- Clarify that `normalized_content` cache therefore stores second-stage derived content.
- Clarify that `source_refs` is the frozen raw-input snapshot, while `normalized_content` is the derived LLM output.

### 6. Frontend Persistence Contract

- Add a table that separates persisted `studio_state.ppt` fields from runtime-only fields.
- Persist at least:
  - `projectId`
  - `activeTaskId`
  - `taskPhase`
  - `previewOpen`
  - `selectedSlideId`
  - existing style fields
- Keep runtime-only:
  - `pptPageRegeneratingIds`
  - transient loading flags
- Chat history stays in DB and is fetched by page, not persisted into `studio_state`.
- Restore logic for `selectedSlideId` must validate that the slide still exists; otherwise fall back to the first available slide.

### 7. Migration Strategy

- Use an MVP-friendly schema migration strategy before implementation starts.
- Do not hard-bind the plan to Alembic.
- Recommended MVP approach: direct SQL / startup schema migration support.
- Minimum schema changes:
  - add nullable project columns first
  - add nullable page columns first
  - create the new chat-history table
  - add indexes only after the table exists
- Recommended rollout order:
  1. back up the target database
  2. apply schema migration on dev/staging
  3. start the new backend and verify compatibility
  4. apply schema migration on the target environment before enabling new backend behavior there
  5. deploy frontend changes after backend/schema compatibility is confirmed
- Prefer nullable columns and additive changes so old code paths degrade safely during rollout.

### 8. Lightweight Concurrency Guard

- Define request-time guards using active task state:
  - reject new `generate_full` while another project-level PPT task is active
  - reject page chat/regeneration while the same page already has an active regeneration task
- Do not introduce `operation_lock`, `version`, or DB-level optimistic locking in this phase.

### 9. SSRF Protection for Web Source Fetching

- Add URL validation requirements for `web` source fetches:
  - allow only `http` / `https`
  - reject localhost, loopback, private, link-local, multicast, and reserved IP targets
  - validate resolved IPs, not only hostname strings
  - do not trust redirects without re-validation
- Implementation guidance:
  - parse URLs with `urllib.parse`
  - resolve hostnames with `socket.getaddrinfo()` and validate every resolved IP via `ipaddress`
  - use `allow_redirects=False`
  - if a redirect is returned, resolve the redirect target with `urljoin()` and re-run the same validation before following it
- Treat SSRF protection as part of the core `from_sources` implementation, not as a later hardening task.

## Execution Sequence

### Phase 1: Spec Alignment

- Update `docs/ppt-refactor-plan.md` so the full body matches the locked decisions above.
- Add three explicit tables:
  - `source_refs` schema
  - page state transitions
  - persisted vs runtime frontend state
- Add one explicit section for:
  - `from_sources` snapshot semantics
  - manual patch API semantics
  - active-task concurrency guards
  - SSRF validation requirements

### Phase 2: Storage and Model Changes

- Extend `src/services/storage/db.py` with:
  - `ppt_projects.source_refs`
  - `ppt_projects.normalized_content`
  - `ppt_projects.content_cached_at`
  - `ppt_pages.is_dirty`
  - `ppt_slide_chat_messages`
- Extend `src/services/storage/ppt_store.py` CRUD for:
  - `source_refs`
  - `is_dirty`
  - chat message storage
  - warning-friendly task payloads
- Implement the chosen schema migration strategy before wiring new API behavior.

### Phase 3: Orchestrator and Backend API

- Extend `src/api/routers/ppt.py`:
  - narrow `creation_type` to `from_research/from_notebook/from_sources`
  - add `/generate/full`
  - add `/pages/{page_id}/chat`
  - add `/pages/{page_id}/chat-history`
- Introduce a centralized PPT prompt manager and route outline/description/image prompts through it.
- Implement orchestrator flow only for `from_research/from_notebook/from_sources`.
- Enforce export guards:
  - dirty page present -> reject
  - missing image present -> reject
  - active page regeneration present -> reject
- Implement lightweight active-task guards for:
  - project-level full generation conflicts
  - same-page regeneration conflicts
- Implement SSRF-safe web fetching in the `from_sources` path.

### Phase 4: Editing Pipeline

- Implement `SlideEditor` classification and application flow.
- Implement `PUT /pages/{page_id}` dirty-only semantics.
- Implement single-page regeneration task flow.
- Ensure `description_edit` regenerates `description + image_prompt + image`, not only image.
- Ensure preview/state logic understands `DESCRIPTION_QUEUED` and `IMAGE_QUEUED` as in-progress statuses.

### Phase 5: Frontend Integration

- Update:
  - `web/app/notebooks/[id]/page.tsx`
  - `web/components/ppt/PptPreviewModal.tsx`
  - `web/lib/pptApi.ts`
  - `web/types/ppt.ts`
- Add `waitForPageRegenTask()` so single-page task polling does not mutate global `pptActiveTaskId`.
- Keep `generate_full` on the existing global recovery path.
- Persist and restore `selectedSlideId`.
- Show dirty overlays and warnings in preview/progress UI.
- Validate restored `selectedSlideId` against current slides before opening the editor panel.

### Phase 6: Validation

- Verify `from_sources` with `report` content works end to end.
- Verify page chat edits affect final export.
- Verify manual `PUT /pages` produces dirty pages and blocks export until regeneration.
- Verify refresh recovery for:
  - `generate_full`
  - preview reopening
  - selected slide restoration
- Verify unsupported source warnings are visible to users.
- Verify `from_sources` never changes when the live sidebar selection changes after project creation.
- Verify SSRF validation rejects internal-network URLs.

## Deferred Implementation Optimization

- `_fetch_web_content()` async parallelization is deferred.
- Full `web`/`kb` content snapshotting is deferred unless determinism requirements expand.
- Heavyweight DB locking/versioning is deferred unless active-task guards prove insufficient.
- WebSocket push for page regeneration progress is deferred.

## Done Definition

- `ppt-refactor-plan.md` is internally consistent and no longer contains obsolete contradictory behavior.
- `from_sources` supports `report` sources correctly.
- Chat edit, manual edit, export blocking, and refresh recovery form one closed system.
- Frontend/backend task semantics remain stable after refresh and retry.
