import os
import traceback
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
# Hardcoded to a currently active free model on OpenRouter
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"

@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        data = request.json or {}
        
        user_message = data.get("message") or data.get("prompt", "")
        if not user_message and "messages" in data and len(data["messages"]) > 0:
            user_message = data["messages"][-1].get("content", "")
        if not user_message:
            user_message = "Hello"

        system_prompt = "You are Moustachio, an unfiltered and direct character..."
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7
        }
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://autoresponder.local",
            "X-Title": "WhatsApp Bot",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=25
        )
        
        res_data = response.json()
        
        if "choices" in res_data:
            ai_reply = res_data["choices"][0]["message"]["content"]
            return jsonify({"replies": [{"message": ai_reply}]})
        else:
            return jsonify({"replies": [{"message": f"OpenRouter Error: {str(res_data)}"}]})
            
    except Exception as e:
        err_msg = traceback.format_exc()
        return jsonify({"replies": [{"message": f"Crash: {str(e)}"}]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)