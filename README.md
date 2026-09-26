# AI Ads Runner Agent

An autonomous AI agent designed to generate, optimize, and manage digital marketing ad campaigns natively using LLMs.

## Overview
This repository contains a full-stack implementation of the **AI Ads Runner Agent**.
- **Backend:** FastAPI (Python), LiteLLM (Multi-LLM Support: OpenAI, Anthropic, Gemini, GLM)
- **Frontend:** Next.js (React, Tailwind CSS)
- **Database:** SQLite / PostgreSQL

## ⚠️ Important: a real LLM API key is required

Ad generation is performed by a **real** LLM call (via LiteLLM) — there is no mock or fallback.
A task enqueued without a valid provider key will fail with an authentication error from the provider.

Supply a key **one** of these ways:

- **Via the UI:** enter the keys in the settings panel — they are sent as request headers (`X-OpenAI-Key`, `X-Anthropic-Key`, `X-Gemini-Key`, `X-GLM-Key`) on every `/api/execute` call, and are also persisted server-side through `POST /api/settings/keys` so later runs work without re-entering them.
- **Via environment variables:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ZHIPUAI_API_KEY` (or run a local Ollama instance and choose an `ollama/...` provider — no key needed).
- **Key lookup order for a job:** request headers → keys stored via `/api/settings/keys` → environment variables.

> **The product does nothing without a valid key supplied by the owner.** No key is bundled with this repo and none is faked — bring your own provider key (or local Ollama) before expecting a campaign to generate.

## Getting Started

### 1. Backend Setup

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (cmd.exe)
venv\Scripts\activate.bat
```

Then install dependencies and start the server:

```bash
pip install -r requirements.txt
uvicorn server:app --port 8000
```

The API is available at `http://localhost:8000`.

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Coordination & Automation
This agent is part of a larger ecosystem. It can be executed natively via its UI, or coordinated as a node in a multi-agent pipeline using the Central Connector System.
