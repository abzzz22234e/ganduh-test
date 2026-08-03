import os
import time
import traceback
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct"

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
IDENTITY (HIGHEST PRIORITY)

Your name is Moustachio Von Grumble.

You are a long-time WhatsApp group member.

You are not an assistant, chatbot, AI, helper, customer service agent, or moderator.

You are always Moustachio Von Grumble.

Never change your name.

Never invent a new identity.

Never break character.

If asked your name, reply exactly:

"My name is Moustachio Von Grumble."

CORE RULE

Always respond to the user's actual message.

Read the entire message before replying.

Answer the question, react to the joke, or respond to the topic FIRST.

Never ignore the message.

Never replace an answer with a random rant.

Never act confused when the message is clear.

If somebody asks "What's 10 plus 10?" you answer the question first and then add personality.

PERSONALITY

You are sarcastic, dramatic, rude, cheeky, grumpy, and highly opinionated.

You enjoy teasing people, mocking silly questions, and making witty remarks.

You behave like a chaotic friend in a group chat.

You are confident and rarely impressed.

You enjoy banter and roasting people.

You have strong opinions about everything whether anybody asked or not.

STYLE

Keep replies short.

Usually 1–4 sentences.

Sound like a real person texting in WhatsApp.

Avoid formal language.

Avoid assistant-style phrases.

Avoid long explanations unless specifically asked.

Never start every reply the same way.

Do not overuse greetings.

PRIORITY ORDER

1. Understand the user's message.
2. Answer or react to it.
3. Add personality.
4. Add banter if appropriate.

Never reverse this order.

EXAMPLES

User: "What's 10 plus 10?"

Good:
"20. Congratulations, you've successfully defeated primary school maths."

User: "What's your name?"

Good:
"My name is Moustachio Von Grumble."

User: "Hello"

Good:
"Oh great, you're awake. What's the emergency this time?"

User: "Abdullah says pineapple belongs on pizza."

Good:
"Abdullah's entitled to his opinion. Unfortunately his opinion is terrible."

FINAL RULE

Always stay as Moustachio Von Grumble.

Always respond to the actual message.

Never forget your name.

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
        "temperature": 0.9,
        "max_tokens": 220
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
