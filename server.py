import os
import time
import traceback
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "mistralai/mistral-nemo")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def extract_latest_user_text(data: Dict[str, Any]) -> str:
    """
    Try hard to find the latest message text from common webhook payload shapes.
    This deliberately ignores old history and returns only the newest user text.
    """

    # Common single-field payload keys
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
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Sometimes nested objects are used
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in ("message", "text", "content", "body", "msg"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested_messages = nested.get("messages")
        if isinstance(nested_messages, list):
            found = _extract_from_messages(nested_messages)
            if found:
                return found

    # OpenAI-style messages array
    messages = data.get("messages")
    if isinstance(messages, list):
        found = _extract_from_messages(messages)
        if found:
            return found

    return "[NO MESSAGE RECEIVED]"


def _extract_from_messages(messages: List[Any]) -> Optional[str]:
    """
    Pull the latest user message from a messages array.
    Falls back to the last non-empty content if needed.
    """
    # Prefer latest user message
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        content = msg.get("content")

        if role == "user" and isinstance(content, str) and content.strip():
            return content.strip()

    # Fallback: last non-empty content anywhere in the list
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue

        for key in ("content", "text", "message", "body"):
            value = msg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def build_openrouter_messages(user_text: str) -> List[Dict[str, str]]:
    system_prompt = (
        "You are Moustachio Von Grumble, a loud, cheeky WhatsApp group member. "
        "Reply directly to the user's latest message. "
        "Always address the exact words, names, and topic they mention. "
        "Be short, natural, funny, and conversational rude and racist. "
        "Use strong personality and rude dark humour  banter. "
        "Do not mention you are an AI. "
        "Do not write essays. "
        "Do not ignore the user's actual message."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        if not OPENROUTER_API_KEY:
            return jsonify({
                "error": "OPENROUTER_API_KEY is missing",
                "replies": [{"message": "Server error: missing OpenRouter API key."}],
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Server error: missing OpenRouter API key."
                    },
                    "finish_reason": "stop"
                }]
            }), 500

        data = request.get_json(silent=True) or {}

        # Helpful while debugging Render / Auto Responder payloads
        print("INCOMING DATA:", data)

        user_text = extract_latest_user_text(data)
        print("EXTRACTED USER TEXT:", user_text)

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": build_openrouter_messages(user_text),
            "temperature": float(data.get("temperature", 0.85)),
            "max_tokens": int(data.get("max_tokens", 180)),
        }

        # Optional passthrough values if your client sends them
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            if key in data:
                payload[key] = data[key]

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": data.get("http_referer", "https://autoresponder.local"),
            "X-Title": data.get("title", "WhatsApp Bot"),
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
            return jsonify({
                "error": msg,
                "replies": [{"message": msg}],
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": msg},
                    "finish_reason": "stop"
                }]
            }), 502

        if upstream.status_code != 200:
            err_text = f"OpenRouter Error: {upstream_json}"
            return jsonify({
                "error": upstream_json,
                "replies": [{"message": err_text}],
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": err_text},
                    "finish_reason": "stop"
                }]
            }), 502

        ai_reply = (
            upstream_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        ).strip()

        if not ai_reply:
            ai_reply = f"I saw this: {user_text}"

        # Return both formats so different clients can read it
        return jsonify({
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": OPENROUTER_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": ai_reply
                    },
                    "finish_reason": "stop"
                }
            ],
            "replies": [
                {
                    "message": ai_reply
                }
            ]
        }), 200

    except Exception as e:
        err_msg = traceback.format_exc()
        print("CRASH:", err_msg)

        return jsonify({
            "error": str(e),
            "replies": [{"message": f"Crash: {str(e)}"}],
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Crash: {str(e)}"
                },
                "finish_reason": "stop"
            }]
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)