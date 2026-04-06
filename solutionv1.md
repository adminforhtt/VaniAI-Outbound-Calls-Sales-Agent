# Vani AI — Antigravity Fix Prompt
**Date:** 2026-04-05 | **Context:** Production crashed on Railway (web service). Fix all 5 issues below in a single focused PR. Do not touch unrelated code.

---

## 🔴 FIX 1 — Celery Worker Import Crash (BLOCKING — fix this first)

**File:** `app/worker/tasks.py`

**Problem:**
The Celery worker imports `hermes_enrich` as a standalone function from `app.services.hermes_service`, but that module only exports a class `LeadEnrichmentService`. This raises an `ImportError` on worker startup, meaning **no background enrichment tasks can run at all.**

```python
# CURRENT (broken)
from app.services.hermes_service import hermes_enrich  # ← does not exist
```

**Fix:**
Replace the broken import with the class-based call pattern. Instantiate `LeadEnrichmentService` inside the task function and call the appropriate method.

```python
# CORRECT
from app.services.hermes_service import LeadEnrichmentService

@celery_app.task
def enrich_lead_task(lead_id: str, campaign_id: str):
    service = LeadEnrichmentService()
    return service.enrich(lead_id=lead_id, campaign_id=campaign_id)
    # Adjust method name to match what's actually defined in LeadEnrichmentService
```

**Acceptance criteria:**
- `celery -A app.worker.tasks worker --loglevel=info` starts without `ImportError`
- A test enrichment task submitted via `.delay()` or `.apply_async()` reaches the `STARTED` state

---

## 🔴 FIX 2 — Fallback Audio Generation (deprecated `bulbul:v1` model)

**Files:** `scripts/generate_fallbacks.py`, `assets/fallbacks/` (currently empty)

**Problem:**
The script calls Sarvam AI TTS using `bulbul:v1`, which is deprecated and returns a `400` error. As a result, `assets/fallbacks/` has no `.wav`/`.mp3` files. Any live call that hits a TTS timeout will play **dead silence**.

**Fix — two parts:**

**Part A — Update the model name in the script:**
Replace `bulbul:v1` with the current Sarvam AI TTS model. As of early 2026, Sarvam's production TTS model is `bulbul:v2`. Verify against [https://docs.sarvam.ai](https://docs.sarvam.ai) before committing.

```python
# BEFORE
payload = { "model": "bulbul:v1", ... }

# AFTER
payload = { "model": "bulbul:v2", ... }  # verify current model name in Sarvam docs
```

**Part B — Pre-generate and commit fallback audio files:**
Run the updated script locally for all 5 supported languages and commit the output files:

| Language | Fallback text (suggested) | Filename |
|---|---|---|
| Hindi | "कृपया थोड़ा रुकें, हम आपसे जल्द जुड़ेंगे।" | `hi_fallback.wav` |
| Marathi | "कृपया थांबा, आम्ही लवकरच संपर्क करतो." | `mr_fallback.wav` |
| Tamil | "தயவுசெய்து காத்திருங்கள், நாங்கள் விரைவில் தொடர்புகொள்கிறோம்." | `ta_fallback.wav` |
| Telugu | "దయచేసి వేచి ఉండండి, మేము త్వరలో మీతో కనెక్ట్ అవుతాము." | `te_fallback.wav` |
| Bengali | "অনুগ্রহ করে অপেক্ষা করুন, আমরা শীঘ্রই আপনার সাথে যোগাযোগ করব।" | `bn_fallback.wav` |

**Acceptance criteria:**
- `assets/fallbacks/` contains all 5 audio files, each >0 bytes
- Script exits with code `0` and no `400` errors in logs

---

## 🟡 FIX 3 — Verify Hermes Agent Hooks

**File:** `app/services/hermes_service.py`

**Problem:**
`LeadEnrichmentService` imports `save_lead_research` and `save_campaign_script` from `app.agents.hermes_tools`. These were added as lightweight database hooks to replace the heavy NousResearch/Hermes CLI pipeline. It is **unverified** whether these functions exist, accept the right signatures, and commit correctly.

**Fix — verification checklist (do all three):**

