import os
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    data = request.json
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": data.get("messages", []),
        "temperature": data.get("temperature", 0.7)
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
        headers=headers
    )
    
    return jsonify(response.json()), response.status_code

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)