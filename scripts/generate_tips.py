import json
import re
from datetime import datetime, timezone

from common import (
    ADMIN_CHAT_ID, PENDING_FILE, HISTORY_FILE,
    send_message, groq_chat, load_json, save_json, log,
)

NUM_TIPS = 10
MAX_HISTORY_TITLES = 300  # how many past titles we remember to avoid repeats

SYSTEM_PROMPT = """
You are the content editor for a Persian-language Telegram channel about piano: practical
tricks, technique tips, and music theory notes for piano players of all levels (beginner to
advanced), including occasional notes useful specifically to one-handed / left-hand-only piano
technique when relevant.

Your job: generate exactly {n} DISTINCT, non-repetitive items. Mix across these categories so the
feed feels varied, not a single theme every day:
  - practical playing tricks / technique tips (hand position, fingering, pedaling, sight-reading, practice methods)
  - music theory notes (scales, chords, intervals, harmony, ear training) explained simply
  - short historical/interesting facts about pieces, composers, or piano-building relevant to players

You will be given a list of titles already used in previous days — NEVER repeat those topics or
near-duplicates of them.

For each of the {n} items, write:
  - "title": short, catchy, in Persian (max ~10 words)
  - "body": 2-4 sentences in Persian, clear, practical/informative, engaging for a general piano
    audience (not overly academic)

Respond with ONLY valid JSON, no markdown fences, no commentary, in this exact shape:
{{
  "tips": [
    {{"title": "...", "body": "..."}},
    ... exactly {n} objects total
  ]
}}
"""


def build_user_prompt(used_titles):
    if used_titles:
        history_block = "Titles already used before (do NOT repeat these or near-duplicates):\n" + \
            "\n".join(f"- {t}" for t in used_titles)
    else:
        history_block = "No titles used yet — this is the first batch."
    return history_block + f"\n\nNow generate {NUM_TIPS} fresh, distinct items."


def extract_json(text):
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    return json.loads(text)


def get_tips_with_retry(used_titles, attempts=2):
    system_prompt = SYSTEM_PROMPT.format(n=NUM_TIPS)
    user_prompt = build_user_prompt(used_titles)
    last_error = None

    for attempt in range(1, attempts + 1):
        prompt = user_prompt if attempt == 1 else (
            user_prompt + "\n\nReminder: respond with ONLY the raw JSON object, nothing else."
        )
        raw = groq_chat(system_prompt, prompt)
        try:
            result = extract_json(raw)
            tips = result.get("tips", [])
            if len(tips) >= NUM_TIPS:
                return tips[:NUM_TIPS]
            last_error = f"Model returned only {len(tips)} tips, expected {NUM_TIPS}."
        except Exception as e:
            last_error = f"{e}\nRaw output:\n{raw}"
        log.warning(f"Attempt {attempt}/{attempts} failed: {last_error}")

    raise RuntimeError(f"Could not get {NUM_TIPS} valid tips from Groq after {attempts} attempts: {last_error}")


def main():
    history = load_json(HISTORY_FILE, {"used_titles": []})
    used_titles = history.get("used_titles", [])

    try:
        tips = get_tips_with_retry(used_titles)
    except RuntimeError as e:
        log.error(str(e))
        return

    pending = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tips": tips,
    }
    save_json(PENDING_FILE, pending)

    lines = [
        "🎹 <b>۱۰ نکته/ترفند پیانوی امروز</b>\n",
        "برای تأیید همه ریپلای کن: <b>همه</b>",
        "برای تأیید بعضیاش، شماره‌ها رو با ویرگول ریپلای کن، مثلاً: <b>1,3,5,7</b>\n",
    ]
    for idx, t in enumerate(tips, 1):
        lines.append(f"<b>{idx}. {t['title']}</b>\n{t['body']}\n")

    send_message(ADMIN_CHAT_ID, "\n".join(lines))
    log.info(f"Sent {len(tips)} tips to admin for review.")


if __name__ == "__main__":
    main()
