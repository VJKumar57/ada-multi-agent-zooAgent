import os
import uuid

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)
agent_url = os.environ["AGENT_URL"].rstrip("/")
app_name = "multi_tool_agent"


@app.get("/")
def index():
    """Render the Zoo Tour Guide chat page."""
    return render_template("index.html")


@app.post("/api/session")
def create_session():
    """Create an isolated ADK session for the browser chat."""
    user_id = f"web-{uuid.uuid4()}"
    session_id = str(uuid.uuid4())
    response = requests.post(
        f"{agent_url}/apps/{app_name}/users/{user_id}/sessions/{session_id}",
        json={},
        timeout=30,
    )
    response.raise_for_status()
    return jsonify({"userId": user_id, "sessionId": session_id})


@app.post("/api/chat")
def chat():
    """Send a message to ADK and return the final text response."""
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId")
    session_id = payload.get("sessionId")
    message = payload.get("message", "").strip()
    if not user_id or not session_id or not message:
        return jsonify({"error": "A session and message are required."}), 400

    try:
        response = requests.post(
            f"{agent_url}/run",
            json={
                "appName": app_name,
                "userId": user_id,
                "sessionId": session_id,
                "newMessage": {"role": "user", "parts": [{"text": message}]},
            },
            timeout=90,
        )
        response.raise_for_status()
        events = response.json()
    except requests.RequestException as error:
        return jsonify({"error": f"The agent request failed: {error}"}), 502
    final_text = next(
        (
            part["text"]
            for event in reversed(events)
            for part in event.get("content", {}).get("parts", [])
            if "text" in part
        ),
        "I could not produce a response.",
    )
    return jsonify({"answer": final_text})