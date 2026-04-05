# 🛰️ VANI AI — DETAILED ANTIGRAVITY PROMPT
## Complete Production Hardening: All 6 Issues

> **Session Type:** Full surgical production fix  
> **AI Agent Instruction:** Read this file completely before touching any code. Execute every section in the order listed. Do not skip sections. Do not refactor code outside the scope of each issue. After each issue, confirm with a checklist tick.

---

## 📐 SYSTEM ARCHITECTURE (Read First — Do Not Skip)

```
CALL FLOW:
Lead Phone Number
    → Twilio dials out
    → Twilio connects to FastAPI WebSocket endpoint (/ws/call/{call_sid})
    → ConversationManager.__init__() bootstraps campaign + lead context
    → receive_from_twilio() ← PRIMARY HEARTBEAT LOOP (never crash this)
        ├── STT: Sarvam ASR (Hindi/Marathi/Tamil/Telugu/Bengali)
        ├── LLM: Groq (fast inference) / OpenRouter (fallback)
        ├── TTS: Sarvam /text-to-speech REST → mulaw audio → Twilio stream
        └── clean_llm_for_tts() ← text sanitizer before TTS

BACKGROUND JOBS:
Lead Enrichment → Celery Task → Railway Redis Broker → Hermes Agent

FRONTEND:
React Dashboard (Vercel) → FastAPI REST (Railway) → PostgreSQL DB

DATABASE:
SQLAlchemy models → PostgreSQL on Railway
Migration tool: MISSING (fix = Alembic)
```

**Stack versions to keep in mind:**
- Python 3.11+ on Railway
- FastAPI 0.110+
- SQLAlchemy 2.x
- Celery 5.x
- React 18 + TypeScript
- Node 20 (Vercel)

---

## ⚠️ GLOBAL RULES FOR THIS SESSION

1. **Never rename existing API routes** — Twilio webhooks are hardcoded
2. **Never change the WebSocket protocol** — Twilio stream format is fixed
3. **Never modify Sarvam API payload keys** — they are vendor-locked
4. **Test every Python change in a venv before pushing to Railway**
5. **All secrets stay in `.env` / Railway environment variables — never hardcode**
6. **After each Issue section, run the verification steps listed at the bottom of that section**

---

---

# ISSUE 1 — DATABASE SCHEMA & MISSING MIGRATION STRATEGY
**Severity: 🔴 CRITICAL — Causes silent 500 crashes on every column rename**

## Root Cause (Detailed)

`Base.metadata.create_all(bind=engine)` in `main.py` startup only creates tables if they do not exist. It performs zero `ALTER TABLE` operations. When the dev renames a SQLAlchemy model column (e.g., `stripe_customer_id` → `razorpay_customer_id`), the PostgreSQL column remains named `stripe_customer_id`. Every query that touches the new attribute name produces:

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) 
column users.razorpay_customer_id does not exist
```

FastAPI catches this as an unhandled 500 with no useful client message. Railway logs show the full traceback but the API caller sees a silent failure.

## Complete Fix

### Step 1 — Install Alembic into the project

```bash
# In your Railway project root (where requirements.txt lives)
pip install alembic psycopg2-binary

# Add to requirements.txt:
echo "alembic==1.13.1" >> requirements.txt
echo "psycopg2-binary==2.9.9" >> requirements.txt
```

### Step 2 — Initialize Alembic

```bash
# Run from project root — this creates alembic/ folder and alembic.ini
alembic init alembic
```

This creates:
```
project_root/
├── alembic/
│   ├── env.py          ← YOU WILL EDIT THIS
│   ├── script.py.mako
│   └── versions/       ← migration files live here
└── alembic.ini         ← YOU WILL EDIT THIS
```

### Step 3 — Edit `alembic.ini`

Find this line:
```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

Replace with:
```ini
# Leave this blank — we set it dynamically from env in env.py
sqlalchemy.url =
```

### Step 4 — Edit `alembic/env.py` (COMPLETE FILE — replace existing content)

```python
# alembic/env.py
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Import your project's Base and ALL models ──────────────────────────────
# CRITICAL: import every model module here so Alembic can detect changes.
# If you add a new model file in the future, add its import here.
from app.db.base import Base          # your declarative_base()
from app.models.user import User       # add all model imports
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.call_log import CallLog
# Add any other model imports here as you create them

# ── Alembic Config ──────────────────────────────────────────────────────────
config = context.config

# Load .ini logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Override DB URL from environment variable ────────────────────────────────
# Never hardcode credentials. Railway injects DATABASE_URL automatically.
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Railway provides postgres:// but SQLAlchemy 2.x requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


# ── Offline migration (generates SQL file without connecting) ────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migration (connects and applies changes) ──────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,       # detect column type changes
            compare_server_default=True,  # detect default value changes
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Step 5 — Create the first migration (captures current state)

```bash
# Auto-generate a migration from current model state vs DB
alembic revision --autogenerate -m "initial_schema_with_razorpay_fields"

# Review the generated file in alembic/versions/ — check it looks correct
# Then apply:
alembic upgrade head
```

### Step 6 — Replace `create_all` in `app/main.py`

**FIND (and remove this block entirely):**
```python
# REMOVE THIS:
from app.db.session import engine
Base.metadata.create_all(bind=engine)
```

**REPLACE WITH:**
```python
# app/main.py
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import logging

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def run_db_migrations():
    """
    Run pending Alembic migrations on every startup.
    This is safe — Alembic tracks which migrations have run via alembic_version table.
    No-op if already at head. Never runs a migration twice.
    """
    try:
        logger.info("Running Alembic migrations...")
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("✅ DB migrations complete — at head.")
    except Exception as e:
        logger.critical(f"❌ DB migration failed on startup: {e}")
        raise  # crash startup if migrations fail — better than silent data corruption
```

### Step 7 — Add Railway deploy hook

In Railway dashboard → your FastAPI service → Settings → Deploy:

**Start Command:**
```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

> This runs migrations **before** FastAPI starts accepting traffic. Zero downtime risk.

### Step 8 — Workflow for all future column changes

```bash
# Developer workflow (do this EVERY time you change a model):
# 1. Edit your SQLAlchemy model
# 2. Generate migration:
alembic revision --autogenerate -m "describe_what_changed"
# 3. Review alembic/versions/<hash>_describe_what_changed.py
# 4. Commit to git
# 5. Railway deploy hook runs: alembic upgrade head automatically
```

### ✅ Verification for Issue 1

```bash
# 1. Check migration applied:
alembic current   # should show: <hash> (head)

# 2. Verify column exists in DB:
psql $DATABASE_URL -c "\d users"  # check razorpay_customer_id is present

# 3. Make a test model change, generate migration, check the SQL is correct:
alembic revision --autogenerate -m "test_change"
cat alembic/versions/<hash>_test_change.py
# Then roll it back:
alembic downgrade -1
```

---

---

# ISSUE 2 — WEBSOCKET CRASH IN `receive_from_twilio()`
**Severity: 🔴 CRITICAL — Call drops mid-sentence on any unhandled exception**

