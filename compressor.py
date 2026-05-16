import os
from typing import List, Dict, Any
from litellm import completion
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MAX_MESSAGES_BEFORE_COMPRESS = int(os.getenv("MAX_MESSAGES_BEFORE_COMPRESS", 10))
KEEP_LAST_N_MESSAGES = int(os.getenv("KEEP_LAST_N_MESSAGES", 4))
CHEAP_MODEL_NAME = os.getenv("CHEAP_MODEL_NAME", "openrouter/google/gemini-flash-1.5")
API_KEY = os.getenv("OPENROUTER_API_KEY")

def summarize_messages(messages_to_summarize: List[Dict[str, str]]) -> str:
    """
    Sends the older messages to the cheap model to generate a compact summary.
    """
    if not messages_to_summarize:
        return ""
        
    # Create a prompt for the cheap model
    prompt = "Please provide a highly compact, detailed summary of the following conversation history. Retain all key technical details, code snippets, user goals, and important context. Do not include conversational filler.\n\n"
    
    for msg in messages_to_summarize:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        prompt += f"[{role}]:\n{content}\n\n"
        
    # Call the cheap model via litellm
    try:
        response = completion(
            model=CHEAP_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            api_key=API_KEY
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error during summarization: {e}")
        # If summarization fails, fallback to keeping the raw text (safety net)
        return prompt

def process_and_compress_context(messages: List[Dict[str, Any]], disable_default_logging: bool = False) -> tuple[List[Dict[str, Any]], bool, int, int]:
    """
    Evaluates the message list based on token count, not just message count.
    If it exceeds the threshold, it splits the history:
    - Keeps the System prompt (if any).
    - Keeps the last N recent messages.
    - Summarizes the middle messages using a cheap model.
    
    Returns: (compressed_messages, was_compressed, original_tokens, compressed_tokens)
    """
    from logger import estimate_tokens
    
    # Calculate original token count.
    # Content can be a string or a list (multimodal), so we handle both safely.
    def extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        return ""
    
    original_text = "".join(extract_text(m.get("content", "")) for m in messages)
    original_tokens = estimate_tokens(original_text)
    
    # Check if we should compress based on tokens, rather than purely message count
    MAX_TOKENS_BEFORE_COMPRESS = int(os.getenv("MAX_TOKENS_BEFORE_COMPRESS", 16000))
    
    if original_tokens <= MAX_TOKENS_BEFORE_COMPRESS and len(messages) <= MAX_MESSAGES_BEFORE_COMPRESS:
        return messages, False, original_tokens, original_tokens

    compressed_messages = []
    
    # 1. Identify and preserve the system prompt (usually the first message)
    start_idx = 0
    if messages and messages[0].get("role") == "system":
        compressed_messages.append(messages[0])
        start_idx = 1
        
    # 2. Identify the messages to summarize (everything in the middle)
    end_idx = len(messages) - KEEP_LAST_N_MESSAGES
    
    if end_idx <= start_idx:
        # Not enough messages to compress after saving system & recent
        return messages, False, original_tokens, original_tokens
        
    messages_to_summarize = messages[start_idx:end_idx]
    recent_messages = messages[end_idx:]
    
    # 3. Call the cheap model
    summary_text = summarize_messages(messages_to_summarize)
    
    # 4. Inject the summary as an assistant/system note
    summary_message = {
        "role": "system", 
        "content": f"[SYSTEM NOTE: The following is a compressed summary of the older conversation history to save tokens.]\n\n{summary_text}"
    }
    compressed_messages.append(summary_message)
    
    # 5. Append the recent messages
    compressed_messages.extend(recent_messages)
    
    # Calculate compressed token count
    compressed_text = "".join(extract_text(m.get("content", "")) for m in compressed_messages)
    compressed_tokens = estimate_tokens(compressed_text)
    
    # Log the full payloads for debugging (rolling buffer)
    if not disable_default_logging:
        from logger import log_debug_context
        log_debug_context(messages, compressed_messages)
    
    return compressed_messages, True, original_tokens, compressed_tokens
