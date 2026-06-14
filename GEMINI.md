# SSU-LMS-Bridge

## Project Overview

**SSU-LMS-Bridge** (숭실대학교 캡스톤 프로젝트) is a full-stack web application designed to integrate Soongsil University's Smart Campus LMS (`lms.ssu.ac.kr`) with external tools like Notion, Obsidian, and various Large Language Models (LLMs).

The application fetches courses, assignments, notices, and materials from the LMS and provides them through a unified interface. It features:
- **SSO Login:** Automated headless login using Playwright.
- **REST APIs & Synchronization:** Manual and scheduled background synchronization of LMS data to Notion.
- **LLM Chat Interface:** A WebSocket-streaming chat interface supporting multiple providers (OpenAI, Gemini, Anthropic) via `litellm`.
- **MCP Integration:** Utilizes the Model Context Protocol (MCP) to expose Notion and Obsidian as tools directly to the LLM within the same FastAPI process.

### Architecture

- **Backend:** Python 3.11+ using **FastAPI**. It handles REST APIs, WebSocket streaming, LMS SSO (Playwright), Canvas REST API interaction, LLM routing (`litellm`), and embeds MCP servers for Notion and Obsidian.
- **Frontend:** **React 18** built with **Vite** using pure JavaScript (no TypeScript). It communicates with the backend via REST and WebSockets.

---

## Directory Structure

```text
ssu-lms-bridge/
├── .env              # Root environment variables (Use .env.example as a template)
├── .venv/            # Shared Python virtual environment
├── backend/          # FastAPI application
│   ├── app/          # Source code (adapters, APIs, MCP client/servers, services)
│   ├── tests/        # Pytest suite
│   └── pyproject.toml# Python dependencies (managed via hatchling)
└── frontend/         # React application
    ├── src/          # React components, pages, API clients, and state
    ├── package.json  # Node dependencies
    └── vite.config.js# Vite configuration (includes API proxying to backend)
```

---

## Building and Running

### Prerequisites
- Python 3.11+
- Node.js & npm

### Backend Setup

1. **Virtual Environment:** Use a single virtual environment at the project root.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install Dependencies:**
   ```bash
   cd backend
   pip install -e ".[dev]"
   ```
3. **Playwright Setup:** Required for SSO login.
   ```bash
   playwright install chromium
   ```
4. **Environment Variables:** Copy the example file and configure it.
   ```bash
   # From the project root
   cp .env.example .env
   ```
5. **Run the Server:** Must be run from inside the `backend/` directory.
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```
   - Swagger UI available at: `http://localhost:8000/docs`

6. **Run Tests:**
   ```bash
   cd backend && python -m pytest -q
   ```

### Frontend Setup

1. **Install Dependencies:**
   ```bash
   cd frontend
   npm install
   ```
2. **Run Development Server:**
   ```bash
   npm run dev
   ```
   - App runs at `http://localhost:3000`
   - API requests to `/api` are automatically proxied to port 8000.

---

## Development Conventions

- **Environment Variables:** The `.env` file must reside in the root directory and must **NEVER** be committed to Git.
- **Backend Execution:** Always run FastAPI commands (`uvicorn`, `pytest`) from within the `backend/` directory to ensure `app.*` import paths resolve correctly.
- **Frontend Language:** The frontend uses pure JavaScript/JSX (`.js`, `.jsx`), not TypeScript.
- **Code Style (Backend):** Python code uses `ruff` for linting and formatting (line-length = 100, target-version = py311).
- **LMS Sync Constraints:** The university LMS updates daily at 3:00 AM. Background synchronizations are best scheduled after 4:00 AM.