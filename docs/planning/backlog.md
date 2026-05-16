# Backlog & Future Features

## 1. Intelligent Logging System
**Goal:** Log the original context, the cheap model's summary, and the expensive model's final response to create a dataset for training a custom compression model in the future.

**The Challenge:**
Cursor sends massive contexts (entire code files) repeatedly with almost every request. Logging the raw JSON payloads for every interaction will result in gigabytes of redundant text, eating up disk space extremely fast.

**Potential Solutions:**
1. **Deduplication / Content Hashing (Preferred):** Instead of saving raw text, hash large code blocks. Store a single "content dictionary" of code blocks, and in the interaction logs, only save the hashes. This solves the root cause of the bloat.
2. **File Compression:** Automatically compress log files using `tar.gz` or `.jsonl.gz`. While this helps, it still stores redundant data.
3. **Conditional Logging:** Only write to the log during turns where the proxy actually decides to trigger a summarization event, ignoring standard short chats.

*Status: Partially implemented. We have full session logging, minimal logging toggles, date-based folder organization, and A/B test isolation. Deep deduplication is deferred.*

## 2. Simple Dashboard / UI
**Goal:** A web-based interface (e.g., using FastAPI's built-in Jinja templates or a lightweight frontend) to manage and monitor the proxy.
**Features (TBD):**
- **Log Viewer:** Display the minimal token savings logs in real-time so we can see the compression working.
- **Recent Context Debugger:** A view showing the raw JSON payload of the last `N` (e.g., 5) requests from Cursor alongside their compressed counterparts. This helps debug what Cursor is actually sending and tune the compression rules. (These logs will be kept in a small, rotating buffer file so they don't eat disk space).
- **Dynamic Configuration:** Allow changing the cheap summarizer model on the fly without editing the `.env` file.
- **Rule Editor:** A text area to write or tweak the custom Python compression rules dynamically without restarting the server.
*Status: Partially implemented. We have a robust session viewer UI (`ui.py`) that supports both live proxy logs and A/B test runs. Dynamic config/rule editing is deferred to V2.*

## 3. Context Size Management & Auto-Retry with Compression
**Goal:** Never let session size grow beyond model context limit; handle "prompt too long" errors gracefully with automatic compression and retry.

**Features:**
1. **Hard Limit Enforcement:**
   - Set maximum context size `X` where `X <= model_max_context` (e.g., 150k for Claude's 200k limit)
   - Continuously monitor estimated token count (messages + tools)
   - Proactively compress/truncate before sending if approaching limit

2. **Error Recovery with Retry:**
   - Catch "prompt too long" errors from provider APIs (Anthropic, OpenRouter)
   - Automatically trigger aggressive compression/summarization
   - Retry the request with compressed context
   - Fall back to emergency truncation if compression isn't enough
   - Log retry events for analysis

3. **Per-Model Limits:**
   - Configure different limits for different models
   - Claude Sonnet 4.5: 200k → use 150k safety margin
   - GPT-4o: 128k → use 100k safety margin
   - DeepSeek: 64k → use 50k safety margin

4. **Compression Strategies on Retry:**
   - First attempt: Keep system prompt + last 50% of messages, summarize middle
   - Second attempt: Keep system prompt + last 30% of messages, summarize middle
   - Final attempt: Emergency truncation to last 20% of messages only

**Why This Matters:**
- Cursor doesn't compress when routing to custom endpoints (only for their direct models)
- Without this, long sessions fail with "prompt too long" errors
- Automatic retry makes the proxy transparent to the user
- We can test different compression strategies in production

*Status: **High Priority** - Core functionality for production use. Implement after pass-through proxy is stable.*