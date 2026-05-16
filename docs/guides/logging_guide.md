# Session Logging Guide

The Context Optimizer proxy includes session logging to track usage and collect training data for compression/routing optimizations.

> **Important:** Understand [terminology.md](./terminology.md) first to know what "session", "turn", and "round" mean in the context of agentic workflows.

## Two Logging Modes

**Quick terminology note:** 
- A "turn" in our logs = one proxy request (each time Cursor calls our API)
- One human message can result in MULTIPLE turns due to tool executions
- See [terminology.md](./terminology.md) for detailed explanation

### 1. Minimal Logging (Default, Recommended for Production)

**Setting:**
```bash
ENABLE_FULL_SESSION_LOGGING=false
```

**What it logs:**
- Session ID and turn number
- Timestamp
- Model used
- Token count estimate
- Message count
- User message preview (first 200 characters)

**Disk usage:** ~1-5 KB per session

**When to use:** Daily usage, production monitoring, when you don't need full message history

**Example log entry:**
```json
{
  "session_id": "abc123",
  "turn": 5,
  "timestamp": "2026-05-15T12:00:00Z",
  "model": "claude-3-opus",
  "message_count": 42,
  "estimated_tokens": 15234,
  "user_message_preview": "Fix the bug in the calculator app where decimal button...",
  "full_logging_disabled": true
}
```

---

### 2. Full Session Logging (Data Collection Mode)

**Setting:**
```bash
ENABLE_FULL_SESSION_LOGGING=true
```

**What it logs:**
- Everything from minimal mode PLUS:
- Complete message history (system prompt, user messages, assistant responses, tool calls, tool results)
- Full message content for every turn

**Disk usage:** ~10-100 MB per session (depending on session length and complexity)

**When to use:** 
- When collecting training data for compression analysis
- When building model routing classifier
- When debugging specific sessions
- During Phase 1 data collection (1-2 weeks)

**WARNING:** This mode can quickly fill up disk space. Use sparingly and compress old sessions.

**Example log entry:**
```json
{
  "session_id": "abc123",
  "turn": 5,
  "timestamp": "2026-05-15T12:00:00Z",
  "model": "claude-3-opus",
  "message_count": 42,
  "estimated_tokens": 15234,
  "messages": [
    {"role": "system", "content": "You are an AI coding assistant..."},
    {"role": "user", "content": "Fix the bug in the calculator..."},
    {"role": "assistant", "content": [{"type": "tool_use", ...}]},
    // ... full message history
  ]
}
```

---

## Switching Between Modes

1. **Enable full logging** (for data collection):
   ```bash
   # Edit .env
   ENABLE_FULL_SESSION_LOGGING=true
   
   # Restart proxy
   uvicorn context_optimizer.main:app --reload
   ```

2. **Disable full logging** (back to normal):
   ```bash
   # Edit .env
   ENABLE_FULL_SESSION_LOGGING=false
   
   # Restart proxy
   uvicorn context_optimizer.main:app --reload
   ```

---

## Managing Disk Space

### During data collection (full logging enabled):

1. **Set a collection window**: Run full logging for 1-2 weeks only
2. **Monitor disk usage**: `du -sh logs/sessions/`
3. **Compress old sessions**:
   ```bash
   # Compress sessions older than 7 days
   find logs/sessions/ -name "*.jsonl" -mtime +7 -exec gzip {} \;
   ```
4. **Archive for analysis**:
   ```bash
   # Move to separate analysis directory
   mkdir -p analysis/raw_sessions
   mv logs/sessions/2026-05-14_May_14 analysis/raw_sessions/
   ```

### During normal use (minimal logging):

- Logs are small enough to keep indefinitely
- Rotate logs monthly if needed
- Use simple log rotation tools

---

## Accessing Logged Sessions

### Via web UI:
```
http://localhost:8000/ui
```

Browse sessions, view turns, inspect messages (if full logging was enabled for that session).

### Via command line:
```bash
# List all sessions
ls logs/sessions/

# View a specific session
cat logs/sessions/session_abc123.jsonl | jq

# Count turns in a session
wc -l logs/sessions/session_abc123.jsonl

# Extract just metadata (works with both modes)
cat logs/sessions/session_abc123.jsonl | jq '{session_id, turn, model, estimated_tokens}'
```

---

## Recommendation

**For most users:** Keep `ENABLE_FULL_SESSION_LOGGING=false` (default)

**Only enable full logging when:**
- You're implementing Phase 1 (data collection for compression research)
- You're training the routing classifier (Phase 5)
- You're debugging a specific issue and need full message history
- You're analyzing compression opportunities

**Always disable after collecting sufficient data.**
