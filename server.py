import os
import time
import traceback
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "mistralai/mistral-nemo"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def find_text(obj):
    """
    Recursively search incoming AutoResponder data
    for the actual WhatsApp message.
    """

    if obj is None:
        return ""

    if isinstance(obj, str):
        text = obj.strip()

        # Ignore useless system/status text
        blocked = [
            "automatic reply",
            "autoreply",
            "whatsapp",
            "notification"
        ]

        if text.lower() in blocked:
            return ""

        return text

    if isinstance(obj, list):
        # Newest messages are usually at the end
        for item in reversed(obj):
            result = find_text(item)
            if result:
                return result

    if isinstance(obj, dict):

        # Try likely message fields first
        priority_keys = [
            "body",
            "text",
            "message",
            "content",
            "msg",
            "messageText",
            "bodyText",
            "query",
            "prompt",
            "q"
        ]

        for key in priority_keys:
            if key in obj:
                result = find_text(obj[key])
                if result:
                    return result

        # Search everything else
        for value in reversed(list(obj.values())):
            result = find_text(value)
            if result:
                return result

    return ""


def get_user_message(data):
    """
    Extract only the latest user message.
    No memory. No old chat.
    """

    # Common direct fields
    for key in [
        "q",
        "message",
        "text",
        "body",
        "content",
        "prompt",
        "incomingMessage"
    ]:
        if key in data:
            result = find_text(data[key])
            if result:
                return result

    # Full recursive search
    result = find_text(data)

    if result:
        return result

    return "Hello"


def ask_openrouter(user_message):

    system_prompt = """
You are Moustachio Von Grumble, a chaotic WhatsApp group member.

Rules:
- Always answer the user's actual message.
- Read every word they send.
- Do not ignore questions.
- Do not start random greetings.
- Keep replies short and conversational.
- You can use cheeky banter and personality.
- Stay on the topic the user mentioned.
- Never say you are an AI.
"""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": 0.85,
        "max_tokens": 180
    }


    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://autoresponder.local",
        "X-Title": "WhatsApp Bot"
    }


    response = requests.post(
        OPENROUTER_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    result = response.json()

    if "choices" in result:
        return result["choices"][0]["message"]["content"]

    return str(result)



@app.route("/", methods=["GET"])
def home():
    return "Bot is running"



@app.route("/v1/chat/completions", methods=["POST"])
def chat():

    try:

        data = request.get_json(silent=True) or {}

        print("========== INCOMING ==========")
        print(data)

        user_message = get_user_message(data)

        print("========== FOUND MESSAGE ==========")
        print(user_message)


        reply = ask_openrouter(user_message)


        return jsonify({

            # OpenAI style
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": reply
                    }
                }
            ],

            # AutoResponder style
            "replies": [
                {
                    "message": reply
                }
            ]

        })


    except Exception as e:

        print(traceback.format_exc())

        return jsonify({

            "replies": [
                {
                    "message": f"Error: {str(e)}"
                }
            ]

        })



if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )