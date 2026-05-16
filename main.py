import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv

from compressor import process_and_compress_context
from logger import log_token_savings, session_logger, estimate_tokens
from ui import router as ui_router
from ab_testing.framework.strategies import apply_strategy

# Load environment variables (API keys are automatically picked up by litellm)
load_dotenv()

app = FastAPI(title="Context Optimizer Proxy")
app.include_router(ui_router)

# MODEL ALIAS TABLE
# Cursor rejects model names that contain "/" so we define simple aliases here.
# Add any model you want to use in Cursor using a plain name (no slashes).
# The proxy will map the alias to the full OpenRouter model string automatically.
# These can also be set via .env as MODEL_ALIAS_<ALIAS>=<full_model_name>
MODEL_ALIASES = {
    # --- co- prefixed aliases (recommended for Cursor) ---
    # Cursor intercepts known model names (gpt-5, gpt-4o, etc.) and routes them internally.
    # Use co- names in Cursor's custom endpoint to guarantee they go through this proxy.
    "co-claude-sonnet":     "anthropic/claude-sonnet-4-5",
    "co-claude-sonnet-4-5": "anthropic/claude-sonnet-4-5",
    "co-claude-3-5-sonnet": "anthropic/claude-3-5-sonnet-20241022",
    "co-claude-haiku":      "anthropic/claude-3-haiku-20240307",
    "co-claude-opus":       "anthropic/claude-3-opus-20240229",
    "co-gpt4o":             "openai/gpt-4o",
    "co-gpt4o-mini":        "openai/gpt-4o-mini",
    "co-gpt5":              "openai/gpt-5",
    "co-gpt5.5":            "openai/gpt-5.5",
    "co-gemini-pro":        "google/gemini-pro-1.5",
    "co-gemini-flash":      "google/gemini-flash-1.5",
    "co-deepseek":          "deepseek/deepseek-r1",
    "co-deepseek-flash":    "deepseek/deepseek-v4-flash",
    # --- Slash names (passthrough) ---
    "anthropic/claude-sonnet-4-5":          "anthropic/claude-sonnet-4-5",
    "anthropic/claude-3-5-sonnet-20241022": "anthropic/claude-3-5-sonnet-20241022",
    "anthropic/claude-3-haiku":             "anthropic/claude-3-haiku-20240307",
    "anthropic/claude-3-haiku-20240307":    "anthropic/claude-3-haiku-20240307",
    "anthropic/claude-3-opus":              "anthropic/claude-3-opus-20240229",
    "anthropic/claude-3-opus-20240229":     "anthropic/claude-3-opus-20240229",
    "openai/gpt-4o":                        "openai/gpt-4o",
    "openai/gpt-4o-mini":                   "openai/gpt-4o-mini",
    "openai/gpt-5":                         "openai/gpt-5",
    "openai/gpt-5.5":                       "openai/gpt-5.5",
    "google/gemini-pro-1.5":                "google/gemini-pro-1.5",
    "google/gemini-flash-1.5":              "google/gemini-flash-1.5",
    "deepseek/deepseek-r1":                 "deepseek/deepseek-r1",
    "deepseek/deepseek-v4-flash":           "deepseek/deepseek-v4-flash",
}

def normalize_tools(tools: list) -> list:
    """
    Cursor sends tools in Anthropic native format {name, description, input_schema}
    for Claude models, but OpenAI format {type, function: {name, description, parameters}}
    for other models. OpenRouter's /v1/chat/completions endpoint expects OpenAI format.
    This converts Anthropic-format tools to OpenAI format so OpenRouter can route them correctly.
    """
    if not tools:
        return tools
    normalized = []
    for tool in tools:
        if "function" in tool:
            normalized.append(tool)  # Already OpenAI format
        else:
            # Anthropic format → OpenAI format
            normalized.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                }
            })
    return normalized


