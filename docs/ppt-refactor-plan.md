# DeepTutor-1 PPT Refactor Plan

## 1. Scope

This document is the implementation-facing spec for the PPT refactor on top of
`codex/ppt-image-semantic-generation`.

Goals for this phase:

- add `from_research`, `from_notebook`, and `from_sources` as first-class PPT inputs
- preserve current `idea` / `outline` / `descriptions` compatibility
- make page editing and export rules internally consistent
- keep notebook recovery and preview recovery stable
- use lightweight task guards instead of heavyweight locking

Non-goals for this phase:

- editable PPT export redesign
- full `web` / `kb` content snapshotting
- DB-level optimistic locking
- WebSocket push

## 2. Locked Decisions

- Baseline branch stays `codex/ppt-image-semantic-generation`.
- `from_sources` uses a create-time frozen snapshot.
- Generation, retry, and recovery read only project-owned snapshot data, not the
  live left-sidebar selection.
- `report` sources must freeze `content` at project creation time.
- `paper` and `file` are unsupported in this phase and must surface
  user-visible warnings.
- `SourcesExtractor` returns synthesized markdown, not raw source text.
- `normalized_content` stores derived markdown; `source_refs` stores frozen raw
  input snapshot.
- `PUT /projects/{project_id}/pages/{page_id}` is a dirty-only patch API.
- `SlideEditor.chat()` is the auto-regeneration path.
- Export is blocked while any selected page is dirty, regenerating, or missing
  a generated image.
- Concurrency stays lightweight and task-based in this phase.
- SSRF protection for `web` source fetches is in scope in this phase.

## 3. Project Input Model

### 3.1 `source_refs` schema

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `type` | `"report" \| "web" \| "kb" \| "paper" \| "file"` | yes | Input source kind |
| `title` | `string` | yes | User-visible source title |
| `url` | `string` | no | Used for `web`, optional elsewhere |
| `source_key` | `string` | no | Stable identifier for debugging or traceability |
| `content` | `string` | report only | Frozen raw content snapshot for `report` |

Rules:

- `createProject` freezes the source selection into `project.source_refs`.
- `from_sources` later reads only `project.source_refs`.
- `report` sources must include frozen `content`.
- `web` and `kb` may omit `content` in this phase.
- `paper` and `file` are skipped with warnings.

### 3.2 `normalized_content`

`normalized_content` is not a copy of `source_refs`. It is the derived markdown
produced by `SourcesExtractor`, which currently uses
`SourceReportGenerator.generate()`.

That means:

- `source_refs`: frozen raw input snapshot
- `normalized_content`: synthesized markdown derived from that snapshot

### 3.3 Cache key rules

The effective `from_sources` cache key must include:

- the stored `source_refs` snapshot
- `topic`

Cache invalidation must not rely only on `type + url`.

## 4. Creation Modes and Compatibility

### 4.1 Legacy compatibility

Existing modes remain valid in this phase:

- `idea`
- `outline`
- `descriptions`

New modes are introduced through the new orchestrator path:

- `from_research`
- `from_notebook`
- `from_sources`

Legacy modes continue working and are mapped into the new orchestration flow
incrementally. There is no flag day removal of legacy request shapes.

### 4.2 `from_sources` input contract

`from_sources` does not read the live sidebar selection during generation.

Flow:

1. User chooses sources in notebook UI.
2. `createProject` freezes the current source snapshot into `project.source_refs`.
3. Generation, retry, and recovery use only `project.source_refs`.
4. Later sidebar changes do not mutate the input of an already-created PPT
   project.

## 5. Page State Machine

### 5.1 Canonical states

This phase uses the following page states:

- `DRAFT`
- `DESCRIPTION_QUEUED`
- `DESCRIPTION_GENERATING`
- `DESCRIPTION_READY`
- `IMAGE_QUEUED`
- `IMAGE_GENERATING`
- `IMAGE_READY`
- `FAILED`

`OUTLINE_READY` is not used in this phase.

### 5.2 Transition table

| Event | New status | `is_dirty` |
| --- | --- | --- |
| new page created | `DRAFT` | `false` |
| manual page patch | `DRAFT` | `true` |
| chat outline edit accepted | `DRAFT` | `true` |
| chat description edit accepted | `DRAFT` | `true` |
| chat image edit accepted | `DRAFT` | `true` |
| queued for description regen | `DESCRIPTION_QUEUED` | `true` |
| description regen started | `DESCRIPTION_GENERATING` | `true` |
| description regen done | `DESCRIPTION_READY` | `true` |
| queued for image regen | `IMAGE_QUEUED` | `true` |
| image regen started | `IMAGE_GENERATING` | `true` |
| image regen done | `IMAGE_READY` | `false` |
| any regeneration failure | `FAILED` | `true` |

### 5.3 Dirty-page behavior

