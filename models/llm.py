import time
from openai import OpenAI
from config.config import OPENROUTER_API_KEY


# All currently active free models on OpenRouter (verified live)
FALLBACK_MODELS = [
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-coder:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3-27b-it:free",
]

# Models that do NOT support system role messages
NO_SYSTEM_ROLE_MODELS = ["google/gemma-3-12b-it:free", "google/gemma-3-27b-it:free"]


def get_openrouter_client():

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    return client


def _prepare_messages(model, messages):
    """
    Some models (e.g. Gemma) don't support 'system' role.
    Merge any system message into the first user message instead.
    """
    needs_conversion = any(keyword in model.lower() for keyword in ["gemma"])

    if not needs_conversion:
        return messages

    system_parts = []
    other_messages = []

    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            other_messages.append(msg)

    if system_parts and other_messages:
        # Prepend system instructions to first user message
        system_text = "\n".join(system_parts)
        first_msg = other_messages[0]
        if first_msg["role"] == "user":
            other_messages[0] = {
                "role": "user",
                "content": f"Instructions: {system_text}\n\n{first_msg['content']}"
            }
        else:
            # Insert as a user message at the start
            other_messages.insert(0, {"role": "user", "content": system_text})

    return other_messages if other_messages else messages


def generate_response(model, messages, max_retries=2):
    """
    Try the selected model first. If it fails with a recoverable error
    (429 rate-limit, 404 not found, 400 bad request, 402 payment),
    automatically retry with fallback models.
    """

    client = get_openrouter_client()

    # Build ordered list: user's chosen model first, then fallbacks
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    last_error = None
    recoverable_codes = ["429", "404", "400", "402", "503"]

    for current_model in models_to_try:
        prepared_messages = _prepare_messages(current_model, messages)

        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    model=current_model,
                    messages=prepared_messages,
                )
                return completion.choices[0].message.content

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check if it's a recoverable error
                is_recoverable = any(code in error_str for code in recoverable_codes)

                if is_recoverable:
                    # For rate limits, wait briefly before retry
                    if "429" in error_str and attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        break  # move to next model
                else:
                    # Unknown error — raise immediately
                    raise e

    # If we exhausted all models, raise a clear error
    raise Exception(
        f"All models are currently unavailable. Last error: {last_error}\n"
        "Tip: Your OpenRouter API key may have exceeded its spend limit. "
        "Check your account at https://openrouter.ai/settings/keys"
    )