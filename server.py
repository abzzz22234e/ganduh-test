import os
import time
import traceback
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Environment
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "mistralai/mistral-nemo")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Keep responses short so the bot feels fast
DEFAULT_TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.85"))
DEFAULT_MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "180"))


def _clean_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _latest_from_messages(messages: Any) -> str:
    """
    Handle OpenAI-style messages arrays and common nested payloads.
    Only returns the latest user message, never old history.
    """
    if not isinstance(messages, list) or not messages:
        return ""

    # Prefer the latest explicit user message
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        role = _clean_text(msg.get("role"))
        if role != "user":
            continue

        for key in ("content", "text", "body", "message"):
            txt = _clean_text(msg.get(key))
            if txt:
                return txt

        # Some webhooks wrap the user text deeper
        for nested_key in ("text", "message", "body", "data", "payload"):
            nested = msg.get(nested_key)
            txt = _search_for_text(nested)
            if txt:
                return txt

    # Fallback: last non-empty text anywhere in the array
    for msg in reversed(messages):
        txt = _search_for_text(msg)
        if txt:
            return txt

    return ""


def _search_for_text(obj: Any) -> str:
    """
    Recursive search for the most likely message text in webhook payloads.
    This is intentionally broad because AutoResponder/Render payloads vary.
    """
    if isinstance(obj, str):
        return obj.strip() if obj.strip() else ""

    if isinstance(obj, list):
        # Search from the end because the newest item is usually last
        for item in reversed(obj):
            found = _search_for_text(item)
            if found:
                return found
        return ""

    if not isinstance(obj, dict):
        return ""

    # Common direct keys first
    for key in (
        "q",
        "message",
        "text",
        "prompt",
        "incomingMessage",
        "content",
        "body",
        "bodyText",
        "msg",
        "chat",
        "reply",
        "caption",
    ):
        txt = _clean_text(obj.get(key))
        if txt:
            return txt

    # Common nested shapes
    for parent_key in ("message", "text", "body", "data", "payload", "chat", "conversation"):
        nested = obj.get(parent_key)
        if nested is None:
            continue

        if isinstance(nested, str):
            if nested.strip():
                return nested.strip()

        if isinstance(nested, dict):
            # Try a few likely subkeys
            for subkey in ("body", "text", "content", "message", "msg", "caption"):
                txt = _clean_text(nested.get(subkey))
                if txt:
                    return txt

            found = _search_for_text(nested)
            if found:
                return found

        if isinstance(nested, list):
            found = _latest_from_messages(nested)
            if found:
                return found

    return ""


def extract_latest_user_text(data: Dict[str, Any]) -> str:
    """
    Return only the newest user text, with no old history.
    """
    if not isinstance(data, dict):
        return ""

    # First, try common payload locations
    for key in ("q", "message", "text", "prompt", "incomingMessage", "content", "body", "bodyText", "msg"):
        txt = _clean_text(data.get(key))
        if txt:
            return txt

    # If messages is provided, use only the latest user message
    msg_text = _latest_from_messages(data.get("messages"))
    if msg_text:
        return msg_text

    # Search common nested wrappers used by WhatsApp webhooks / autoresponders
    for key in ("data", "payload", "message", "text", "body", "chat", "conversation"):
        nested = data.get(key)
        txt = _search_for_text(nested)
        if txt:
            return txt

    # Last resort: recursive broad search over the whole object
    txt = _search_for_text(data)
    if txt:
        return txt

    return "[NO MESSAGE RECEIVED]"


def build_openrouter_messages(user_text: str) -> List[Dict[str, str]]:
    system_prompt = (
        "You are Moustachio Von Grumble, a loud, cheeky WhatsApp group member. "
        "Reply directly to the user's latest message. "
        "Always address the exact words, names, and topic they mention. "
        "Keep replies short, natural, funny, and conversational. "
        "Use strong personality and casual banter. "
        "Do not mention that you are an AI. "
        "Do not write essays. "
        "Do not ignore the user's actual message. "
        "Do not keep old chat memory unless it is explicitly included in the current input."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]


@app.route("/", methods=["GET"])
def home():
    return jsonify(
        {
            "status": "ok",
            "model": OPENROUTER_MODEL,
        }
    ), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        if not OPENROUTER_API_KEY:
            message = "Server error: OPENROUTER_API_KEY is missing."
            return jsonify(
                {
                    "error": message,
                    "replies": [{"message": message}],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": message},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ), 500

        data = request.get_json(silent=True) or {}

        # Helpful for Render logs while you test
        print("RAW REQUEST:", request.data.decode("utf-8", errors="ignore"))
        print("JSON DATA:", data)

        user_text = extract_latest_user_text(data)
        print("EXTRACTED USER TEXT:", user_text)

        # Allow the client to override model if desired, otherwise use env default
        model = _clean_text(data.get("model")) or OPENROUTER_MODEL

        payload = {
            "model": model,
            "messages": build_openrouter_messages(user_text),
            "temperature": float(data.get("temperature", DEFAULT_TEMPERATURE)),
            "max_tokens": int(data.get("max_tokens", DEFAULT_MAX_TOKENS)),
        }

        # Optional passthroughs
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop", "stream"):
            if key in data:
                payload[key] = data[key]

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": _clean_text(data.get("http_referer")) or "https://autoresponder.local",
            "X-Title": _clean_text(data.get("title")) or "WhatsApp Bot",
            "Content-Type": "application/json",
        }

        upstream = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        try:
            upstream_json = upstream.json()
        except Exception:
            msg = f"OpenRouter returned non-JSON response (status {upstream.status_code})"
            print(msg)
            return jsonify(
                {
                    "error": msg,
                    "replies": [{"message": msg}],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": msg},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ), 502

        if upstream.status_code != 200:
            err_text = f"OpenRouter Error: {upstream_json}"
            print(err_text)
            return jsonify(
                {
                    "error": upstream_json,
                    "replies": [{"message": err_text}],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": err_text},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ), 502

        ai_reply = (
            upstream_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        ).strip()

        if not ai_reply:
            ai_reply = f"I saw this: {user_text}"

        # Return both formats because different bots read different fields
        return jsonify(
            {
                "id": "chatcmpl-local",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": ai_reply,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "replies": [
                    {
                        "message": ai_reply,
                    }
                ],
            }
        ), 200

    except Exception as e:
        err_msg = traceback.format_exc()
        print("CRASH:", err_msg)

        return jsonify(
            {
                "error": str(e),
                "replies": [{"message": f"Crash: {str(e)}"}],
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"Crash: {str(e)}",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)