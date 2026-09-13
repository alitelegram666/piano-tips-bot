"""
Offline end-to-end smoke test — no real network calls.
Run with: python3 tests/smoke_test.py
"""

import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

os.environ["TELEGRAM_BOT_TOKEN"] = "TEST_TOKEN"
os.environ["TELEGRAM_ADMIN_CHAT_ID"] = "111111"
os.environ["TELEGRAM_CHANNEL_ID"] = "@test_piano_channel"
os.environ["GROQ_API_KEY"] = "TEST_GROQ_KEY"

import common  # noqa: E402
import generate_tips  # noqa: E402
import check_and_publish  # noqa: E402

sent_messages = []


def json_dumps(obj):
    import json as _json
    return _json.dumps(obj, ensure_ascii=False)


def fake_session_post(url, json=None, headers=None, timeout=None):
    resp = MagicMock()
    resp.raise_for_status = lambda: None

    if "api.groq.com" in url:
        fake_tips = {"tips": [
            {"title": f"نکته شماره {i}", "body": f"توضیح نکته {i}."} for i in range(1, 11)
        ]}
        resp.json = lambda: {"choices": [{"message": {"content": json_dumps(fake_tips)}}]}
        return resp

    if "api.telegram.org" in url:
        method = url.rsplit("/", 1)[-1]
        if method == "getUpdates":
            resp.json = lambda: {
                "ok": True,
                "result": [{
                    "update_id": 2001,
                    "message": {"chat": {"id": 111111}, "text": "1,3,5"},
                }],
            }
            return resp
        if method == "sendMessage":
            sent_messages.append(json)
            resp.json = lambda: {"ok": True, "result": {}}
            return resp

    raise AssertionError(f"Unexpected POST to {url}")


common._session.post = fake_session_post

common.save_json(common.PENDING_FILE, {})
common.save_json(common.STATE_FILE, {"last_update_id": 0})
common.save_json(common.HISTORY_FILE, {"used_titles": []})

# ---- Step 1: daily generation ----
generate_tips.main()

pending = common.load_json(common.PENDING_FILE, None)
assert pending and len(pending["tips"]) == 10, "Expected 10 tips to be saved to pending.json"
assert len(sent_messages) == 1, "Expected exactly one review message to the admin"
assert "نکته شماره 1" in sent_messages[0]["text"], "Review message should list tip #1"
print("[OK] Daily generation step: 10 tips created and sent for review.")

# ---- Step 2: reply "1,3,5" -> publish those 3 as separate channel posts ----
sent_messages.clear()
check_and_publish.main()

history = common.load_json(common.HISTORY_FILE, {"used_titles": []})
pending_after = common.load_json(common.PENDING_FILE, None)

channel_posts = [m for m in sent_messages if m["chat_id"] == "@test_piano_channel"]
admin_confirms = [m for m in sent_messages if m["chat_id"] == "111111"]

assert len(channel_posts) == 3, f"Expected 3 separate channel posts, got {len(channel_posts)}"
assert "نکته شماره 1" in channel_posts[0]["text"]
assert "نکته شماره 3" in channel_posts[1]["text"]
assert "نکته شماره 5" in channel_posts[2]["text"]
assert len(admin_confirms) == 1, "Expected one confirmation message to admin"
assert len(history["used_titles"]) == 10, "All 10 shown titles should be recorded in history"
assert pending_after == {}, "Pending should be cleared after publishing"
print("[OK] Reply step: tips 1, 3, 5 correctly published as separate posts; history updated.")

print("\nALL TESTS PASSED")
