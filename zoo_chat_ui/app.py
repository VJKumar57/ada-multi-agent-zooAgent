import os
import hashlib
import json
import re
import time
import uuid
from collections import defaultdict, deque
from functools import wraps
from threading import Lock

import firebase_admin
import requests
from firebase_admin import auth, credentials
from flask import Flask, g, jsonify, render_template, request
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token


app = Flask(__name__)
agent_url = os.environ["AGENT_URL"].rstrip("/")
app_name = "multi_tool_agent"
firebase_enabled = os.getenv("FIREBASE_AUTH_ENABLED", "FALSE").upper() == "TRUE"
firebase_web_config = {
    "apiKey": os.getenv("FIREBASE_API_KEY", ""),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
    "appId": os.getenv("FIREBASE_APP_ID", ""),
}
admin_emails = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024
agent_request_timeout = 60
rate_limit_window_seconds = 60
rate_limit_max_requests = 20
request_timestamps: dict[str, deque[float]] = defaultdict(deque)
rate_limit_lock = Lock()
answer_cache_ttl_seconds = 30 * 60
cache_redis_url = os.getenv("CACHE_REDIS_URL", "")
cache_key_prefix = os.getenv("CACHE_KEY_PREFIX", "zoo-tour-guide:v1")
cache_client = None
cache_client_initialized = False
time_sensitive_message_pattern = re.compile(
    r"\b(now|today|tomorrow|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|weather|forecast|route|traffic|open|hours)\b",
    re.IGNORECASE,
)
role_sensitive_message_pattern = re.compile(
    r"\b(ticket|pass|admission|price|pricing|cafe|meal|food|credit|discount)\b",
    re.IGNORECASE,
)

if firebase_enabled and not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.ApplicationDefault())


def authenticated_user(handler):
    """Require and verify a Firebase ID token before serving a UI API request."""
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not firebase_enabled:
            return jsonify({"error": "Authentication is not configured."}), 503
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return jsonify({"error": "Sign in is required."}), 401
        try:
            decoded_token = auth.verify_id_token(authorization.removeprefix("Bearer "))
        except Exception:
            return jsonify({"error": "Your sign-in session is invalid or expired."}), 401
        email = decoded_token.get("email", "").lower()
        g.user = {
            "uid": decoded_token["uid"],
            "email": email,
            "role": "admin" if email in admin_emails else decoded_token.get("role", "guest"),
        }
        return handler(*args, **kwargs)

    return wrapped


def required_role(*roles):
    """Restrict an authenticated API route to the specified personas."""
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return jsonify({"error": "You do not have permission for this action."}), 403
            return handler(*args, **kwargs)

        return wrapped

    return decorator


def agent_headers() -> dict[str, str]:
    """Build authenticated headers for the private ADK Cloud Run service."""
    token = fetch_id_token(Request(), agent_url)
    return {"Authorization": f"Bearer {token}"}


def normalized_message(message: str) -> str:
    """Normalize an exact chat message before deriving a cache key."""
    return " ".join(message.casefold().split())


def answer_cache_key(user_id: str, session_id: str, message: str) -> str:
    """Build an opaque key scoped to one authenticated user and ADK session."""
    digest = hashlib.sha256(normalized_message(message).encode()).hexdigest()
    return f"{cache_key_prefix}:answer:{user_id}:{session_id}:{digest}"


def is_cacheable_message(message: str) -> bool:
    """Exclude dynamic and role-dependent requests from answer caching."""
    return not (
        time_sensitive_message_pattern.search(message)
        or role_sensitive_message_pattern.search(message)
    )


def get_cache_client():
    """Create an optional Redis client lazily so cache failures never block chat."""
    global cache_client, cache_client_initialized
    if cache_client_initialized:
        return cache_client
    cache_client_initialized = True
    if not cache_redis_url:
        return None
    try:
        import redis

        cache_client = redis.Redis.from_url(cache_redis_url, decode_responses=True)
        cache_client.ping()
    except Exception:
        cache_client = None
    return cache_client


def cached_answer(cache_key: str) -> dict | None:
    """Read a valid cached answer, treating cache failures as a miss."""
    try:
        value = get_cache_client().get(cache_key) if get_cache_client() else None
        payload = json.loads(value) if value else None
        if isinstance(payload, dict) and isinstance(payload.get("answer"), str):
            return payload
    except (Exception, json.JSONDecodeError):
        pass
    return None


