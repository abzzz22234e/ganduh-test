import os
import traceback
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free")

@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        data = request.json or {}
        
        user_message = data.get("message") or data.get("prompt", "")
        if not user_message and "messages" in data:
            user_message = data["messages"][-1].get("content", "")

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
        
        # If OpenRouter returns an error, catch it here
        if "choices" not in res_data:
            print(f"OpenRouter Error: {res_data}")
            return jsonify({"replies": [{"message": f"OpenRouter API Error: {res_data}"}]}), 500
            
        ai_reply = res_data["choices"][0]["message"]["content"]
        
        return jsonify({"replies": [{"message": ai_reply}]})
        
    except Exception as e:
        traceback.print_exc() # This will print the exact line of the crash in Render logs
        return jsonify({"replies": [{"message": f"Server Error: {str(e)}"}]}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)