## Root Cause (Detailed)

`receive_from_twilio()` in `ConversationManager` is structured as:

```python
# CURRENT BROKEN PATTERN:
async for message in self.websocket.iter_text():
    try:
        # ... process media, start, stop events
    except Exception as e:
        logger.error(f"Error: {e}")
        raise   # ← THIS IS THE BUG. raise inside the async for loop
                # propagates the exception OUT of the generator
                # FastAPI's WebSocket handler catches it and closes the socket
                # Twilio sees a 1006 abnormal closure
                # User's phone hangs up
```

Any of these common runtime issues will kill the call:
- `data["media"]["payload"]` → KeyError if Twilio sends a non-media event
- STT buffer arriving in unexpected format → AttributeError
- Campaign JSON file missing a key → KeyError
- `asyncio.wait_for` timeout on TTS → TimeoutError

## Complete Fix

### Step 1 — Define custom exception types

Create new file: `app/services/exceptions.py`

```python
# app/services/exceptions.py
"""
Custom exceptions for ConversationManager.
Used to allow specific handling without crashing the WebSocket loop.
"""

class STTBufferException(Exception):
    """Raised when Sarvam STT returns malformed or empty buffer."""
    pass

class CampaignLoadException(Exception):
    """Raised when campaign config file is missing required keys."""
    pass

class TTSGenerationException(Exception):
    """Raised when Sarvam TTS fails to generate audio for a chunk."""
    pass

class LLMInferenceException(Exception):
    """Raised when Groq/OpenRouter inference fails or times out."""
    pass

class TwilioStreamException(Exception):
    """Raised only for fatal Twilio stream errors — will exit the loop."""
    pass
```

### Step 2 — Pre-load fallback audio at `__init__`

In `ConversationManager.__init__()`, add:

```python
# app/services/conversation_manager.py — inside __init__

import base64, os

# Pre-load fallback audio at startup so it's always available, even if TTS is down.
# Files: assets/fallback_hi.wav, assets/fallback_mr.wav, assets/fallback_en.wav
# These are short pre-recorded phrases: "एक सेकंड..." / "थांबा..." / "One moment..."
self._fallback_audio_cache: dict[str, str] = {}
fallback_dir = os.path.join(os.path.dirname(__file__), "../../assets/fallbacks")

for lang_code in ["hi", "mr", "ta", "te", "bn", "en"]:
    fallback_path = os.path.join(fallback_dir, f"fallback_{lang_code}.wav")
    if os.path.exists(fallback_path):
        with open(fallback_path, "rb") as f:
            # Pre-encode to base64 mulaw — ready to send directly to Twilio
            self._fallback_audio_cache[lang_code] = base64.b64encode(f.read()).decode()
    else:
        logger.warning(f"[ConversationManager] Missing fallback audio for lang: {lang_code}")
```

### Step 3 — Create fallback audio files

```bash
# Create the assets directory
mkdir -p assets/fallbacks

# You need 6 short WAV files (8kHz, mono, mulaw — Twilio format):
# fallback_hi.wav — "एक सेकंड..."
# fallback_mr.wav — "थांबा..."
# fallback_ta.wav — "ஒரு நிமிடம்..."
# fallback_te.wav — "ఒక్క నిమిషం..."
# fallback_bn.wav — "এক মুহূর্ত..."
# fallback_en.wav — "One moment..."

# Generate using Sarvam TTS CLI or record manually.
# Alternatively, use this Python script to generate all fallbacks via Sarvam on first deploy:

# scripts/generate_fallbacks.py
import httpx, base64, os, json

SARVAM_API_KEY = os.environ["SARVAM_API_KEY"]
FALLBACKS = {
    "hi-IN": ("hi", "एक सेकंड, मैं सोच रही हूँ।"),
    "mr-IN": ("mr", "थांबा, मी विचार करतेय।"),
    "ta-IN": ("ta", "ஒரு நிமிடம், நான் யோசிக்கிறேன்."),
    "te-IN": ("te", "ఒక్క నిమిషం, నేను ఆలోచిస్తున్నాను."),
    "bn-IN": ("bn", "এক মুহূর্ত, আমি ভাবছি।"),
    "en-IN": ("en", "One moment, let me think."),
}

os.makedirs("assets/fallbacks", exist_ok=True)

for lang_code, (short_code, text) in FALLBACKS.items():
    resp = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"API-Subscription-Key": SARVAM_API_KEY},
        json={"inputs": [text], "target_language_code": lang_code,
              "speaker": "meera", "model": "bulbul:v1",
              "enable_preprocessing": True}
    )
    audio_b64 = resp.json()["audios"][0]
    audio_bytes = base64.b64decode(audio_b64)
    with open(f"assets/fallbacks/fallback_{short_code}.wav", "wb") as f:
        f.write(audio_bytes)
    print(f"✅ Generated fallback_{short_code}.wav")
```

### Step 4 — Refactor `_get_fallback_audio()` to be safe

```python
# app/services/conversation_manager.py

async def _get_fallback_audio(self, reason: str = "unknown") -> None:
    """
    Send a pre-loaded fallback audio phrase to keep the user on the line.
    Never raises — absorbs all errors internally.
    Safe to call from anywhere inside the WebSocket loop.
    """
    lang = getattr(self, "campaign_language", "hi")  # default Hindi
    short_lang = lang.split("-")[0]  # "hi-IN" → "hi"

    fallback_b64 = self._fallback_audio_cache.get(short_lang) or \
                   self._fallback_audio_cache.get("hi") or \
                   self._fallback_audio_cache.get("en")

    if not fallback_b64:
        logger.error(f"[fallback_audio] No fallback audio available at all! Reason: {reason}")
        return  # Nothing we can do — but DO NOT crash

    try:
        await self._send_audio_to_twilio(fallback_b64)
        logger.info(f"[fallback_audio] Played fallback for lang={short_lang}, reason={reason}")
    except Exception as fe:
        # Even the fallback send failed — absorb silently. Loop must continue.
        logger.error(f"[fallback_audio] Failed to send fallback audio: {fe}")
```

### Step 5 — Rewrite `receive_from_twilio()` with full exception handling

