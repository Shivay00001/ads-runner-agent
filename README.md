# AI Ads Runner Agent

An autonomous AI agent designed to generate, optimize, and manage digital marketing ad campaigns natively using LLMs.

## Overview
This repository contains a full-stack implementation of the **AI Ads Runner Agent**. 
- **Backend:** FastAPI (Python), LiteLLM (Multi-LLM Support: OpenAI, Anthropic, Gemini, GLM)
- **Frontend:** Next.js (React, Tailwind CSS)
- **Database:** SQLite / PostgreSQL

## Getting Started

### 1. Backend Setup
\\\ash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --port 8000
\\\

### 2. Frontend Setup
\\\ash
cd frontend
npm install
npm run dev
\\\

## Coordination & Automation
This agent is part of a larger ecosystem. It can be executed natively via its UI, or coordinated as a node in a multi-agent pipeline using the Central Connector System.
