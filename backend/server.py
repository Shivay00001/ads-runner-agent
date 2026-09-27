"""ads-runner-agent backend — FastAPI service that generates full Google Ads
campaign architecture (ad groups, keywords, char-limited ad copy) via a REAL
litellm call and exports an import-ready Google Ads Editor CSV.

Configuration is 100% environment-driven; see .env.example for every variable.
There are no mock/fallback AI paths: a job without a valid provider key fails
with the provider's authentic error.
"""

import csv
import io
import json
import logging
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import litellm

from database import Base, SessionLocal, engine, get_db
from models import ExecutionLog, Setting

load_dotenv()
logger = logging.getLogger("ads-runner-agent")

SERVICE_NAME = "ads-runner-agent"


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Ads Runner Agent", version="1.0.0", lifespan=lifespan)


def _allowed_origins() -> list:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),  # never "*" when credentials are allowed
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-OpenAI-Key", "X-Anthropic-Key",
                   "X-Gemini-Key", "X-GLM-Key"],
)


# ---------------------------------------------------------------------------
# Structured error handling — never leak stack traces to clients
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(p) for p in err.get("loc", ())), "message": err.get("msg")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": "Invalid request input", "details": details},
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred"},
    )


# ---------------------------------------------------------------------------
# Auth — shared-secret API key on every non-public endpoint
# ---------------------------------------------------------------------------
async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    expected = os.getenv("API_KEY")
    if not expected:
        # Fail closed: the server is misconfigured, do not serve anything.
        raise HTTPException(status_code=500, detail="API_KEY is not configured on the server")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
    return True


# ---------------------------------------------------------------------------
# Provider-key storage helpers (per-provider LLM keys saved via settings)
# ---------------------------------------------------------------------------
async def get_api_key(db: AsyncSession, key_name: str, env_fallback: str = "") -> Optional[str]:
    result = await db.execute(select(Setting).where(Setting.key == key_name))
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        return setting.value
    return os.getenv(env_fallback) if env_fallback else None