```python
# app/services/conversation_manager.py

from app.services.exceptions import (
    STTBufferException, CampaignLoadException,
    TTSGenerationException, LLMInferenceException, TwilioStreamException
)

async def receive_from_twilio(self) -> None:
    """
    PRIMARY WEBSOCKET HEARTBEAT LOOP.

    CONTRACT:
    - MUST NEVER terminate due to a business logic exception.
    - ONLY exits on: Twilio "stop" event, WebSocket disconnect, or TwilioStreamException.
    - ALL other exceptions → log + fallback audio + continue.

    This is intentional. The call staying alive is more important than any single frame.
    If the AI stumbles, the user hears "एक सेकंड..." and the conversation resumes.
    """
    logger.info(f"[receive_from_twilio] Stream loop started. Call SID: {self.call_sid}")

    async for raw_message in self.websocket.iter_text():

        # ── Parse raw message ──────────────────────────────────────────────
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError as e:
            logger.warning(f"[receive_from_twilio] Malformed JSON frame: {e}. Skipping.")
            continue  # Twilio sometimes sends ping frames — ignore

        event = data.get("event", "")

        # ── Route by event type ────────────────────────────────────────────

        if event == "stop":
            # ONLY clean exit
            logger.info("[receive_from_twilio] Twilio stop event received. Exiting loop.")
            break

        elif event == "connected":
            logger.info("[receive_from_twilio] Twilio WebSocket connected.")
            continue

        elif event == "start":
            try:
                await self._handle_stream_start(data)
            except CampaignLoadException as e:
                logger.error(f"[stream_start] Campaign load failed: {e}")
                await self._get_fallback_audio(reason="campaign_load_error")
                # Don't break — campaign might still be partially usable
            except Exception as e:
                logger.exception(f"[stream_start] Unexpected error: {e}")
                await self._get_fallback_audio(reason="stream_start_error")
            continue

        elif event == "media":
            try:
                await self._handle_media_chunk(data)

            # ── Known recoverable exceptions ──────────────────────────────
            except KeyError as e:
                # Missing expected key in Twilio media payload
                logger.warning(f"[media] Missing key in payload: {e}. Frame skipped.")
                continue  # no fallback needed — just skip the frame

            except STTBufferException as e:
                logger.error(f"[media] STT buffer error: {e}")
                await self._get_fallback_audio(reason="stt_buffer_error")
                continue

            except TTSGenerationException as e:
                logger.error(f"[media] TTS generation failed: {e}")
                await self._get_fallback_audio(reason="tts_generation_error")
                continue

            except LLMInferenceException as e:
                logger.error(f"[media] LLM inference failed: {e}")
                await self._get_fallback_audio(reason="llm_inference_error")
                continue

            except asyncio.TimeoutError as e:
                # TTS or LLM timed out — don't drop the call
                logger.error(f"[media] Async timeout: {e}")
                await self._get_fallback_audio(reason="timeout")
                continue

            except TwilioStreamException as e:
                # Fatal stream error — exit loop (not WebSocket crash, controlled exit)
                logger.critical(f"[media] Fatal Twilio stream error: {e}. Exiting loop.")
                break

            except Exception as e:
                # Catch-all — unknown bug. Log full traceback for debugging.
                # NEVER raise — the call must survive.
                logger.exception(f"[media] Unhandled exception (call kept alive): {e}")
                await self._get_fallback_audio(reason="unknown_error")
                continue

        else:
            # Unknown event type — Twilio may add new events in future
            logger.debug(f"[receive_from_twilio] Unknown event '{event}'. Ignoring.")
            continue

    logger.info(f"[receive_from_twilio] Loop exited. Call SID: {self.call_sid}")
```

### Step 6 — Raise custom exceptions inside helper methods

In `_handle_media_chunk()`, `_run_stt()`, `_run_llm()`, `_run_tts()` — wrap library calls:

```python
# Example — wrap Sarvam STT call:
async def _run_stt(self, audio_bytes: bytes) -> str:
    try:
        response = await self.stt_client.transcribe(audio_bytes)
        if not response or not response.get("transcript"):
            raise STTBufferException(f"Empty STT response: {response}")
        return response["transcript"]
    except httpx.TimeoutException as e:
        raise STTBufferException(f"STT request timed out: {e}") from e
    except httpx.HTTPStatusError as e:
        raise STTBufferException(f"STT HTTP error {e.response.status_code}: {e}") from e

# Example — wrap Groq LLM call:
async def _run_llm(self, messages: list) -> str:
    try:
        response = await self.groq_client.chat.completions.create(
            model=self.llm_model,
            messages=messages,
            timeout=8.0
        )
        return response.choices[0].message.content
    except Exception as e:
        raise LLMInferenceException(f"Groq inference failed: {e}") from e
```

### ✅ Verification for Issue 2

```python
# Test script — simulate a KeyError inside receive_from_twilio:
# Temporarily add this to _handle_media_chunk for testing:
if os.environ.get("TEST_CRASH_MODE"):
    raise KeyError("test_missing_key")

# Place a test call → verify:
# 1. Call does NOT hang up
# 2. Fallback audio plays ("एक सेकंड...")
# 3. Railway log shows: "[media] Missing key in payload: test_missing_key. Frame skipped."
# 4. Conversation resumes normally after fallback
```

---

---

# ISSUE 3 — FRONTEND PHONE NUMBER BUG + ALERT UX
**Severity: 🟡 HIGH — Calls silently route to Afghanistan. Blocking UI on failures.**

## Root Cause A — The Afghanistan Bug (Detailed)

The user types `9307201890`. Dashboard.tsx does:
```typescript
// CURRENT BROKEN CODE:
const formatted = `+${phoneInput.replace(/\D/g, '')}`;
// Input: "9307201890" → Output: "+9307201890"
// Twilio parses "+93" as Afghanistan country code
// Dials: Afghanistan +93 07201890
// Twilio accepts the API call (no error!) but routing fails silently
```

## Root Cause B — `window.alert()` (Detailed)

`window.alert()` is a browser-blocking synchronous call. It freezes the entire JavaScript event loop, cancels pending network requests, and cannot be styled. Users see an ugly OS-native popup mid-workflow.

## Complete Fix

### Step 1 — Install `libphonenumber-js`

```bash
# In frontend/ directory:
npm install libphonenumber-js
```

### Step 2 — Create phone utility: `frontend/src/utils/phoneUtils.ts`

