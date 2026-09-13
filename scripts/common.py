import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter, Retry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("piano-tips-bot")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
HISTORY_FILE = os.path.join(DATA_DIR, "posted_history.json")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"  # current free/production Groq model (llama-3.3-70b-versatile is decommissioned)

_session = requests.Session()
_retries = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retries))


def _require_env():
    missing = [name for name, val in [
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN),
        ("TELEGRAM_ADMIN_CHAT_ID", ADMIN_CHAT_ID),
        ("TELEGRAM_CHANNEL_ID", CHANNEL_ID),
        ("GROQ_API_KEY", GROQ_API_KEY),
    ] if not val]
    if missing:
        raise RuntimeError(
            "Missing required secrets: " + ", ".join(missing) +
            ". Add them under GitHub repo Settings > Secrets and variables > Actions."
        )


def _tg(method, **params):
    _require_env()
    url = TELEGRAM_API.format(token=TELEGRAM_TOKEN, method=method)
    r = _session.post(url, json=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok", False):
        raise RuntimeError(f"Telegram API error on {method}: {data}")
    return data


def send_message(chat_id, text, parse_mode="HTML"):
    return _tg("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)


def get_updates(offset=None):
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    return _tg("getUpdates", **params)


def groq_chat(system_prompt, user_prompt, temperature=0.9):
    _require_env()
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    r = _session.post(GROQ_API, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "choices" not in data or not data["choices"]:
        raise RuntimeError(f"Groq API returned no choices: {data}")
    return data["choices"][0]["message"]["content"]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
