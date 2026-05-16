import json
import os
import hashlib
from datetime import datetime
from collections import deque

LOG_DIR = os.getenv("LOG_DIR", "logs")
TOKEN_LOG_FILE = os.path.join(LOG_DIR, "token_savings.jsonl")
DEBUG_BUFFER_FILE = os.path.join(LOG_DIR, "debug_buffer.json")
SESSIONS_DIR = os.path.join(LOG_DIR, "sessions")
DEBUG_BUFFER_SIZE = int(os.getenv("DEBUG_BUFFER_SIZE", 5))

# Full session logging flag (saves complete messages - uses lots of disk space)
# Default: false (minimal logging only - token counts and metadata)
# Set to true when collecting training data for compression/routing analysis
ENABLE_FULL_SESSION_LOGGING = os.getenv("ENABLE_FULL_SESSION_LOGGING", "false").lower() == "true"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Session Logger
# ---------------------------------------------------------------------------

class SessionLogger:
    """
    Detects agentic session boundaries and logs each proxy request to a per-session JSONL file.

    TERMINOLOGY:
    - Session: Continuous conversation with same initial context (same system prompt hash)
    - Turn: Each proxy request (what we log). One human message can trigger MULTIPLE turns
            due to tool executions. See docs/guides/terminology.md for detailed explanation.
    - Round: One tool_use + tool_result pair within the conversation

    Session detection: if the first message of the new request matches the first
    message of the previous request (by content hash), it's a continuation of the
    same session. Otherwise it's a new session.

    Each line in the session file is one proxy request (turn):
    {session_id, turn, timestamp, model, message_count, token_count, messages}
    
    NOTE: turn=22 doesn't mean "22 human messages" — it means "22 proxy requests".
    A typical session with 22 turns represents ~5 human interactions, with the rest
    being internal tool execution loops.
    """

    def __init__(self):
        self._session_id: str | None = None
        self._turn: int = 0
        self._first_msg_hash: str | None = None

    def _msg_hash(self, messages: list) -> str:
        """Hash the first message content to identify a session."""
        if not messages:
            return ""
        first = messages[0]
        content = first.get("content", "")
        if isinstance(content, list):
            content = json.dumps(content, sort_keys=True)
        return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()

    def _is_continuation(self, messages: list) -> bool:
        if not self._session_id or not self._first_msg_hash:
            return False
        return self._msg_hash(messages) == self._first_msg_hash

    def log_turn(self, messages: list, model: str, token_count: int, force_full_logging: bool = False, custom_log_dir: str = None, session_key: str = None, system: str = None, tools: list = None) -> tuple[str, int]:
        """
        Log one proxy turn. Returns (session_id, turn_number).
        
        If ENABLE_FULL_SESSION_LOGGING (or force_full_logging) is true: saves full messages for analysis
        If false (default): saves only metadata (tokens, model, counts) to save disk space
        
        If session_key is provided, it forces a specific session (used by A/B test
        framework to keep each run/strategy as its own session even when first
        messages are identical).
        
        system and tools are optional fields that will be logged when full logging is enabled.
        """
        import uuid

        # Explicit session key overrides hash-based detection (used by A/B tests)
        if session_key:
            if self._session_id != session_key:
                # New session boundary - reset turn counter
                self._session_id = session_key
                self._turn = 1
                self._first_msg_hash = self._msg_hash(messages)
            else:
                self._turn += 1
        elif self._is_continuation(messages):
            self._turn += 1
        else:
            self._session_id = uuid.uuid4().hex[:8]
            self._turn = 1
            self._first_msg_hash = self._msg_hash(messages)

        out_dir = SESSIONS_DIR
        if custom_log_dir:
            # If custom_log_dir is provided, put it under LOG_DIR
            out_dir = os.path.join(LOG_DIR, custom_log_dir)
            os.makedirs(out_dir, exist_ok=True)

        session_file = os.path.join(out_dir, f"session_{self._session_id}.jsonl")

        entry = {
            "session_id": self._session_id,
            "turn": self._turn,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model": model,
            "message_count": len(messages),
            "estimated_tokens": token_count,
        }

        do_full_logging = ENABLE_FULL_SESSION_LOGGING or force_full_logging

        # Only save full messages if full logging is enabled
        if do_full_logging:
            entry["messages"] = messages
            if system:
                entry["system"] = system
            if tools:
                entry["tools"] = tools
        else:
            # Minimal logging: just save user message preview and assistant message count
            user_msg = next((m.get("content", "")[:200] for m in reversed(messages) if m.get("role") == "user"), "")
            entry["user_message_preview"] = user_msg
            entry["full_logging_disabled"] = True

        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        log_type = "FULL" if do_full_logging else "MINIMAL"
        print(f"[SESSION:{log_type}] {self._session_id} turn={self._turn} msgs={len(messages)} ~{token_count}tok → {model}")
        return self._session_id, self._turn


# Module-level singleton — shared across all requests in the same server process
session_logger = SessionLogger()


# ---------------------------------------------------------------------------
# Debug buffer (rolling window of last N raw payloads)
# ---------------------------------------------------------------------------

def log_debug_context(original_messages: list, compressed_messages: list):
    buffer = deque(maxlen=DEBUG_BUFFER_SIZE)
    if os.path.exists(DEBUG_BUFFER_FILE):
        try:
            with open(DEBUG_BUFFER_FILE, "r") as f:
                buffer.extend(json.load(f))
        except Exception:
            pass

    buffer.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "original_messages": original_messages,
        "compressed_messages": compressed_messages,
    })

    with open(DEBUG_BUFFER_FILE, "w") as f:
        json.dump(list(buffer), f, indent=2)


# ---------------------------------------------------------------------------
# Token savings log
# ---------------------------------------------------------------------------

def log_token_savings(expensive_model: str, original_token_count: int,
                      compressed_token_count: int, cheap_model_used: str):
    savings = original_token_count - compressed_token_count
    pct = round((savings / original_token_count) * 100, 2) if original_token_count > 0 else 0

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "expensive_model": expensive_model,
        "cheap_model": cheap_model_used,
        "original_tokens": original_token_count,
        "compressed_tokens": compressed_token_count,
        "tokens_saved": savings,
        "savings_pct": pct,
    }

    print(f"\n[COMPRESSION] {original_token_count} → {compressed_token_count} tokens "
          f"({savings} saved, {pct}%) on {expensive_model}\n")

    with open(TOKEN_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Token estimator
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough estimator: ~4 chars per token."""
    return len(text) // 4