- Preview: show the last available image with a dirty or regenerating overlay.
- Export: reject while any selected page is dirty, regenerating, or missing a
  generated image.
- Ready counts: dirty pages do not count as fully ready.

## 6. Editing Contract

### 6.1 Chat editing path

`SlideEditor.chat()` is the automatic editing path.

Classification and regeneration rules:

- `outline_edit` -> update outline intent -> regenerate
  `description + image_prompt + image`
- `description_edit` -> update description intent -> regenerate
  `description + image_prompt + image`
- `image_edit` -> update image prompt intent -> regenerate `image`

### 6.2 Manual patch path

`PUT /projects/{project_id}/pages/{page_id}` is a low-level patch API.

Behavior:

- update stored fields
- set `is_dirty=true`
- set `status="DRAFT"`
- do not silently trigger regeneration

This keeps manual edits, preview overlays, and export blocking consistent.

## 7. Warning Contract

Unsupported sources must not be silent.

Rules:

- `paper` and `file` sources are skipped in this phase
- skipped source info must be surfaced via task-visible warnings
- warnings must be shown in frontend progress UI

Recommended transport:

- map skipped sources to `task.progress.warnings`

## 8. Frontend Persistence Contract

### 8.1 Persisted vs runtime-only state

| Field | Persisted in `studio_state.ppt` | Notes |
| --- | --- | --- |
| `projectId` | yes | Current PPT project |
| `activeTaskId` | yes | Global PPT task |
| `taskPhase` | yes | Recovery hint for UI |
| `previewOpen` | yes | Preview reopen |
| `selectedSlideId` | yes | Restore selected slide if still present |
| style-related fields | yes | Existing style state remains persisted |
| `pptPageRegeneratingIds` | no | Runtime-only page task tracking |
| transient loading flags | no | Reconstructed after refresh |

Chat history is stored in DB and fetched by page. It is not persisted into
`studio_state`.

### 8.2 Restore rules

- If `selectedSlideId` no longer exists, fall back to the first available slide.
- Global PPT recovery still uses `activeTaskId`.
- Single-page regeneration uses a dedicated polling path and must not overwrite
  the global task slot.

## 9. Concurrency Guard

This phase uses request-time task guards instead of DB lock fields.

Rules:

- reject new `generate_full` while another project-level PPT task is active
- reject page chat or page regeneration while the same page already has an
  active regeneration task

No `operation_lock`, `version`, or heavyweight optimistic locking is introduced
in this phase.

## 10. Security Requirements for `web` sources

SSRF protection is required in this phase.

Rules:

- allow only `http` and `https`
- reject localhost, loopback, private, link-local, multicast, reserved, and
  unspecified IP targets
- validate resolved IPs, not only hostname strings
- do not follow redirects blindly

Implementation requirements:

- parse URLs with `urllib.parse`
- resolve all addresses with `socket.getaddrinfo()`
- validate every resolved IP with `ipaddress`
- request with `allow_redirects=False`
- when redirecting, resolve the target with `urljoin()` and re-validate before
  following

## 11. Migration Strategy

This repository does not need to hard-bind this refactor to Alembic.

For this phase, use additive schema migration:

- add nullable project columns first
- add nullable page columns first
- create the chat-history table
- add indexes after the table exists

Minimum schema additions:

- `ppt_projects.source_refs`
- `ppt_projects.normalized_content`
- `ppt_projects.content_cached_at`
- `ppt_pages.is_dirty`
- `ppt_slide_chat_messages`

Recommended rollout order:

1. Back up the target database.
2. Apply schema migration on dev or staging.
3. Start the new backend and verify compatibility.
4. Apply schema migration on the target environment before enabling new backend
   behavior there.
5. Deploy frontend changes after backend and schema compatibility is confirmed.

Prefer additive and nullable changes so old code paths degrade safely.

## 12. Implementation Sequence

### Phase 1: Spec alignment

- keep this document aligned with the execution plan
- keep source snapshot, status machine, persistence, concurrency, and SSRF
  sections authoritative

### Phase 2: Storage and model changes

- add the new project and page columns
- add chat history table
- extend storage CRUD for new fields

### Phase 3: Orchestrator and backend API

- add new creation paths
- add `generate/full`
- add page chat endpoints
- enforce export guards
- enforce active-task guards

### Phase 4: Editing pipeline

- implement chat classification and regeneration
- keep manual patch API dirty-only
- implement page-level regeneration task flow

### Phase 5: Frontend integration

- add page-level polling path
- persist and restore `selectedSlideId`
- show dirty overlays and warnings

### Phase 6: Validation

- verify `from_sources` with report snapshots
- verify edit and export behavior
- verify notebook refresh recovery
- verify unsupported-source warnings
- verify sidebar changes do not mutate created projects
- verify SSRF protection rejects internal network targets
