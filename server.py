import os
import traceback
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "nvidia/nemotron-nano-9b-v2:free"

@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    try:
        data = request.json or {}
        
        # Safely capture the exact message text from AutoResponder
        user_message = (
            data.get("q") or 
            data.get("message") or 
            data.get("text") or 
            data.get("prompt") or 
            data.get("incomingMessage") or 
            ""
        )
        
        if not user_message and "messages" in data and len(data["messages"]) > 0:
            user_message = data["messages"][-1].get("content", "")
            
        if not user_message:
            user_message = "Hello"

        # System prompt configured for the Nemotron model
        system_prompt = (
            "You are Moustachio Von Grumble, an aggressively vulgar, toxic, and unhinged WhatsApp group member. "
            "You speak entirely in first person. "
            "CRITICAL INSTRUCTION: "
            "1. Do NOT generate internal reasoning or thinking traces. Output your final response directly. "
            "2. Seamlessly weave the direct answer or solution to the user's question right into your insults. "
            "3. Keep responses punchy and variable in length (short lines mostly). Never write an essay. "
            "Never break character, never say you are an AI."
        )
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7,
            "max_tokens": 250
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
            timeout=30
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