async def upsert_setting(db: AsyncSession, key: str, value: str):
    """Insert or update a single Setting row (commit is the caller's job)."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value))


# Maps the per-provider slot used by the frontend/execute path to the DB key
# used by /api/settings/keys.
PROVIDER_SETTING_KEYS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "glm": "zhipuai_api_key",
}


async def fill_missing_keys_from_db(db: AsyncSession, api_keys: dict):
    """Fill any provider key not supplied via headers from stored settings,
    so keys saved through /api/settings/keys are actually usable by jobs."""
    for provider_slot, setting_key in PROVIDER_SETTING_KEYS.items():
        if not api_keys.get(provider_slot):
            api_keys[provider_slot] = await get_api_key(db, setting_key)


def get_api_key_for_model(model_id: str, api_keys: dict):
    if model_id.startswith("gpt"):
        return api_keys.get("openai") or os.getenv("OPENAI_API_KEY")
    elif model_id.startswith("claude"):
        return api_keys.get("anthropic") or os.getenv("ANTHROPIC_API_KEY")
    elif model_id.startswith("gemini"):
        return api_keys.get("gemini") or os.getenv("GEMINI_API_KEY")
    elif model_id.startswith("zhipu"):
        return api_keys.get("glm") or os.getenv("ZHIPUAI_API_KEY")
    return None


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def generate_google_ads_csv(campaign_data: dict, target_url: str, budget: str) -> str:
    """Converts the JSON campaign struct into a Google Ads Editor CSV format"""
    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        "Campaign", "Daily Budget", "Ad Group", "Keyword", "Match Type",
        "Headline 1", "Headline 2", "Headline 3", "Description 1", "Description 2", "Final URL"
    ])

    campaign_name = campaign_data.get("campaign_name", "AI Auto Generated Campaign")

    for ag in campaign_data.get("ad_groups", []):
        ag_name = ag.get("name", "Ad Group")

        # Write Keywords row
        for kw in ag.get("keywords", []):
            writer.writerow([
                campaign_name, budget, ag_name, kw, "Phrase",
                "", "", "", "", "", ""
            ])

        # Write Ads row
        for ad in ag.get("ads", []):
            writer.writerow([
                campaign_name, budget, ag_name, "", "",
                ad.get("headline_1", "")[:30],
                ad.get("headline_2", "")[:30],
                ad.get("headline_3", "")[:30],
                ad.get("description_1", "")[:90],
                ad.get("description_2", "")[:90],
                target_url
            ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Background job — REAL litellm call, no mocks or fallbacks
# ---------------------------------------------------------------------------
async def process_ads_job(task_id: str, product_url: str, description: str,
                          budget: str, provider: str, api_keys: dict):
    async with SessionLocal() as db:
        try:
            result = await db.execute(select(ExecutionLog).where(ExecutionLog.task_id == task_id))
            log = result.scalar_one()
            log.status = "running"
            await db.commit()

            # Header keys win; fall back to keys stored via /api/settings/keys,
            # then to env vars (handled inside get_api_key_for_model).
            await fill_missing_keys_from_db(db, api_keys)

            api_key = get_api_key_for_model(provider, api_keys)
            api_base = "http://localhost:11434" if provider.startswith("ollama") else None

            system_prompt = (
                "You are an expert Google Ads Campaign Architect. "
                "Output ONLY a raw JSON object with this exact structure, nothing else (no markdown fences):\n"
                "{\n"
                '  "campaign_name": "...",\n'
                '  "ad_groups": [\n'
                '    {\n'
                '      "name": "...",\n'
                '      "keywords": ["key1", "key2"],\n'
                '      "ads": [\n'
                '        {"headline_1": "...", "headline_2": "...", "headline_3": "...", "description_1": "...", "description_2": "..."}\n'
                '      ]\n'
                '    }\n'
                '  ]\n'
                "}\n\n"
                "RULES:\n"
                "1. Headlines strictly <= 30 chars.\n"
                "2. Descriptions strictly <= 90 chars.\n"
                "3. Create at least 2 highly relevant Ad Groups."
            )

            user_prompt = f"Product URL: {product_url}\nDescription: {description}\nBudget: {budget}"

            response = await litellm.acompletion(
                model=provider,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                api_key=api_key,
                api_base=api_base,
                max_tokens=2000
            )

            raw_text = response.choices[0].message.content.strip()
            # Remove any possible markdown
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            campaign_data = json.loads(raw_text)
            csv_output = generate_google_ads_csv(campaign_data, product_url, budget)

            log.campaign_json = json.dumps(campaign_data)
            log.csv_output = csv_output
            log.status = "success"
            await db.commit()

        except Exception as e:
            logger.exception("Error processing Ads job %s", task_id)
            result = await db.execute(select(ExecutionLog).where(ExecutionLog.task_id == task_id))
            log = result.scalar_one_or_none()
            if log:
                log.status = "error"
                # Only the provider's own error text is surfaced; never a stack trace.
                log.campaign_json = json.dumps({"error": str(e)})
                await db.commit()


# ---------------------------------------------------------------------------
# Request models with validation
# ---------------------------------------------------------------------------
PROVIDER_RE = re.compile(r"^(gpt|claude|gemini|zhipu|ollama)[\w.\-/:]{0,80}$")
URL_RE = re.compile(r"^https?://[^\s]{1,2040}$")


class ExecuteRequest(BaseModel):
    product_url: str
    description: str
    budget: str
    provider: str

    @field_validator("product_url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not URL_RE.match(v):
            raise ValueError("product_url must be a valid http(s) URL")
        return v

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("description must be at least 10 characters")
        if len(v) > 5000:
            raise ValueError("description must be at most 5000 characters")
        return v

    @field_validator("budget")
    @classmethod
    def budget_present(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("budget is required")
        if len(v) > 64:
            raise ValueError("budget is too long")
        return v

    @field_validator("provider")
    @classmethod
    def provider_known(cls, v: str) -> str:
        v = v.strip()
        if not PROVIDER_RE.match(v):
            raise ValueError(
                "provider must be a litellm model id starting with "
                "gpt|claude|gemini|zhipu|ollama (e.g. gpt-4o, gemini/gemini-1.5-pro, ollama/llama3)"
            )
        return v


class ApiKeysUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    zhipuai_api_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Liveness probe. Public — no auth required."""
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/")
async def root():
    """Public service info."""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "health": "/health",
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# Protected endpoints — require X-API-Key (see API_KEY in .env.example)
# ---------------------------------------------------------------------------
@app.post("/api/execute", dependencies=[Depends(require_api_key)])
async def enqueue_ads_task(req: ExecuteRequest, background_tasks: BackgroundTasks,
                           request: Request, db: AsyncSession = Depends(get_db)):
    task_id = str(uuid.uuid4())

    log = ExecutionLog(
        task_id=task_id,
        product_url=req.product_url,
        description=req.description,
        budget=req.budget,
        model_provider=req.provider,
        status="pending"
    )
    db.add(log)
    await db.commit()

    api_keys = {
        "openai": request.headers.get("X-OpenAI-Key"),
        "anthropic": request.headers.get("X-Anthropic-Key"),
        "gemini": request.headers.get("X-Gemini-Key"),
        "glm": request.headers.get("X-GLM-Key")
    }

    background_tasks.add_task(process_ads_job, task_id, req.product_url,
                              req.description, req.budget, req.provider, api_keys)

    return {"status": "success", "task_id": task_id}


@app.get("/api/tasks/{task_id}", dependencies=[Depends(require_api_key)])
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    if len(task_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid task id")
    result = await db.execute(select(ExecutionLog).where(ExecutionLog.task_id == task_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Task not found")

    campaign_data = None
    if log.campaign_json:
        try:
            campaign_data = json.loads(log.campaign_json)
        except Exception:
            pass

    return {
        "status": log.status,
        "campaign_data": campaign_data,
        "csv_output": log.csv_output
    }


@app.post("/api/settings/keys", dependencies=[Depends(require_api_key)])
async def update_keys(req: ApiKeysUpdate, db: AsyncSession = Depends(get_db)):
    stored = 0
    for field in ("openai_api_key", "anthropic_api_key", "gemini_api_key", "zhipuai_api_key"):
        value = getattr(req, field, None)
        if value:
            await upsert_setting(db, field, value)
            stored += 1
    if stored:
        await db.commit()
    return {"status": "success", "stored": stored}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8007")))
