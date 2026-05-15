# Context Optimizer Design

## Architecture
```text
[ Cursor IDE ] 
     |
     | (Standard OpenAI API Request: {"model": "openai/gpt-4o", "messages": [...]})
     v
[ FastAPI Local Server (http://localhost:8000/v1) ]
     |
     |--> 1. Intercept Request
     |--> 2. Evaluate context length. If short -> skip to Step 4.
     |--> 3. If long -> Extract old messages. Send to Cheap Model (OpenRouter) for summarization.
     |       Replace old messages with `{"role": "system", "content": "Summary of previous conversation: ..."}`
     |--> 4. Send the new compressed payload to the originally requested Expensive Model via OpenRouter.
     |
     v
[ OpenRouter API ]
     |
     | (Streaming response chunks)
     v
[ FastAPI Local Server ]
     |
     | (Yield chunks)
     v
[ Cursor IDE ]
```

## Tech Stack
- **Web Framework:** `FastAPI` (for creating the local server easily).
- **Server:** `Uvicorn` (to run the FastAPI app).
- **LLM Routing/Calling:** `litellm` (standardizes API calls, makes it trivial to call OpenRouter models and handle streaming).
- **Language:** Python 3.

## Core Components
1. **`main.py`**: The entry point. Runs the FastAPI server and defines the `/v1/chat/completions` endpoint.
2. **`compressor.py`**: Contains the custom Python rules for evaluating context length and calling the cheap model to summarize history.
4. **`.env`**: Stores the OpenRouter API key and configurable thresholds (e.g., `MAX_MESSAGES_BEFORE_COMPRESS`, `CHEAP_MODEL_NAME`).
5. **`logger.py`**: A minimal V1 logger that only records token counts (Input Tokens to cheap model vs. Output Tokens from cheap model) to track exactly how many tokens are being saved before sending to the expensive model.