```typescript
// frontend/src/utils/phoneUtils.ts

import { parsePhoneNumber, isValidPhoneNumber, CountryCode } from 'libphonenumber-js';

export interface PhoneValidationResult {
  isValid: boolean;
  e164: string | null;
  displayFormat: string | null;
  error: string | null;
  detectedCountry: CountryCode | null;
}

/**
 * Validates and normalizes a phone number to E.164 format for Twilio.
 *
 * Rules (in order of priority):
 * 1. If input is exactly 10 digits → assume India (+91)
 * 2. If input starts with 91 and has 12 digits → strip leading 91, apply +91
 * 3. If input starts with + → parse as international
 * 4. If input starts with 00 → replace 00 with + and parse
 * 5. All other cases → invalid
 *
 * @param rawInput - Raw string typed by user (may include spaces, dashes, brackets)
 * @param defaultCountry - ISO country code for ambiguous numbers (default: 'IN')
 */
export function validateAndFormatPhone(
  rawInput: string,
  defaultCountry: CountryCode = 'IN'
): PhoneValidationResult {
  const invalid = (error: string): PhoneValidationResult => ({
    isValid: false, e164: null, displayFormat: null, error, detectedCountry: null
  });

  if (!rawInput || rawInput.trim() === '') {
    return invalid('Phone number is required.');
  }

  // Strip all non-digit, non-plus characters for analysis
  const digitsOnly = rawInput.replace(/\D/g, '');
  const stripped = rawInput.trim();

  // Rule 1: Exactly 10 digits → Indian mobile number
  if (digitsOnly.length === 10) {
    const candidate = `+91${digitsOnly}`;
    if (isValidPhoneNumber(candidate, 'IN')) {
      const parsed = parsePhoneNumber(candidate, 'IN');
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: 'IN'
      };
    }
    return invalid(`"${rawInput}" is not a valid Indian mobile number. Check the digits.`);
  }

  // Rule 2: 12 digits starting with 91 → likely typed with country code without +
  if (digitsOnly.length === 12 && digitsOnly.startsWith('91')) {
    const candidate = `+${digitsOnly}`;
    if (isValidPhoneNumber(candidate, 'IN')) {
      const parsed = parsePhoneNumber(candidate, 'IN');
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: 'IN'
      };
    }
  }

  // Rule 3: Starts with 00 → international prefix
  const normalizedInput = stripped.startsWith('00')
    ? `+${stripped.slice(2)}`
    : stripped;

  // Rule 4: Try parsing as international (with or without +)
  try {
    const candidate = normalizedInput.startsWith('+')
      ? normalizedInput
      : `+${digitsOnly}`;

    if (isValidPhoneNumber(candidate)) {
      const parsed = parsePhoneNumber(candidate);
      const country = parsed.country as CountryCode;
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: country || null
      };
    }
  } catch (e) {
    // parsePhoneNumber throws on genuinely invalid input
  }

  return invalid(
    `Could not parse "${rawInput}" as a valid phone number. ` +
    `For India, enter 10 digits (e.g., 9307201890) or use international format (+91XXXXXXXXXX).`
  );
}

/**
 * Formats a raw input progressively as the user types.
 * Used for input field display — does not validate.
 */
export function formatPhoneAsTyped(input: string): string {
  const digits = input.replace(/\D/g, '');
  if (digits.length <= 10) {
    // Format Indian mobile: XXXXX XXXXX
    return digits.replace(/(\d{5})(\d{1,5})/, '$1 $2');
  }
  return input; // Don't reformat international numbers
}
```

### Step 3 — Create Toast system: `frontend/src/hooks/useToast.ts`

```typescript
// frontend/src/hooks/useToast.ts

import { useState, useCallback, useRef } from 'react';

export type ToastVariant = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
  duration: number;  // ms
}

export interface UseToastReturn {
  toasts: Toast[];
  showToast: (message: string, variant?: ToastVariant, duration?: number) => void;
  dismissToast: (id: number) => void;
  clearAllToasts: () => void;
}

export function useToast(): UseToastReturn {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const showToast = useCallback((
    message: string,
    variant: ToastVariant = 'info',
    duration = 4000
  ) => {
    const id = ++counterRef.current;
    setToasts(prev => [...prev, { id, message, variant, duration }]);

    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, duration);
    }
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const clearAllToasts = useCallback(() => {
    setToasts([]);
  }, []);

  return { toasts, showToast, dismissToast, clearAllToasts };
}
```

### Step 4 — Create Toast component: `frontend/src/components/ToastContainer.tsx`

```typescript
// frontend/src/components/ToastContainer.tsx

import React from 'react';
import { Toast, ToastVariant } from '../hooks/useToast';

interface ToastContainerProps {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}

const VARIANT_STYLES: Record<ToastVariant, { bg: string; icon: string; border: string }> = {
  success: { bg: '#1a2e1a', icon: '✅', border: '#22c55e' },
  error:   { bg: '#2e1a1a', icon: '🚨', border: '#ef4444' },
  warning: { bg: '#2e261a', icon: '⚠️',  border: '#f59e0b' },
  info:    { bg: '#1a1e2e', icon: 'ℹ️',  border: '#3b82f6' },
};

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed', bottom: '24px', right: '24px',
      display: 'flex', flexDirection: 'column', gap: '12px',
      zIndex: 9999, maxWidth: '420px', width: '100%',
    }}>
      {toasts.map(toast => {
        const style = VARIANT_STYLES[toast.variant];
        return (
          <div
            key={toast.id}
            role="alert"
            aria-live="assertive"
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              borderLeft: `4px solid ${style.border}`,
              borderRadius: '8px',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              color: '#f1f5f9',
              fontSize: '14px',
              lineHeight: '1.5',
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              animation: 'slideIn 0.2s ease-out',
            }}
          >
            <span style={{ fontSize: '16px', flexShrink: 0, marginTop: '1px' }}>
              {style.icon}
            </span>
            <span style={{ flex: 1 }}>{toast.message}</span>
            <button
              onClick={() => onDismiss(toast.id)}
              aria-label="Dismiss notification"
              style={{
                background: 'none', border: 'none', color: '#94a3b8',
                cursor: 'pointer', fontSize: '16px', padding: '0', flexShrink: 0,
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(20px); opacity: 0; }
          to   { transform: translateX(0);   opacity: 1; }
        }
      `}</style>
    </div>
  );
};
```

### Step 5 — Update `Dashboard.tsx` — Quick Call section

**FIND the Quick Call submit handler (look for `window.alert` and the phone formatting logic):**

```typescript
// REMOVE ALL of these patterns from Dashboard.tsx:
// window.alert("...")
// const formatted = `+${phone}` or similar naive formatting
// Any direct phone string manipulation before API call
```

**REPLACE with:**

```typescript
// frontend/src/components/Dashboard.tsx
// Add at top of file:
import { validateAndFormatPhone, formatPhoneAsTyped } from '../utils/phoneUtils';
import { useToast } from '../hooks/useToast';
import { ToastContainer } from './ToastContainer';

// Inside the Dashboard component:
const { toasts, showToast, dismissToast } = useToast();
const [phoneInput, setPhoneInput] = useState('');
const [phoneError, setPhoneError] = useState<string | null>(null);
const [isCallLoading, setIsCallLoading] = useState(false);

// Phone input change handler:
const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const val = e.target.value;
  setPhoneInput(val);
  // Clear error as user types
  if (phoneError) setPhoneError(null);
};