1. **Confirm the functions exist:**
   Open `app/agents/hermes_tools.py` and verify both `save_lead_research` and `save_campaign_script` are defined (not just imported from somewhere else).

2. **Confirm signatures match call sites:**
   In `hermes_service.py`, find each call. Verify the arguments passed match the function signature in `hermes_tools.py`. Example expected signatures:
   ```python
   def save_lead_research(lead_id: str, research: dict) -> bool: ...
   def save_campaign_script(campaign_id: str, script: str) -> bool: ...
   ```

3. **Add a smoke test:**
   Write a minimal pytest test in `tests/test_hermes_hooks.py`:
   ```python
   from app.agents.hermes_tools import save_lead_research, save_campaign_script

   def test_hooks_importable():
       assert callable(save_lead_research)
       assert callable(save_campaign_script)
   ```
   Run with `pytest tests/test_hermes_hooks.py -v`. Must pass.

**Acceptance criteria:**
- Both functions exist, match their call sites, and the smoke test passes
- If a function is missing: create a stub that logs a warning and returns `False` (do not raise, enrichment should degrade gracefully)

---

## 🟢 FIX 4 — Frontend Chunk Size Warning (Vite/Webpack)

**File:** `frontend/vite.config.ts` (or `webpack.config.js`)

**Problem:**
`npm run build` warns that some chunks exceed 500 kB after minification. The likely culprit is a heavy phone/dialer library loaded at the top level.

**Fix — add dynamic imports for heavy dependencies:**

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          // Move the phone library to its own chunk
          phone: ['<name-of-phone-library>'],
        }
      }
    },
    chunkSizeWarningLimit: 600  // Optional: raise threshold if 1 chunk is intentionally large
  }
})
```

And in the component that uses the phone library:
```tsx
// BEFORE
import PhoneDialer from 'some-phone-lib'

// AFTER
const PhoneDialer = React.lazy(() => import('some-phone-lib'))
// Wrap usage in <Suspense fallback={<Spinner />}>
```

**Acceptance criteria:**
- `npm run build` completes with no chunk size warnings, or all remaining warnings are acknowledged and documented in a comment
- Dashboard loads correctly in browser after build

---

## 🟢 FIX 5 — Remove/Update Dangling WebSocket Test Script

**File:** `test_api.py`

**Problem:**
The script targets legacy paths (`/speech-to-text-translate/ws`) and the deprecated `saaras:v3` model. The actual STT pipeline is now Groq Whisper (`whisper-large-v3`). This file is a trap for any developer testing the stack.

**Fix:**
Two acceptable approaches — pick one:

**Option A (Recommended) — Update the script:**
```python
# BEFORE
WS_URL = "ws://localhost:8000/speech-to-text-translate/ws"
MODEL   = "saaras:v3"

# AFTER
# STT is now handled by Groq Whisper via REST, not a local WebSocket
# Use the actual /calls or /enrich endpoint for integration tests
import httpx
response = httpx.post("http://localhost:8000/api/v1/calls", json={...})
```

**Option B — Delete and document:**
Delete `test_api.py` entirely and add a note in `README.md` or `CONTRIBUTING.md`:
```markdown
## Testing
Integration tests live in `tests/`. Do not use the legacy `test_api.py` — it has been removed.
STT is handled by Groq Whisper (REST). Use `pytest tests/integration/` for end-to-end coverage.
```

**Acceptance criteria:**
- No file in the repo references `/speech-to-text-translate/ws` or `saaras:v3`
- A developer following the test instructions in the README can run tests without hitting legacy paths

---

## PR Checklist

Before opening the pull request, confirm:

- [ ] `celery worker` starts without `ImportError` (Fix 1)
- [ ] `assets/fallbacks/` has all 5 audio files, each > 0 bytes (Fix 2)
- [ ] `pytest tests/test_hermes_hooks.py` passes (Fix 3)
- [ ] `npm run build` exits with no chunk warnings (Fix 4)
- [ ] No references to `saaras:v3` or `/speech-to-text-translate/ws` in codebase (Fix 5)
- [ ] Railway deployment goes from `CRASHED` → `ACTIVE` after merge

**Do not introduce new dependencies, refactor unrelated modules, or change database schema in this PR.**