def normalize_tool_choice(tool_choice) -> dict | None:
    """Convert Anthropic-format tool_choice to OpenAI format."""
    if not isinstance(tool_choice, dict):
        return tool_choice
    if tool_choice.get("type") == "tool":
        # Anthropic: {"type": "tool", "name": "Shell"} → OpenAI: {"type": "function", "function": {"name": "Shell"}}
        name = tool_choice.get("name", "")
        if not name.strip():
            return {"type": "auto"}
        return {"type": "function", "function": {"name": name}}
    return tool_choice


@app.get("/v1/models")
async def list_models():
    """
    Cursor calls this endpoint to validate model names.
    We return our alias list so Cursor accepts them.
    """
    model_list = [
        {"id": alias, "object": "model", "owned_by": "context-optimizer"}
        for alias in MODEL_ALIASES
    ]
    return JSONResponse({"object": "list", "data": model_list})

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Intercepts the OpenAI-compatible chat completion request from Cursor.
    Compresses the context if necessary, then forwards to the target model using litellm.
    """
    body = await request.json()
    
    # Extract API overrides from headers (useful for test scripts)
    force_full_logging = request.headers.get("x-proxy-full-logging", "false").lower() == "true"
    custom_log_dir = request.headers.get("x-proxy-log-dir")
    # Explicit session key for A/B test framework — forces a fresh session per test run/strategy
    session_key = request.headers.get("x-proxy-session-key")
    
    # 1. Extract exactly what Cursor is asking for
    requested_model = body.get("model")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    
    # In Cursor, users often just add "claude-3-opus" or "gpt-4o" in the UI.
    # If they are routing everything to OpenRouter, we need to ensure the model string
    # is properly formatted for OpenRouter if it doesn't already have a provider prefix.
    # You can customize this mapping based on how you name models in the Cursor UI.
    
    # --- ROUTING LOGIC ---
    DEFAULT_BACKEND = os.getenv("DEFAULT_BACKEND", "openrouter")

    # Step 1: Resolve alias (e.g. "claude-sonnet-4-5" -> "anthropic/claude-sonnet-4-5")
    if requested_model in MODEL_ALIASES:
        requested_model = MODEL_ALIASES[requested_model]
        print(f"[PROXY] Alias resolved → {requested_model}")

    # Step 2: Explicit CO_ override bypasses default backend
    # e.g. "CO_anthropic/claude-3-opus" sends directly to Anthropic (not OpenRouter)
    if requested_model.startswith("CO_"):
        # CO_ prefix: strip it and send directly (no backend prepended)
        requested_model = requested_model[3:]
        print(f"[PROXY] CO_ override → {requested_model}")
    else:
        # For OpenRouter direct HTTP calls we do NOT prepend "openrouter/".
        # OpenRouter expects model IDs like "anthropic/claude-sonnet-4-5" (not "openrouter/anthropic/...")
        # We only prepend the backend if it's NOT openrouter (e.g. for future direct Anthropic/OpenAI routing).
        if DEFAULT_BACKEND != "openrouter" and not requested_model.startswith(f"{DEFAULT_BACKEND}/"):
            requested_model = f"{DEFAULT_BACKEND}/{requested_model}"

    print(f"[PROXY] Routing to → {requested_model}")
    # --- END ROUTING LOGIC ---
        
    # We pass the rest of the arguments (temperature, max_tokens, etc.) directly.
    # Exclude model, messages, and stream since we handle those explicitly.
    kwargs = {k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}

    # Cursor sends its own tool definitions for agentic features (file editing, terminal, etc.).
    # Some of these may have empty names which OpenRouter/Anthropic reject outright.
    # 2. Apply preprocessing strategies (noise stripping, etc.)
    strategy = os.getenv("AB_TEST_STRATEGY", "none")
    if strategy != "none":
        try:
            messages = apply_strategy(strategy, messages)
            print(f"[PROXY] Applied preprocessing strategy: {strategy}")
        except Exception as e:
            print(f"[PROXY] Warning: Strategy {strategy} failed: {e}")
    
    # Extract disable_default_logging from headers
    disable_default_logging = request.headers.get("x-proxy-disable-default-logging", "false").lower() == "true"

    # 3. Evaluate and Compress the Context
    bypass = os.getenv("BYPASS_COMPRESSION", "false").lower() == "true"
    if bypass:
        compressed_messages, was_compressed, orig_tokens, comp_tokens = messages, False, 0, 0
        print(f"[PROXY] Compression BYPASSED (BYPASS_COMPRESSION=true)")
    else:
        compressed_messages, was_compressed, orig_tokens, comp_tokens = process_and_compress_context(messages, disable_default_logging=disable_default_logging)
    
    # 4. Log the savings if compression occurred
    if was_compressed and not disable_default_logging:
        cheap_model = os.getenv("CHEAP_MODEL_NAME", "openrouter/google/gemini-flash-1.5")
        log_token_savings(
            expensive_model=requested_model,
            original_token_count=orig_tokens,
            compressed_token_count=comp_tokens,
            cheap_model_used=cheap_model
        )

    # 5. Forward the request via LiteLLM
    # LiteLLM automatically knows how to route to Anthropic, OpenAI, or OpenRouter 
    # based purely on the model string (e.g., "anthropic/claude-3-opus", "gpt-4o", "openrouter/...")
    # It will automatically use the correct API key from the .env file.
    
    # --- BUILD FINAL REQUEST BODY ---
    # Normalize tools: Cursor sends Anthropic-format tools for Claude models but OpenRouter
    # expects OpenAI format on its /v1/chat/completions endpoint.
    raw_tools = body.get("tools")
    normalized_tools = normalize_tools(raw_tools) if raw_tools else raw_tools
    raw_tc = body.get("tool_choice")
    normalized_tc = normalize_tool_choice(raw_tc)

    # Strip OpenAI-specific fields that some backends reject; keep everything else.
    clean_body = {k: v for k, v in body.items() if k not in ["stream_options", "tools", "tool_choice"]}
    final_body = {**clean_body, "model": requested_model, "messages": compressed_messages}
    if normalized_tools is not None:
        final_body["tools"] = normalized_tools
    if normalized_tc is not None:
        final_body["tool_choice"] = normalized_tc


    tools_summary = f"{len(body['tools'])} tools" if "tools" in body else "no tools"
    tool_choice = body.get("tool_choice")
    print(f"[IN]  messages={len(messages)} compressed={was_compressed} {tools_summary} tool_choice={tool_choice!r} → {requested_model}")

    # Session logging — save every turn so we can analyse patterns later
    try:
        def extract_text(m):
            content = m.get("content")
            if content is None:
                return ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return ""

        raw_token_count = estimate_tokens("".join(extract_text(m) for m in messages))
        
        # Extract system prompt: either from body.system or from first message with role="system"
        system_prompt = body.get("system")
        if not system_prompt and messages and messages[0].get("role") == "system":
            system_prompt = messages[0].get("content", "")
            
        def log_this_turn(assistant_msg=None, actual_usage=None):
            try:
                msgs_to_log = list(compressed_messages)
                if assistant_msg:
                    msgs_to_log.append(assistant_msg)
                
                tokens = raw_token_count
                if actual_usage and "total_tokens" in actual_usage:
                    tokens = actual_usage["total_tokens"]
                    
                # Extract disable_default_logging from headers
                disable_default_logging = request.headers.get("x-proxy-disable-default-logging", "false").lower() == "true"
                    
                session_logger.log_turn(
                    msgs_to_log, 
                    requested_model, 
                    tokens,
                    force_full_logging=force_full_logging,
                    custom_log_dir=custom_log_dir,
                    session_key=session_key,
                    system=system_prompt,
                    tools=body.get("tools"),
                    disable_default_logging=disable_default_logging
                )
            except Exception as log_e:
                print(f"[ERROR] Session logging failed: {log_e}")
                
    except Exception as e:
        print(f"[ERROR] Logging preparation failed: {e}")
        return {"error": f"Logging preparation failed: {e}"}

    # Dump full request body for debugging (skip if disabled)
    if not disable_default_logging:
        import pathlib
        pathlib.Path("logs/last_request.json").write_text(json.dumps(body, indent=2))

    # --- ROUTING: Anthropic models → Anthropic API directly; everything else → OpenRouter ---
    # Cursor sends requests in Anthropic's native format for Claude models (messages with
    # tool_use/tool_result content blocks, tools with input_schema). OpenRouter's OpenAI-
    # compatible endpoint can't cleanly convert this format, so we go direct to Anthropic.
    is_anthropic = requested_model.startswith("anthropic/")

    if is_anthropic:
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        if not ANTHROPIC_API_KEY:
            return JSONResponse({"error": "ANTHROPIC_API_KEY not set in .env"}, status_code=500)

        # Build Anthropic-native request body from what Cursor already sent
        anthropic_model = requested_model.replace("anthropic/", "", 1)
        
        # Convert messages to Anthropic format
        # OpenAI format assistant messages may have tool_calls, which need to be converted to content blocks
        # OpenAI format "tool" role messages need to be converted to user messages with tool_result blocks
        anthropic_messages = []
        for msg in compressed_messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                # Convert OpenAI tool_calls to Anthropic content blocks
                content_blocks = []
                # Add text content if present
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                # Convert tool_calls to tool_use blocks
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {}),
                    })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            elif msg.get("role") == "tool":
                # Anthropic doesn't support role="tool", convert to user message with tool_result
                content = msg.get("content", "")
                # Extract text from content if it's a list (Anthropic format)
                if isinstance(content, list):
                    text = " ".join(item.get("text", "") for item in content if isinstance(item, dict))
                else:
                    text = content
                
                tool_use_id = msg.get("tool_use_id") or msg.get("tool_call_id", "")
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": text
                    }]
                })
            else:
                # Keep user messages as-is
                anthropic_messages.append(msg)
        
        anthropic_body = {
            "model": anthropic_model,
            "messages": anthropic_messages,
            "max_tokens": final_body.get("max_tokens", 8192),
            "stream": stream,
        }
        # Forward optional fields if present
        for field in ("system", "tools", "tool_choice", "temperature", "top_p", "stop_sequences", "metadata"):
            if field in final_body:
                anthropic_body[field] = final_body[field]
            elif field in body:
                anthropic_body[field] = body[field]

        # Restore tools to Anthropic format (undo the OpenAI normalization above)
        if "tools" in anthropic_body:
            anthropic_tools = []
            for t in anthropic_body["tools"]:
                if "function" in t:
                    fn = t["function"]
                    anthropic_tools.append({
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    })
                else:
                    anthropic_tools.append(t)
            anthropic_body["tools"] = anthropic_tools

        # Debug: show what we're actually sending to Anthropic
        print(f"[DEBUG] anthropic_body keys: {list(anthropic_body.keys())}")
        print(f"[DEBUG] anthropic_body['system']: {anthropic_body.get('system', 'MISSING')[:80] if anthropic_body.get('system') else 'MISSING'}")
        print(f"[DEBUG] anthropic_body['tools']: {len(anthropic_body.get('tools', []))} tools")
        
        # Restore tool_choice to Anthropic format
        if "tool_choice" in anthropic_body:
            tc = anthropic_body["tool_choice"]
            if isinstance(tc, dict) and tc.get("type") == "function":
                anthropic_body["tool_choice"] = {"type": "tool", "name": tc.get("function", {}).get("name", "")}

        anthropic_headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        print(f"[PROXY] → Anthropic direct: {anthropic_model} stream={stream}")
        print(f"[PROXY] Sending to Anthropic: system={'present' if anthropic_body.get('system') else 'MISSING'}, tools={len(anthropic_body.get('tools', []))} tools")

        try:
            if stream:
                async def generate_anthropic_stream():
                    """Convert Anthropic SSE events to OpenAI SSE format for Cursor."""
                    import uuid, time
                    gen_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
                    created = int(time.time())
                    input_tokens = 0
                    
                    accumulated_content = ""
                    accumulated_tool_calls = []

                    async with httpx.AsyncClient(timeout=300) as client:
                        async with client.stream(
                            "POST", "https://api.anthropic.com/v1/messages",
                            json=anthropic_body, headers=anthropic_headers
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                if line.startswith("event:"):
                                    continue
                                if not line.startswith("data:"):
                                    continue
                                raw = line[5:].strip()
                                if not raw:
                                    continue
                                try:
                                    ev = json.loads(raw)
                                except Exception:
                                    continue

                                etype = ev.get("type", "")

                                if etype == "message_start":
                                    usage = ev.get("message", {}).get("usage", {})
                                    input_tokens = usage.get("input_tokens", 0)
                                    chunk = {"id": gen_id, "object": "chat.completion.chunk", "created": created,
                                             "model": requested_model,
                                             "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}
                                    yield f"data: {json.dumps(chunk)}\n\n"

                                elif etype == "content_block_start":
                                    block = ev.get("content_block", {})
                                    btype = block.get("type")
                                    if btype == "tool_use":
                                        # Start of a tool call
                                        tool_idx = ev.get("index", 0)
                                        # Ensure array is large enough
                                        while len(accumulated_tool_calls) <= tool_idx:
                                            accumulated_tool_calls.append({
                                                "id": "",
                                                "type": "function",
                                                "function": {"name": "", "arguments": ""}
                                            })
                                        accumulated_tool_calls[tool_idx]["id"] = block.get("id", "")
                                        accumulated_tool_calls[tool_idx]["function"]["name"] = block.get("name", "")
                                        
                                        chunk = {"id": gen_id, "object": "chat.completion.chunk", "created": created,
                                                 "model": requested_model,
                                                 "choices": [{"index": 0, "delta": {
                                                     "tool_calls": [{"index": tool_idx, "id": block.get("id", ""),
                                                                     "type": "function",
                                                                     "function": {"name": block.get("name", ""), "arguments": ""}}]
                                                 }, "finish_reason": None}]}
                                        yield f"data: {json.dumps(chunk)}\n\n"

                                elif etype == "content_block_delta":
                                    delta = ev.get("delta", {})
                                    dtype = delta.get("type")
                                    tool_idx = ev.get("index", 0)
                                    if dtype == "text_delta":
                                        text = delta.get("text", "")
                                        accumulated_content += text
                                        chunk = {"id": gen_id, "object": "chat.completion.chunk", "created": created,
                                                 "model": requested_model,
                                                 "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                                        yield f"data: {json.dumps(chunk)}\n\n"
                                    elif dtype == "input_json_delta":
                                        partial = delta.get("partial_json", "")
                                        if len(accumulated_tool_calls) > tool_idx:
                                            accumulated_tool_calls[tool_idx]["function"]["arguments"] += partial
                                        chunk = {"id": gen_id, "object": "chat.completion.chunk", "created": created,
                                                 "model": requested_model,
                                                 "choices": [{"index": 0, "delta": {
                                                     "tool_calls": [{"index": tool_idx, "function": {"arguments": partial}}]
                                                 }, "finish_reason": None}]}
                                        yield f"data: {json.dumps(chunk)}\n\n"

                                elif etype == "message_delta":
                                    usage = ev.get("usage", {})
                                    output_tokens = usage.get("output_tokens", 0)
                                    stop_reason = ev.get("delta", {}).get("stop_reason")
                                    finish = "tool_calls" if stop_reason == "tool_use" else "stop"
                                    chunk = {"id": gen_id, "object": "chat.completion.chunk", "created": created,
                                             "model": requested_model,
                                             "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                                             "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens,
                                                       "total_tokens": input_tokens + output_tokens}}
                                    yield f"data: {json.dumps(chunk)}\n\n"

                                elif etype == "message_stop":
                                    yield "data: [DONE]\n\n"
                                    
                    # Log at the end of stream
                    assistant_msg = {"role": "assistant"}
                    if accumulated_content:
                        assistant_msg["content"] = accumulated_content
                    if accumulated_tool_calls:
                        assistant_msg["tool_calls"] = accumulated_tool_calls
                    log_this_turn(assistant_msg=assistant_msg, actual_usage={"total_tokens": input_tokens + output_tokens})

                return StreamingResponse(generate_anthropic_stream(), media_type="text/event-stream")

            else:
                async with httpx.AsyncClient(timeout=300) as client:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        json=anthropic_body, headers=anthropic_headers
                    )
                    result = resp.json()
                    if "error" in result:
                        print(f"[ERROR] Anthropic: {json.dumps(result['error'])}")
                        return JSONResponse(result, status_code=resp.status_code)
                    # Convert Anthropic response format to OpenAI format
                    content_blocks = result.get("content", [])
                    text = " ".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                    tool_calls = [
                        {"id": b.get("id", ""), "type": "function",
                         "function": {"name": b.get("name", ""), "arguments": json.dumps(b.get("input", {}))}}
                        for b in content_blocks if b.get("type") == "tool_use"
                    ]
                    message = {"role": "assistant", "content": text or None}
                    if tool_calls:
                        message["tool_calls"] = tool_calls
                    usage = result.get("usage", {})
                    openai_resp = {
                        "id": result.get("id", ""),
                        "object": "chat.completion",
                        "model": requested_model,
                        "choices": [{"index": 0, "message": message, "finish_reason": result.get("stop_reason", "stop")}],
                        "usage": {"prompt_tokens": usage.get("input_tokens", 0),
                                  "completion_tokens": usage.get("output_tokens", 0),
                                  "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)},
                    }
                    print(f"[OUT] Anthropic response preview={text[:120]!r}")
                    log_this_turn(assistant_msg=message, actual_usage=openai_resp["usage"])
                    return JSONResponse(openai_resp)

        except Exception as e:
            print(f"[ERROR] Anthropic direct call failed: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    else:
        # --- NON-ANTHROPIC: forward to OpenRouter ---
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
        }

        try:
            if stream:
                async def generate_stream():
                    accumulated_content = ""
                    async with httpx.AsyncClient(timeout=120) as client:
                        async with client.stream("POST", OPENROUTER_URL, json=final_body, headers=headers) as resp:
                            async for line in resp.aiter_lines():
                                if line:
                                    print(f"[OUT] {line[:300]}")
                                    yield line + "\n\n"
                                    if line.startswith("data: "):
                                        try:
                                            data = json.loads(line[6:])
                                            delta = data.get("choices", [{}])[0].get("delta", {})
                                            if "content" in delta and delta["content"]:
                                                accumulated_content += delta["content"]
                                        except Exception:
                                            pass
                    log_this_turn(assistant_msg={"role": "assistant", "content": accumulated_content})

                return StreamingResponse(generate_stream(), media_type="text/event-stream")
            else:
                print(f"[PROXY] Sending to OpenRouter: system={'present' if final_body.get('system') or any(m.get('role')=='system' for m in final_body.get('messages',[])) else 'MISSING'}, tools={len(final_body.get('tools', []))} tools")
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(OPENROUTER_URL, json=final_body, headers=headers)
                    result = resp.json()
                    if "error" in result:
                        print(f"[ERROR] OpenRouter: {json.dumps(result['error'])}")
                    else:
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        print(f"[OUT] response_preview={(content or '')[:120]!r}")
                        assistant_msg = result.get("choices", [{}] )[0].get("message", {})
                        usage = result.get("usage", {})
                        log_this_turn(assistant_msg=assistant_msg, actual_usage=usage)
                    return result

        except Exception as e:
            import traceback
            print(f"[ERROR] Direct OpenRouter call failed: {e}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Starting Context Optimizer Proxy on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)