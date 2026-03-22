# PPT Refactor Automated Test Plan

## Goal

Validate the 1-6 phase PPT refactor with a test strategy that matches the
current `DeepTutor-1` MVP state:

- keep backend contracts stable
- verify new PPT storage and orchestration behavior
- verify the notebook PPT frontend still builds and recovers correctly
- catch the highest-risk regressions first

This plan is intentionally split into:

- **Required CI gates**: cheap, deterministic, should run on every branch
- **Extended integration / E2E**: slower, higher confidence, can run in PR or nightly

## Review Summary of Current Gaps

Before writing tests, note these current implementation gaps:

1. The notebook frontend still does **not expose the new three-entry creation
   flow** end to end.
   - `ExportContentSource` is still only `"research" | "sources"`.
   - `buildPptCreatePayload()` still resolves to legacy
     `idea/outline/descriptions`.
   - `from_research` / `from_notebook` / `from_sources` backend paths therefore
     exist, but are not first-class UI paths yet.

2. Manual slide edits are marked dirty, but the explicit regeneration action is
   still image-only.
   - `PUT /pages/{page_id}` correctly marks pages dirty.
   - The current preview UI button still calls `/regenerate-image`.
   - That path does not recompute `description + image_prompt`, so manual title
     or points edits are not fully closed-loop yet.

These two items should be treated as active review findings while designing test
coverage.

## Test Layers

### Layer A: Required CI Gates

These should run on every feature branch:

1. Backend syntax gate
2. Backend pytest suite for PPT
3. Frontend type check
4. Frontend production build

### Layer B: Extended API / Integration

These should run on PR validation:

1. API-level tests against FastAPI app
2. Storage / migration tests against real Postgres
3. Service tests with monkeypatched AI and source fetch dependencies

### Layer C: E2E Notebook Flow

These should run after UI for new creation entries is fully exposed:

1. notebook -> create PPT -> generate_full
2. page chat edit -> preview refresh -> export re-enabled
3. refresh recovery of preview + selected slide

## Environment

## Backend database

Use **real Postgres** for automated backend tests.

Reason:

- `db.py` is written for Postgres first
- additive schema migration uses Postgres-oriented SQL
- JSON / TIMESTAMPTZ / index behavior should be validated on the real target

Recommended local test database options:

1. Reuse the existing `docker-compose.yml` Postgres service
2. Or boot a dedicated temporary container for tests:

```bash
docker run --rm -d \
  --name deeptutor-ppt-test-pg \
  -e POSTGRES_DB=deeptutor_test \
  -e POSTGRES_USER=deeptutor \
  -e POSTGRES_PASSWORD=deeptutor \
  -p 55432:5432 \
  postgres:16-alpine
```

Recommended env for pytest:

```bash
export DATABASE_URL=postgresql+psycopg://deeptutor:deeptutor@localhost:55432/deeptutor_test
```

## Frontend

Frontend gates should run from:

```bash
cd web
npm ci
./node_modules/.bin/tsc --noEmit
npm run build
```

## Required CI Gates

### Gate 1: Backend syntax

Command:

```bash
python -m py_compile \
  src/api/routers/ppt.py \
  src/services/export/ppt_project_service.py \
  src/services/export/source_report.py \
  src/services/storage/db.py \
  src/services/storage/ppt_store.py
```

### Gate 2: Backend PPT pytest suite

Create a dedicated test package:

```text
tests/ppt/
  conftest.py
  test_ppt_schema.py
  test_ppt_store.py
  test_ppt_project_service.py
  test_ppt_router.py
  test_source_report_security.py
```

Run:

```bash
pytest tests/ppt -q
```

### Gate 3: Frontend type check

```bash
cd web
./node_modules/.bin/tsc --noEmit
```

### Gate 4: Frontend production build

```bash
cd web
npm run build
```

## Backend Test Design

### `tests/ppt/conftest.py`

Provide fixtures for:

- temporary Postgres-backed `DATABASE_URL`
- clean database initialization through `init_db()`
- cleanup helpers for `ppt_projects`, `ppt_pages`, `ppt_tasks`,
  `ppt_page_image_versions`, `ppt_slide_chat_messages`
- monkeypatched task manager that runs tasks inline for deterministic tests
- monkeypatched Banana PPT service / LLM helpers

Recommended fixture pattern:

- set `DATABASE_URL`
- reset `src.services.storage.db._engine = None`
- call `init_db()`
- truncate PPT tables before each test

### `tests/ppt/test_ppt_schema.py`

Coverage:

1. `init_db()` creates:
   - `ppt_projects.source_refs`
   - `ppt_projects.normalized_content`
   - `ppt_projects.content_cached_at`
   - `ppt_pages.is_dirty`
   - `ppt_slide_chat_messages`
2. additive schema bootstrap is idempotent
3. required chat-history indexes exist

### `tests/ppt/test_ppt_store.py`

Coverage:

1. `create_project()` persists `source_refs`
2. `create_project()` persists `normalized_content`
3. `create_page()` persists `is_dirty`
4. `create_slide_chat_message()` + `list_slide_chat_messages()` return in created order
5. `update_task()` keeps warnings / phase payload shape stable

### `tests/ppt/test_source_report_security.py`

Coverage:

1. `_validate_safe_fetch_url()` rejects:
   - `http://127.0.0.1/...`
   - `http://localhost/...`
   - `http://10.x.x.x/...`
   - `http://169.254.169.254/...`
2. redirects are revalidated
3. non-HTTP schemes are rejected
4. a public hostname with mocked safe IP is allowed

Recommended strategy:

- monkeypatch `socket.getaddrinfo`
- monkeypatch `requests.get`
- do not hit the real network

### `tests/ppt/test_ppt_project_service.py`

This is the highest-value test file.

Coverage:

1. **Source snapshot contract**
   - `from_sources` project creation freezes `source_refs`
   - `report` source keeps `content`
   - later generation uses stored `source_refs`, not live sidebar state

2. **`normalized_content` generation**
   - `SourceReportGenerator.generate()` result is stored into both
     `normalized_content` and `source_content`
   - skipped sources become warnings

3. **Dirty-only manual patch**
   - `update_page()` sets `status="DRAFT"`
   - `update_page()` sets `is_dirty=True`
   - export rejects while dirty

4. **Chat edit classification**
   - chat classified as `outline_edit`
   - chat classified as `description_edit`
   - chat classified as `image_edit`

5. **Description edit regeneration**
   - `description_edit` leads to:
     - regenerated `description_content`
     - regenerated `image_prompt`
     - regenerated image paths
     - `is_dirty=False` after success

6. **Image-only regeneration path**
   - `start_regenerate_page_image()` creates page task
   - sets `IMAGE_QUEUED`
   - clears dirty after success

7. **Concurrency guards**
   - reject second `generate_full` while one is active
   - reject page chat when same page regeneration task is active

8. **Export guards**
   - reject export if any page dirty
   - reject export if any page missing image
   - reject export if active page regeneration exists

Implementation advice:

- monkeypatch `banana_service.generate_outline`
- monkeypatch `_generate_page_description`
- monkeypatch `banana_service.generate_image`
- monkeypatch file save helpers when possible to avoid heavy image fixtures

### `tests/ppt/test_ppt_router.py`

Use `fastapi.testclient.TestClient` against `src.api.main.app`.

Coverage:

1. `POST /api/v1/ppt/projects`
   - accepts legacy creation types
   - accepts `from_sources`
   - accepts `source_refs`

2. `POST /api/v1/ppt/projects/{id}/generate/full`
   - returns task payload with `phase`

3. `PUT /api/v1/ppt/projects/{id}/pages/{page_id}`
   - marks page dirty

4. `POST /api/v1/ppt/projects/{id}/pages/{page_id}/chat`
   - returns task + `edit_type` + `assistant_message`

5. `GET /api/v1/ppt/projects/{id}/pages/{page_id}/chat-history`
   - returns stored message list

6. export endpoint rejects dirty project

## Frontend Test Design

Current repo state:

- no existing Vitest config
- no existing frontend test files
- no existing Playwright config committed

For MVP, use a two-step strategy:

### Step 1: keep static frontend gates mandatory

- `tsc --noEmit`
- `next build`

This is already valuable because the PPT notebook page is large and
type-sensitive.

### Step 2: add Playwright smoke coverage

Recommended new files:

```text
web/playwright.config.ts
web/e2e/ppt-refactor.spec.ts
```

Recommended scenarios:

1. **Dirty export blocking**
   - open notebook PPT preview
   - edit slide title manually
   - expect dirty overlay visible
   - expect export button disabled

2. **Single-page chat edit**
   - select a slide
   - submit chat instruction
   - expect loading state
   - expect chat history renders user + assistant messages
   - expect export re-enabled after regeneration completes

3. **Selected slide recovery**
   - open preview
   - select slide N
   - reload page
   - expect preview reopened with the same selected slide if still present

4. **Warnings visibility**
   - create a `from_sources` project with unsupported source types
   - expect warning banner in preview/progress UI

5. **Frozen source snapshot**
   - create project from selected sources
   - mutate live sidebar selection
   - trigger retry/recovery
   - assert project result is still based on stored snapshot

## Recommended Test Order

### PR-required

Run on every PR:

```bash
python -m py_compile \
  src/api/routers/ppt.py \
  src/services/export/ppt_project_service.py \
  src/services/export/source_report.py \
  src/services/storage/db.py \
  src/services/storage/ppt_store.py

pytest tests/ppt -q

cd web
./node_modules/.bin/tsc --noEmit
npm run build
```

### Extended PR or nightly

```bash
cd web
npx playwright test web/e2e/ppt-refactor.spec.ts
```

## Recommended First Batch to Implement

If the team wants the highest ROI first, implement these 6 tests before
anything else:

1. `test_from_sources_freezes_report_content_snapshot`
2. `test_update_page_marks_dirty_and_blocks_export`
3. `test_page_chat_description_edit_regenerates_description_prompt_and_image`
4. `test_same_page_regeneration_conflict_is_rejected`
5. `test_ssrf_guard_rejects_internal_network_targets`
6. `test_frontend_build_and_typecheck`

## Exit Criteria

The automated test plan is considered effective when it can prove:

- `from_sources` uses frozen `source_refs`
- manual edits correctly produce dirty/export-blocked state
- page chat edits affect final exported result
- refresh recovery keeps preview and selected slide stable
- unsupported source warnings are user-visible
- SSRF validation blocks internal network fetch targets