def store_cached_answer(
    cache_key: str, answer: str, execution: list[dict[str, str]]
) -> None:
    """Store only the final answer and sanitized execution metadata."""
    try:
        client = get_cache_client()
        if client:
            client.setex(
                cache_key,
                answer_cache_ttl_seconds,
                json.dumps({"answer": answer, "execution": execution}),
            )
    except Exception:
        pass


def is_rate_limited() -> bool:
    """Limit each client IP to a bounded number of UI API calls per minute."""
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
    now = time.monotonic()
    with rate_limit_lock:
        timestamps = request_timestamps[client_ip]
        while timestamps and now - timestamps[0] >= rate_limit_window_seconds:
            timestamps.popleft()
        if len(timestamps) >= rate_limit_max_requests:
            return True
        timestamps.append(now)
    return False


@app.get("/")
def index():
    """Render the Zoo Tour Guide chat page."""
    return render_template(
        "index.html",
        firebase_enabled=firebase_enabled,
        firebase_config=firebase_web_config,
    )


@app.post("/api/session")
@authenticated_user
def create_session():
    """Create an isolated ADK session for the browser chat."""
    if is_rate_limited():
        return jsonify({"error": "Too many requests. Please try again shortly."}), 429

    user_id = f"firebase-{g.user['uid']}"
    session_id = str(uuid.uuid4())
    response = requests.post(
        f"{agent_url}/apps/{app_name}/users/{user_id}/sessions/{session_id}",
        json={"state": {"USER_ROLE": g.user["role"]}},
        headers=agent_headers(),
        timeout=agent_request_timeout,
    )
    response.raise_for_status()
    return jsonify({"userId": user_id, "sessionId": session_id})


def execution_trace(events: list[dict]) -> list[dict[str, str]]:
    """Extract agent transfers and tool calls without exposing tool arguments or results."""
    steps = []
    for event in events:
        transferred_agent = event.get("actions", {}).get("transferToAgent")
        if transferred_agent:
            steps.append({"type": "agent", "name": transferred_agent})
        for part in event.get("content", {}).get("parts", []):
            function_call = part.get("functionCall")
            if function_call and function_call.get("name") != "transfer_to_agent":
                steps.append({"type": "tool", "name": function_call["name"]})
    return steps


@app.post("/api/chat")
@authenticated_user
def chat():
    """Send a message to ADK and return the final text response."""
    if is_rate_limited():
        return jsonify({"error": "Too many requests. Please try again shortly."}), 429

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("sessionId")
    message = payload.get("message", "").strip()
    if not session_id or not message:
        return jsonify({"error": "A session and message are required."}), 400
    if len(message) > 1_000:
        return jsonify({"error": "Messages must be 1,000 characters or fewer."}), 400

    user_id = f"firebase-{g.user['uid']}"
    cache_key = answer_cache_key(user_id, session_id, message)
    if is_cacheable_message(message):
        cached = cached_answer(cache_key)
        if cached:
            return jsonify({**cached, "cached": True})

    try:
        response = requests.post(
            f"{agent_url}/run",
            json={
                "appName": app_name,
                "userId": user_id,
                "sessionId": session_id,
                "newMessage": {"role": "user", "parts": [{"text": message}]},
            },
            headers=agent_headers(),
            timeout=agent_request_timeout,
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
    execution = execution_trace(events)
    if is_cacheable_message(message):
        store_cached_answer(cache_key, final_text, execution)
    return jsonify({"answer": final_text, "execution": execution, "cached": False})


@app.post("/api/admin/users/<user_id>/role")
@authenticated_user
@required_role("admin")
def set_user_role(user_id):
    """Assign a Firebase custom-claim role for an existing Zoo Tour Guide user."""
    role = (request.get_json(silent=True) or {}).get("role", "").lower()
    if role not in {"admin", "employee", "member", "guest"}:
        return jsonify({"error": "Role must be admin, employee, member, or guest."}), 400
    auth.set_custom_user_claims(user_id, {"role": role})
    return jsonify({"status": "success", "role": role})