import os
import traceback
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "mistralai/mistral-nemo"  # cheap + fast; swap this if needed

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def extract_user_text(data: dict) -> str:
    """
    Pull a usable last user message from a few common payload shapes.
    """
    # Common single-message keys
    for key in ("q", "message", "text", "prompt", "incomingMessage", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # OpenAI-style messages array
    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        # Prefer the latest non-empty user message
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and isinstance(content, str) and content.strip():
                return content.strip()

        # Fallback to the very last non-empty content
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

    return "Hello"


def build_messages(data: dict) -> list:
    """
    Keep the full conversation if provided, but always force our own system prompt.
    """
    system_prompt = (
        "You are Moustachio Von Grumble, a loud, cheeky WhatsApp group member. "
        "Reply to the latest message directly and naturally. "
        "Start by addressing what the user actually said. "
        "You may use sharp banter, rude jokes, and casual profanity, but do not become a generic rant machine. "
        "Keep replies short, conversational, and on-topic. "
        "Do not ignore names, words, or topics from the user. "
        "Do not mention that you are an AI. "
        "Do not write essays. "
        "Do not censor ordinary swear words with asterisks."
    )

    messages = [{"role": "system", "content": system_prompt}]

    incoming = data.get("messages")
    if isinstance(incoming, list) and incoming:
        for msg in incoming:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            content = msg.get("content")

            if role not in ("user", "assistant"):
                continue
            if not isinstance(content, str) or not content.strip():
                continue

            messages.append({"role": role, "content": content.strip()})
    else:
        # Fallback for simple payloads
        messages.append({"role": "user", "content": extract_user_text(data)})

    return messages


@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        if not OPENROUTER_API_KEY:
            return jsonify({
                "replies": [{"message": "Server error: OPENROUTER_API_KEY is missing."}]
            }), 500

        data = request.get_json(silent=True) or {}
        user_text = extract_user_text(data)
        messages = build_messages(data)

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": float(data.get("temperature", 0.8)),
            "max_tokens": int(data.get("max_tokens", 180)),
        }

        # Optional passthrough if your client sends them
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            if key in data:
                payload[key] = data[key]

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": data.get("http_referer", "https://autoresponder.local"),
            "X-Title": data.get("title", "WhatsApp Bot"),
            "Content-Type": "application/json",
        }

        response = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        # Try to parse JSON even on errors
        try:
            res_data = response.json()
        except Exception:
            return jsonify({
                "replies": [{"message": f"OpenRouter Error: non-JSON response ({response.status_code})"}]
            }), 502

        if response.status_code != 200:
            return jsonify({
                "replies": [{"message": f"OpenRouter Error: {res_data}"}]
            }), 502

        ai_reply = (
            res_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if not ai_reply.strip():
            ai_reply = f"I saw this: {user_text}"

        return jsonify({"replies": [{"message": ai_reply}]})

    except Exception as e:
        err_msg = traceback.format_exc()
        return jsonify({
            "replies": [{"message": f"Crash: {str(e)}\n{err_msg}"}]
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)