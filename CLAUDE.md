# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Backend
pip install -r requirements.txt           # Install Python deps (3.10+)
python src/api/run_server.py              # Start backend (default port 8001)
python scripts/start_web.py              # Start backend + frontend together

# Frontend
npm install --prefix web                  # Install frontend deps
npm run dev --prefix web                  # Next.js dev server
npm run build --prefix web                # Production build
npm run lint --prefix web                 # ESLint

# Testing
pytest tests -q                           # Run all tests
pytest tests/ppt/ -v                      # PPT tests only
pytest tests/agents/solve/utils/test_json_utils.py  # Single test file

# Docker
docker compose up --build -d              # Production
make dev                                  # Dev mode (with hot reload)

# Code quality
pre-commit run --all-files                # Must pass before PR
```

## Code Style

- **Python**: Ruff lint/format, line length 100, 4-space indent (configured in `pyproject.toml`)
- **Frontend**: Prettier (2-space indent, single quotes, no semicolons) via `web/.prettierrc.json`
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`)
- **PRs**: Target `dev` branch, never `main`

## Architecture

DeepTutor is an AI learning platform with a Python backend and Next.js frontend, coordinated via Docker Compose.

### Backend (`src/`)

- **`src/api/`** - FastAPI server. Routers in `src/api/routers/` define REST and WebSocket endpoints.
- **`src/agents/`** - Multi-agent workflows organized by feature (chat, solve, research, question, guide, ideagen, co_writer). Each agent module has its own pipeline of specialized sub-agents.
- **`src/services/`** - Business logic layer:
  - `llm/` and `embedding/` - Pluggable LLM/embedding provider abstraction (OpenAI, Anthropic, Azure, Ollama, etc.)
  - `export/` - PPT, PDF, mindmap generation. `ppt_project_service.py` is the main PPT orchestrator; `banana_ppt_service.py` handles AI image generation for slides.
  - `rag/` - RAG retrieval service
  - `storage/` - S3/MinIO object storage
- **`src/tools/`** - Agent tools: RAG query, web search, ArXiv paper search, code execution, web crawling
- **`src/knowledge/`** - Knowledge base management: document ingestion, chunking, vector embedding

### Frontend (`web/`)

Next.js 16 App Router with React 19 and TypeScript. Key routes:

- `/notebooks/[id]` - Main notebook interface (largest component)
- `/chat`, `/solver`, `/research`, `/question`, `/guide`, `/ideagen`, `/co_writer` - Feature-specific UIs
- `/preview/ppt` - PPT preview

### Infrastructure

- **PostgreSQL 16** - Metadata, tasks, sessions (SQLAlchemy 2.0 ORM)
- **Redis** - Caching and queues
- **MinIO** - S3-compatible object storage for uploaded/generated files

### Configuration

- `config/main.yaml` - Runtime config (LLM settings, export options, RAG provider)
- `config/agents.yaml` - Agent behavior configuration
- `.env` / `web/.env.local` - Environment variables (API keys, ports, database URLs)
- Path alias: `@/*` maps to `web/` root in TypeScript imports

### PPT Generation System

The PPT pipeline supports multiple creation flows (from idea, outline, research, notebook, or sources). The workflow: create project -> generate outline -> generate slide descriptions -> generate images -> export PPTX. Key files: `src/services/export/ppt_project_service.py` (orchestrator), `src/api/routers/ppt.py` (API), `banana_ppt_service.py` (image generation).