// Quick Call submit:
const handleQuickCall = async () => {
  // 1. Validate phone
  const validation = validateAndFormatPhone(phoneInput);
  if (!validation.isValid) {
    setPhoneError(validation.error);
    return;
  }

  // 2. Confirm country if not India
  if (validation.detectedCountry && validation.detectedCountry !== 'IN') {
    const confirmed = window.confirm(
      // One case where confirm is intentional — international call confirmation
      `This will dial an international number: ${validation.displayFormat} (${validation.detectedCountry}). Continue?`
    );
    if (!confirmed) return;
  }

  setIsCallLoading(true);
  try {
    const response = await fetch('/api/calls/quick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone_number: validation.e164,  // Always E.164 to backend
        campaign_id: selectedCampaignId,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Server error: ${response.status}`);
    }

    const result = await response.json();
    showToast(`✅ Call initiated to ${validation.displayFormat}`, 'success');
    setPhoneInput('');

  } catch (err: any) {
    showToast(err.message || 'Failed to initiate call. Please try again.', 'error');
  } finally {
    setIsCallLoading(false);
  }
};

// In the JSX — phone input with inline validation:
<div style={{ position: 'relative' }}>
  <input
    type="tel"
    value={phoneInput}
    onChange={handlePhoneChange}
    placeholder="9307201890 or +91XXXXXXXXXX"
    aria-invalid={!!phoneError}
    aria-describedby={phoneError ? "phone-error" : undefined}
    style={{
      borderColor: phoneError ? '#ef4444' : undefined,
      // ... your existing input styles
    }}
  />
  {phoneError && (
    <p id="phone-error" role="alert" style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>
      {phoneError}
    </p>
  )}
</div>

<button
  onClick={handleQuickCall}
  disabled={isCallLoading || !phoneInput.trim()}
>
  {isCallLoading ? 'Initiating...' : 'Quick Call'}
</button>

// At the bottom of Dashboard JSX (before closing tag):
<ToastContainer toasts={toasts} onDismiss={dismissToast} />
```

### Step 6 — Find and replace ALL remaining `window.alert()` calls

```bash
# Run this in frontend/src/ to find all window.alert occurrences:
grep -rn "window.alert" frontend/src/

# Replace each one with showToast:
# window.alert("Campaign saved!") → showToast("Campaign saved!", "success")
# window.alert("Error: " + err) → showToast(`Error: ${err}`, "error")
# window.alert("Please fill all fields") → showToast("Please fill all required fields.", "warning")
```

### ✅ Verification for Issue 3

```typescript
// Test cases for validateAndFormatPhone:
validateAndFormatPhone("9307201890")     // → { isValid: true, e164: "+919307201890" }
validateAndFormatPhone("919307201890")   // → { isValid: true, e164: "+919307201890" }
validateAndFormatPhone("+919307201890")  // → { isValid: true, e164: "+919307201890" }
validateAndFormatPhone("+93072018")      // → { isValid: false, error: "..." }
validateAndFormatPhone("9307201890")     // detectedCountry === "IN" (not "AF")
validateAndFormatPhone("+14155552671")   // → US number, triggers confirm dialog
```

---

---

# ISSUE 4 — CONVERSATIONAL LOGIC & AUDIO CHOPPING
**Severity: 🟡 HIGH — Random mid-sentence silence destroys conversation illusion**

## Root Cause (Detailed)

`clean_llm_for_tts()` currently does this:

```python
# CURRENT BROKEN CODE (approximate):
def clean_llm_for_tts(text: str) -> str:
    if len(text) > MAX_CHARS:
        # Find last period/devanagari danda
        last_period = max(text.rfind('.'), text.rfind('।'))
        if last_period > 0:
            return text[:last_period + 1]
        else:
            return text[:MAX_CHARS]  # hard cut — splits mid-word
```

If the LLM returns: `"हाँ जी, हमारी योजना में आपको मासिक किश्तों में भुगतान करने की सुविधा मिलती है, जिसमें कोई छुपा हुआ शुल्क नहीं है, और पहले महीने में आपको कोई ब्याज नहीं देना होगा"`

There are zero `.` or `।` characters → hard cut at MAX_CHARS → mid-word like `"...कोई ब्याज नही"` → Sarvam TTS generates choppy/incomplete audio → user hears `"...ko-ee byaaj nahi"` then silence.

## Complete Fix

### Replace `clean_llm_for_tts()` entirely

```python
# app/services/conversation_manager.py

import re
from typing import Optional

# ── Sentence boundary patterns for all supported languages ──────────────────
# Devanagari (Hindi, Marathi): ।  Double danda: ॥
# Tamil: ।, .  Telugu: ।, .  Bengali: ।, .
_HARD_SENTENCE_BREAKS = re.compile(r'(?<=[.!?।॥])\s+')
_SOFT_CLAUSE_BREAKS = re.compile(r'(?<=[,;:])\s+')

def clean_llm_for_tts(
    text: str,
    max_chars: int = 180,
    ellipsis: str = "..."
) -> str:
    """
    Safely prepare LLM output for TTS generation.

    Truncation priority (highest to lowest):
    1. Hard sentence boundary (. ! ? । ॥)
    2. Soft clause boundary (, ; :)
    3. Word boundary (space)
    4. Hard character cut (last resort — should almost never happen)

    All truncated text gets an ellipsis so TTS generates a natural trailing tone.
    Also strips markdown, code blocks, HTML tags, and emoji.
    """
    if not text:
        return ""

    # ── Step 1: Strip formatting noise ──────────────────────────────────────
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)            # *italic*
    text = re.sub(r'`(.+?)`', r'\1', text)              # `code`
    text = re.sub(r'#{1,6}\s+', '', text)               # # headings
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [link](url)
    text = re.sub(r'<[^>]+>', '', text)                  # HTML tags

    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Remove emoji (basic Unicode ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\u2600-\u26FF\u2700-\u27BF]', '', text
    )

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # ── Step 2: Return as-is if within limit ────────────────────────────────
    if len(text) <= max_chars:
        return text

    # ── Step 3: Find best truncation point ──────────────────────────────────
    search_window = text[:max_chars]

    # Priority 1: Hard sentence break (. ! ? । ॥)
    sentence_positions = [
        search_window.rfind('.'),
        search_window.rfind('!'),
        search_window.rfind('?'),
        search_window.rfind('।'),
        search_window.rfind('॥'),
    ]
    best_sentence = max(p for p in sentence_positions)

    # Only use sentence break if it's past 40% of max_chars (avoids tiny fragments)
    if best_sentence > max_chars * 0.40:
        return text[:best_sentence + 1].strip()

    # Priority 2: Soft clause break (, ; :)
    clause_positions = [
        search_window.rfind(','),
        search_window.rfind(';'),
        search_window.rfind(':'),
    ]
    best_clause = max(p for p in clause_positions)

    if best_clause > max_chars * 0.35:
        return text[:best_clause].strip() + ellipsis

    # Priority 3: Word boundary (space)
    last_space = search_window.rfind(' ')
    if last_space > max_chars * 0.30:
        return text[:last_space].strip() + ellipsis

    # Priority 4: Hard cut (last resort)
    return text[:max_chars].strip() + ellipsis


def split_text_for_streaming_tts(
    text: str,
    max_chunk_chars: int = 100
) -> list[str]:
    """
    Split cleaned LLM output into sentence-sized chunks for streaming TTS.
    Each chunk generates one TTS audio segment.

    Use this instead of clean_llm_for_tts() when implementing streaming TTS.
    Chunks are split at sentence boundaries, falling back to clause boundaries.
    """
    text = clean_llm_for_tts(text, max_chars=99999)  # clean but don't truncate

    if len(text) <= max_chunk_chars:
        return [text] if text else []

    # Split on hard sentence boundaries first
    raw_sentences = _HARD_SENTENCE_BREAKS.split(text)
    chunks = []
    current_chunk = ""

    for sentence in raw_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 <= max_chunk_chars:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single sentence exceeds max_chunk_chars, split at clauses
            if len(sentence) > max_chunk_chars:
                sub_chunks = _split_at_clauses(sentence, max_chunk_chars)
                chunks.extend(sub_chunks[:-1])
                current_chunk = sub_chunks[-1] if sub_chunks else ""
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return [c for c in chunks if c.strip()]


def _split_at_clauses(text: str, max_chars: int) -> list[str]:
    """Split a single long sentence at clause boundaries."""
    parts = _SOFT_CLAUSE_BREAKS.split(text)
    result = []
    current = ""
    for part in parts:
        if len(current) + len(part) + 1 <= max_chars:
            current += (" " if current else "") + part
        else:
            if current:
                result.append(current)
            current = part
    if current:
        result.append(current)
    return result if result else [text[:max_chars]]
```

### ✅ Verification for Issue 4

```python
# Unit test cases:
from app.services.conversation_manager import clean_llm_for_tts, split_text_for_streaming_tts

# Test 1: Short text — no truncation
assert clean_llm_for_tts("नमस्ते।") == "नमस्ते।"

# Test 2: Sentence boundary
result = clean_llm_for_tts("यह पहला वाक्य है। यह दूसरा बहुत लंबा वाक्य है जो सीमा से आगे जाता है।" * 3)
assert result.endswith("।"), f"Should end at sentence boundary, got: {result[-20:]}"

# Test 3: Comma boundary fallback
long_no_periods = "हाँ, हमारी योजना में सुविधा है, जिसमें कोई शुल्क नहीं है, और ब्याज नहीं है" * 3
result = clean_llm_for_tts(long_no_periods, max_chars=80)
assert result.endswith("..."), f"Should end with ellipsis, got: {result[-20:]}"
assert not result.endswith("ह..."), "Should not cut mid-word"

# Test 4: Streaming split
chunks = split_text_for_streaming_tts("First sentence. Second sentence. Third sentence.", max_chunk_chars=50)
assert len(chunks) > 1
assert all(len(c) <= 60 for c in chunks)  # reasonable bound
print("All clean_llm_for_tts tests passed ✅")
```

---

---

# ISSUE 5 — LATENCY BOTTLENECK IN SARVAM TTS
**Severity: 🟡 HIGH — 15s silence gaps confuse users into barge-in, breaking conversation**

## Root Cause (Detailed)

`TTSService.generate_speech()` currently:
1. Takes the **entire LLM response** as one input
2. Makes **one synchronous REST call** to Sarvam `/text-to-speech`
3. Waits up to 15 seconds for the full audio to be returned
4. Only then starts `audioop.ratecv` conversion and Twilio streaming

For a 3-sentence response, this means:
- T+0.0s: LLM finishes → TTS call starts
- T+4.5s: Sarvam finishes generating → conversion starts
- T+5.0s: First audio reaches Twilio → user hears first word

5 seconds of silence. Users hang up or barge in.

## Complete Fix

### Step 1 — Create `TTSService.generate_speech_chunked()`

```python
# app/services/tts_service.py

import asyncio
import audioop
import base64
import httpx
import logging
from typing import AsyncGenerator

from app.services.exceptions import TTSGenerationException

logger = logging.getLogger(__name__)

class TTSService:

    def __init__(self, api_key: str, sample_rate: int = 8000):
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.sarvam_url = "https://api.sarvam.ai/text-to-speech"

        # Reuse HTTP client across requests (connection pooling)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=3.0,    # fail fast if Sarvam is down
                read=10.0,      # per-chunk timeout (was 15s for entire response)
                write=3.0,
                pool=5.0
            ),
            headers={"API-Subscription-Key": self.api_key}
        )

    async def generate_speech(self, text: str, lang_code: str = "hi-IN") -> bytes:
        """
        Original method — kept for backward compatibility.
        Now internally uses chunked generation and concatenates.
        """
        chunks_audio = await self.generate_speech_chunked_collected(text, lang_code)
        return b"".join(chunks_audio)

    async def generate_speech_chunked_collected(
        self, text: str, lang_code: str = "hi-IN"
    ) -> list[bytes]:
        """
        Generate TTS for each sentence chunk in PARALLEL.
        Returns ordered list of raw PCM/mulaw bytes ready to stream.
        """
        from app.services.conversation_manager import split_text_for_streaming_tts

        chunks = split_text_for_streaming_tts(text, max_chunk_chars=90)
        if not chunks:
            return []

        logger.info(f"[TTS] Generating {len(chunks)} chunk(s) in parallel for lang={lang_code}")

        # Fire all TTS requests concurrently — fastest chunk plays first
        tasks = [self._generate_single_chunk(chunk, lang_code) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        audio_segments = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[TTS] Chunk {i} failed: {result}. Substituting silence.")
                # 0.5 seconds of mulaw silence at 8kHz = 4000 bytes of 0x7F
                audio_segments.append(bytes([0x7F] * 4000))
            else:
                audio_segments.append(result)

        return audio_segments

    async def generate_speech_streaming(
        self, text: str, lang_code: str = "hi-IN"
    ) -> AsyncGenerator[bytes, None]:
        """
        Advanced: yields audio chunks as they complete, in order.
        Allows first chunk to play while later chunks still generate.
        Use this in receive_from_twilio for minimum latency.
        """
        from app.services.conversation_manager import split_text_for_streaming_tts

        chunks = split_text_for_streaming_tts(text, max_chunk_chars=90)
        if not chunks:
            return

        # Create futures for all chunks upfront (start all requests immediately)
        loop = asyncio.get_event_loop()
        futures = [
            asyncio.ensure_future(self._generate_single_chunk(chunk, lang_code))
            for chunk in chunks
        ]

        # Yield results IN ORDER as each future completes
        for future in futures:
            try:
                audio_bytes = await future
                yield audio_bytes
            except Exception as e:
                logger.error(f"[TTS streaming] Chunk failed: {e}. Yielding silence.")
                yield bytes([0x7F] * 4000)

    async def _generate_single_chunk(self, text: str, lang_code: str) -> bytes:
        """
        Call Sarvam TTS for a single text chunk.
        Returns raw mulaw bytes ready for Twilio.
        Raises TTSGenerationException on failure.
        """
        payload = {
            "inputs": [text],
            "target_language_code": lang_code,
            "speaker": "meera",
            "model": "bulbul:v1",
            "enable_preprocessing": True,
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
        }

        try:
            response = await self._client.post(self.sarvam_url, json=payload)
            response.raise_for_status()

            data = response.json()
            if not data.get("audios") or not data["audios"][0]:
                raise TTSGenerationException(f"Sarvam returned empty audio for: {text[:50]}")

            # Decode base64 PCM audio from Sarvam
            pcm_bytes = base64.b64decode(data["audios"][0])

            # Convert PCM (16-bit linear) → mulaw (8-bit) at 8kHz for Twilio
            mulaw_bytes = self._pcm_to_mulaw(pcm_bytes)
            return mulaw_bytes

        except httpx.TimeoutException as e:
            raise TTSGenerationException(f"TTS timeout for chunk: {text[:30]}...") from e
        except httpx.HTTPStatusError as e:
            raise TTSGenerationException(
                f"TTS HTTP {e.response.status_code} for chunk: {text[:30]}..."
            ) from e

    def _pcm_to_mulaw(self, pcm_bytes: bytes) -> bytes:
        """Convert 16-bit PCM to 8-bit mulaw at 8kHz for Twilio Media Streams."""
        # Sarvam outputs 22050Hz → downsample to 8000Hz
        resampled, _ = audioop.ratecv(
            pcm_bytes,
            2,          # sample width (bytes): 2 = 16-bit
            1,          # channels: 1 = mono
            22050,      # input rate (Sarvam default)
            8000,       # output rate (Twilio required)
            None        # state
        )
        # Convert linear16 → mulaw8
        mulaw = audioop.lin2ulaw(resampled, 2)
        return mulaw

    async def close(self):
        await self._client.aclose()
```

### Step 2 — Use streaming TTS in `ConversationManager`

Find the section in `receive_from_twilio()` / `_handle_media_chunk()` where TTS is called. Replace:

```python
# CURRENT (slow):
audio_bytes = await self.tts_service.generate_speech(response_text, lang_code)
await self._send_audio_to_twilio(base64.b64encode(audio_bytes).decode())
```

With:

```python
# NEW (streaming — first chunk plays while rest generate):
async for audio_chunk in self.tts_service.generate_speech_streaming(response_text, lang_code):
    await self._send_audio_to_twilio(base64.b64encode(audio_chunk).decode())
    # Each chunk plays immediately — perceived latency = time for first chunk only (~1-2s)
```

### Step 3 — Close the HTTP client on shutdown

```python
# app/main.py
@app.on_event("shutdown")
async def shutdown_tts_client():
    if hasattr(app.state, "tts_service"):
        await app.state.tts_service.close()
```

### ✅ Verification for Issue 5

```bash
# Benchmark: time a TTS call before and after
python scripts/benchmark_tts.py --text "हाँ जी, मैं आपको हमारी योजना के बारे में बताती हूँ। इसमें मासिक किश्तें हैं।"
# Expected: before ~4-6s, after ~1.5-2s for first chunk
```

---

---

# ISSUE 6 — BACKGROUND WORKER RESILIENCE (CELERY + RAILWAY REDIS)
**Severity: 🔴 CRITICAL — Dead workers block all lead enrichment silently**

## Root Cause (Detailed)

Two combined problems:

**Problem A:** Celery runs as root inside Railway containers → Redis connection raises `SecurityWarning: You're running the worker with superuser privileges`. With strict Redis configs, this causes connection refusal after a reboot.

**Problem B:** Celery's default reconnect behavior is aggressive — it tries to reconnect quickly, hits Railway Redis's rate limits, and gives up. The worker process stays running (Railway thinks it's healthy) but processes no tasks. Tasks queue up in Redis forever.

## Complete Fix

### Step 1 — Dockerfile: Non-root user for Celery

```dockerfile
# Dockerfile (or Dockerfile.celery if separate)

FROM python:3.11-slim

WORKDIR /app

# Create a non-root user for Celery
RUN groupadd -r celery && useradd -r -g celery celeryuser

# Install dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Switch to non-root before running
USER celeryuser
```

**Railway Start Command for Celery service:**
```bash
celery -A app.worker.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=100 \
  --without-gossip \
  --without-mingle
```

> `--max-tasks-per-child=100`: Worker process restarts after 100 tasks — prevents memory leaks.
> `--without-gossip --without-mingle`: Reduces Redis chatter, more stable on Railway.

### Step 2 — Full Celery app config: `app/worker/celery_app.py` (COMPLETE REWRITE)

```python
# app/worker/celery_app.py

import os
import logging
from celery import Celery
from celery.signals import worker_ready, worker_shutdown, task_failure
from kombu import Queue

logger = logging.getLogger(__name__)

# ── Redis URL normalization ──────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# Railway Redis sometimes uses rediss:// (TLS) — keep as-is
# Ensure it's not the raw postgres URL accidentally
if REDIS_URL.startswith("postgres"):
    raise ValueError("REDIS_URL is set to a PostgreSQL URL. Check Railway env vars.")

# ── Celery app creation ──────────────────────────────────────────────────────
celery_app = Celery(
    "vani_ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"]  # auto-discover tasks
)

# ── Core configuration ───────────────────────────────────────────────────────
celery_app.conf.update(

    # Task serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,

    # ── RELIABILITY: Task acknowledgment ────────────────────────────────────
    # acks_late=True: Task is removed from queue ONLY after successful completion.
    # If worker dies mid-task, task re-queues automatically.
    task_acks_late=True,
    task_reject_on_worker_lost=True,  # re-queue if worker process dies
    worker_prefetch_multiplier=1,     # fetch one task at a time (fair dispatch)

    # ── RELIABILITY: Redis broker transport ─────────────────────────────────
    broker_transport_options={
        # Retry connecting to Redis up to 15 times before giving up
        "max_retries": 15,
        # Start with no delay, then increase up to 5s between retries
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 5.0,
        "retry_on_timeout": True,
        # Visibility timeout: task becomes visible again if not acked in 1hr
        "visibility_timeout": 3600,
    },

    # ── RELIABILITY: Connection retry ───────────────────────────────────────
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=20,

    # ── RELIABILITY: Heartbeat ───────────────────────────────────────────────
    # Worker sends heartbeat every 10s. If missed, broker marks worker as dead.
    broker_heartbeat=10,
    broker_heartbeat_checkrate=2,

    # ── RELIABILITY: Cancel tasks on connection loss ─────────────────────────
    worker_cancel_long_running_tasks_on_connection_loss=True,

    # ── PERFORMANCE: Result expiry ───────────────────────────────────────────
    result_expires=3600,  # Keep task results for 1 hour

    # ── QUEUES: Explicit queue definitions ──────────────────────────────────
    task_queues=(
        Queue("default",  routing_key="default"),
        Queue("enrichment", routing_key="enrichment"),
        Queue("reporting", routing_key="reporting"),
    ),
    task_default_queue="default",
    task_default_routing_key="default",
)

# ── Signal handlers for observability ───────────────────────────────────────

@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    logger.info("✅ [Celery] Worker is ready and connected to Redis.")

@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    logger.info("🔴 [Celery] Worker shutting down.")

@task_failure.connect
def on_task_failure(task_id, exception, traceback, einfo, **kwargs):
    logger.error(
        f"[Celery] Task {task_id} FAILED: {exception}",
        exc_info=True
    )
    # TODO: Send to your alerting system (Slack/PagerDuty) here
```

### Step 3 — Robust task definitions: `app/worker/tasks.py`

```python
# app/worker/tasks.py

import logging
from celery import Task
from kombu.exceptions import OperationalError

from app.worker.celery_app import celery_app
from app.services.hermes_agent import hermes_enrich  # your existing Hermes call

logger = logging.getLogger(__name__)


class BaseVaniTask(Task):
    """
    Base class for all Vani AI tasks.
    Provides:
    - Automatic retry on Redis/connection errors
    - Structured logging on failure
    - On-failure callback hook
    """
    abstract = True
    max_retries = 5
    default_retry_delay = 5  # seconds between retries

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            f"[{self.name}] Permanent failure after {self.max_retries} retries. "
            f"Task ID: {task_id}. Error: {exc}",
            exc_info=True
        )
        # Override in subclass to send alerts, update DB, etc.

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(
            f"[{self.name}] Retrying (attempt {self.request.retries + 1}"
            f"/{self.max_retries}). Error: {exc}"
        )


@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="vani_ai.enrich_lead",
    queue="enrichment",
    # Auto-retry these specific exception types immediately
    autoretry_for=(OperationalError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 5, "countdown": 5},
    # Task-level timeout — kill task if it runs > 5 minutes
    time_limit=300,
    soft_time_limit=240,  # sends SIGTERM at 4min, SIGKILL at 5min
)
def enrich_lead_task(self, lead_id: str, campaign_id: str) -> dict:
    """
    Enrich a lead via Hermes agent.
    Retries up to 5 times on connection/timeout errors.
    Updates lead record in DB on success.
    """
    logger.info(f"[enrich_lead] Starting enrichment. lead_id={lead_id}, campaign_id={campaign_id}")

    try:
        result = hermes_enrich(lead_id=lead_id, campaign_id=campaign_id)

        if not result:
            raise ValueError(f"Hermes returned empty result for lead {lead_id}")

        # Update lead status in DB
        from app.db.session import get_db
        from app.models.lead import Lead
        from sqlalchemy.orm import Session

        db: Session = next(get_db())
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.enrichment_status = "completed"
                lead.enrichment_data = result
                db.commit()
        finally:
            db.close()

        logger.info(f"[enrich_lead] ✅ Completed for lead_id={lead_id}")
        return {"status": "success", "lead_id": lead_id, "data": result}

    except (OperationalError, ConnectionError, TimeoutError) as e:
        # These are retriable — Celery autoretry handles them
        raise

    except Exception as e:
        logger.exception(f"[enrich_lead] Non-retriable error for lead {lead_id}: {e}")
        # Update lead as failed in DB
        try:
            from app.db.session import get_db
            from app.models.lead import Lead
            db = next(get_db())
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.enrichment_status = "failed"
                lead.enrichment_error = str(e)
                db.commit()
            db.close()
        except Exception as db_e:
            logger.error(f"[enrich_lead] Also failed to update DB: {db_e}")
        raise  # Mark task as failed in Celery result backend


@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="vani_ai.health_check",
    queue="default",
)
def celery_health_check(self) -> dict:
    """Lightweight task to verify Celery worker is alive. Called by /health endpoint."""
    return {"status": "alive", "worker_id": self.request.hostname}
```

### Step 4 — Add health check endpoint for Railway

```python
# app/api/endpoints/health.py

from fastapi import APIRouter
from app.worker.celery_app import celery_app
import asyncio

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Health check for Railway.
    Checks: FastAPI running, Redis reachable, Celery worker alive.
    """
    # Check Redis connectivity via Celery
    try:
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active()
        celery_status = "healthy" if active is not None else "no_workers"
    except Exception as e:
        celery_status = f"unreachable: {str(e)[:50]}"

    return {
        "status": "ok",
        "celery": celery_status,
    }
```

```python
# app/main.py — register the health router
from app.api.endpoints.health import router as health_router
app.include_router(health_router)
```

### Step 5 — Railway service settings

**FastAPI service:**
- Health Check Path: `/health`
- Health Check Interval: 30s

**Celery Worker service:**
- Health Check: Not applicable (no HTTP server) — use Railway restart policy instead
- Restart Policy: Always
- Start Command:
```bash
celery -A app.worker.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100 --without-gossip --without-mingle
```

### Step 6 — Add Celery monitoring (Flower) on Railway (optional but recommended)

```bash
# Add to requirements.txt:
flower==2.0.1

# New Railway service — Flower dashboard:
# Start Command:
celery -A app.worker.celery_app flower --port=$PORT --broker=$REDIS_URL
```

### ✅ Verification for Issue 6

```bash
# 1. Confirm no SecurityWarning in logs:
railway logs --service celery-worker | grep -i security
# Expected: zero results

# 2. Test Redis reconnect:
# Restart Redis service in Railway → watch Celery logs
# Expected: "[Celery] Worker is ready and connected to Redis." within 30s — no manual restart

# 3. Test task retry:
# Trigger an enrich_lead_task with a bad lead_id
# Expected: 5 retries logged, then permanent failure with DB status="failed"

# 4. Test health endpoint:
curl https://your-api.railway.app/health
# Expected: {"status": "ok", "celery": "healthy"}
```

---

---

# 📋 MASTER EXECUTION CHECKLIST

Execute in this exact order. Do not proceed to the next item until the verification passes.

| # | Issue | Files Modified | Risk | Verification |
|---|-------|---------------|------|--------------|
| 1 | Alembic DB migrations | `alembic/`, `main.py`, `requirements.txt` | 🔴 High — test on staging DB first | `alembic current` shows `(head)` |
| 2 | WebSocket crash guard | `conversation_manager.py`, `exceptions.py`, `assets/fallbacks/` | 🟡 Medium | Test call survives forced KeyError |
| 3a | Phone validation | `phoneUtils.ts`, `Dashboard.tsx` | 🟢 Low | `validateAndFormatPhone("9307201890")` → `"+919307201890"` |
| 3b | Toast UX | `useToast.ts`, `ToastContainer.tsx`, `Dashboard.tsx` | 🟢 Low | No `window.alert` in codebase |
| 4 | LLM text truncation | `conversation_manager.py` (`clean_llm_for_tts`) | 🟢 Low | Unit tests all pass |
| 5 | TTS chunked streaming | `tts_service.py`, `conversation_manager.py` | 🟡 Medium | First audio chunk arrives < 2.5s |
| 6 | Celery resilience | `celery_app.py`, `tasks.py`, `Dockerfile`, `health.py` | 🟡 Medium | Redis restart → worker auto-reconnects |

---

# 🚀 RAILWAY DEPLOYMENT SEQUENCE

```bash
# 1. Run on staging first:
railway environment staging
alembic upgrade head         # migrations
railway deploy               # deploy FastAPI

# 2. Verify staging:
curl https://staging-api.railway.app/health
# Run a test call through the staging number

# 3. Deploy to production:
railway environment production
alembic upgrade head
railway deploy

# 4. Watch logs for 5 minutes post-deploy:
railway logs --service vani-api --follow
railway logs --service vani-celery --follow
```

---

*Vani AI Production Hardening — All 6 Issues. Generated for AI coding session context.*
*Stack: FastAPI · SQLAlchemy · Alembic · React/TS · Twilio · Sarvam AI · Groq · Celery · Redis · Railway · Vercel*
