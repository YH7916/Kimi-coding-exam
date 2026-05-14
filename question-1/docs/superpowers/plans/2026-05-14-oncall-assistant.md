# On-Call Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Q1 On-Call assistant web app with `/v1`, `/v2`, and `/v3` routes, pylint enforcement, separated route and implementation layers, and git commits after each coherent change.

**Architecture:** Use a small Python standard-library HTTP server. Keep HTTP route handling in `oncall_app/routes.py`; keep document parsing, search, agent behavior, and rendering in focused implementation modules under `oncall_app/`. Tests exercise implementation modules and route behavior without depending on an external service.

**Tech Stack:** Python 3, standard-library `http.server`, `html.parser`, `unittest`, `pylint`.

---

## File Structure

- Create `app.py`: entry point that starts the HTTP server.
- Create `oncall_app/routes.py`: maps HTTP method/path to implementation services.
- Create `oncall_app/server.py`: `BaseHTTPRequestHandler` adapter and response helpers.
- Create `oncall_app/html_parser.py`: extracts title and visible text from SOP HTML.
- Create `oncall_app/repository.py`: loads and stores SOP documents, exposes `read_file`.
- Create `oncall_app/search.py`: keyword and semantic search logic.
- Create `oncall_app/agent.py`: deterministic tool-using on-call assistant.
- Create `oncall_app/pages.py`: minimal HTML pages for `/v1`, `/v2`, `/v3`.
- Create `oncall_app/models.py`: dataclasses shared across modules.
- Create `tests/`: `unittest` tests for parser, search, routes, and agent.
- Create `.pylintrc`: local pylint constraints.

## Task 1: Project Tooling Skeleton

**Files:**
- Create: `app.py`
- Create: `oncall_app/__init__.py`
- Create: `.pylintrc`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create a smoke test**

Create `tests/test_smoke.py`:

```python
from oncall_app import __version__


def test_package_has_version():
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -v`

Expected: fail or error because `oncall_app` is not implemented yet.

- [ ] **Step 3: Add minimal package and entry point**

Implement `oncall_app/__init__.py` with `__version__ = "0.1.0"` and `app.py` with a `main()` placeholder that will later start the server.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest discover -v
pylint app.py oncall_app tests
git add app.py oncall_app tests .pylintrc
git commit -m "chore: add Python project skeleton"
```

## Task 2: HTML Parsing and Repository

**Files:**
- Create: `oncall_app/models.py`
- Create: `oncall_app/html_parser.py`
- Create: `oncall_app/repository.py`
- Test: `tests/test_documents.py`

- [ ] **Step 1: Write parser and repository tests**

Test title extraction, visible text extraction, HTML entity decoding, script/style exclusion, and `read_file(fname)` path safety.

- [ ] **Step 2: Verify tests fail**

Run: `python -m unittest tests.test_documents -v`

Expected: errors because modules do not exist.

- [ ] **Step 3: Implement parser and repository**

Use `html.parser.HTMLParser`, skip `script` and `style`, decode entities via parser behavior plus `html.unescape`, and only allow direct file names in `read_file`.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest tests.test_documents -v
pylint app.py oncall_app tests
git add oncall_app tests
git commit -m "feat: load and parse SOP documents"
```

## Task 3: Phase 1 Keyword Search

**Files:**
- Create: `oncall_app/search.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Write keyword search tests**

Cover README checks: `OOM` returns `sop-001`, `故障` returns many docs, `replication` returns empty when it only appears in script content, `CDN` returns `sop-003` and `sop-010`, and `&` finds entity-decoded content.

- [ ] **Step 2: Verify tests fail**

Run: `python -m unittest tests.test_search -v`

Expected: errors because search implementation does not exist.

- [ ] **Step 3: Implement keyword search**

Add ranked title/body matching, snippets around the first match, and stable score ordering.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest tests.test_search -v
pylint app.py oncall_app tests
git add oncall_app tests
git commit -m "feat: implement keyword SOP search"
```

## Task 4: HTTP Routes and Pages for V1/V2 Shell

**Files:**
- Create: `oncall_app/server.py`
- Create: `oncall_app/routes.py`
- Create: `oncall_app/pages.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write route tests**

Cover `GET /v1`, `GET /v1/search`, `POST /v1/documents`, and JSON response shapes.

- [ ] **Step 2: Verify tests fail**

Run: `python -m unittest tests.test_routes -v`

Expected: errors because route layer does not exist.

- [ ] **Step 3: Implement routes separately from services**

Keep parsing request paths and returning response objects in `routes.py`; route functions should call repository/search services instead of embedding business logic.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest tests.test_routes -v
pylint app.py oncall_app tests
git add app.py oncall_app tests
git commit -m "feat: add routed HTTP API and pages"
```

## Task 5: Phase 2 Semantic Search

**Files:**
- Modify: `oncall_app/search.py`
- Modify: `oncall_app/routes.py`
- Modify: `oncall_app/pages.py`
- Test: `tests/test_semantic_search.py`

- [ ] **Step 1: Write semantic tests**

Cover `服务器挂了` ranking `sop-001` and `sop-004` near top, `黑客攻击` ranking `sop-005` first, and `机器学习模型出问题` ranking `sop-008` first.

- [ ] **Step 2: Verify tests fail**

Run: `python -m unittest tests.test_semantic_search -v`

Expected: failure because semantic ranking is not implemented.

- [ ] **Step 3: Implement deterministic semantic expansion**

Use a local synonym/intent table and document topic profiles, merged with keyword search score.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest tests.test_semantic_search -v
pylint app.py oncall_app tests
git add oncall_app tests
git commit -m "feat: add semantic SOP search"
```

## Task 6: Phase 3 Agent

**Files:**
- Create: `oncall_app/agent.py`
- Modify: `oncall_app/routes.py`
- Modify: `oncall_app/pages.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write agent tests**

Cover each README prompt: database replication delay reads `sop-002.html`, OOM reads `sop-001.html`, P0 reads multiple SOP files, intrusion reads `sop-005.html`, and recommendation quality reads `sop-008.html`.

- [ ] **Step 2: Verify tests fail**

Run: `python -m unittest tests.test_agent -v`

Expected: errors because the agent module does not exist.

- [ ] **Step 3: Implement tool-only agent**

Use exactly one tool function, `readFile(fname: str) -> str`, inside the agent. The agent may choose file names from deterministic intent logic, but the displayed trace must show `readFile` calls.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m unittest tests.test_agent -v
pylint app.py oncall_app tests
git add oncall_app tests
git commit -m "feat: add tool-using on-call assistant"
```

## Task 7: Final Verification

**Files:**
- Modify: `README.md` if startup notes are needed.

- [ ] **Step 1: Run full checks**

Run:

```powershell
python -m unittest discover -v
pylint app.py oncall_app tests
python app.py
```

- [ ] **Step 2: Verify HTTP examples**

In another terminal or after starting a short-lived server in tests, verify:

```powershell
curl "http://localhost:8000/v1/search?q=OOM"
curl "http://localhost:8000/v1/search?q=replication"
curl "http://localhost:8000/v2/search?q=黑客攻击"
```

- [ ] **Step 3: Commit final docs or fixes**

If final docs or fixes were needed:

```powershell
git add README.md oncall_app tests
git commit -m "docs: add run and verification notes"
```

