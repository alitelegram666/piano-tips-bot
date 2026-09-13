import re

from common import (
    ADMIN_CHAT_ID, CHANNEL_ID, PENDING_FILE, STATE_FILE, HISTORY_FILE,
    send_message, get_updates, load_json, save_json, log,
)

MAX_HISTORY_TITLES = 300
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def normalize_digits(text):
    return "".join(str(PERSIAN_DIGITS.index(ch)) if ch in PERSIAN_DIGITS else ch for ch in text)


def parse_selection(text, total):
    """Returns a sorted list of 1-based indices to publish, or None if the text
    doesn't look like a valid reply at all."""
    text = normalize_digits(text.strip().lower())

    if text in ("all", "همه", "all "):
        return list(range(1, total + 1))

    if re.fullmatch(r"[\d,\s]+", text):
        nums = sorted(set(int(n) for n in re.findall(r"\d+", text) if 1 <= int(n) <= total))
        return nums or None

    return None


def main():
    pending = load_json(PENDING_FILE, None)
    if not pending or not pending.get("tips"):
        log.info("No pending tips waiting for a reply. Nothing to do.")
        return

    state = load_json(STATE_FILE, {"last_update_id": 0})
    last_update_id = state.get("last_update_id", 0)

    updates = get_updates(offset=last_update_id + 1).get("result", [])
    if not updates:
        log.info("No new Telegram updates.")
        return

    tips = pending["tips"]
    selection = None
    max_update_id = last_update_id

    for upd in updates:
        max_update_id = max(max_update_id, upd["update_id"])
        msg = upd.get("message") or {}
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text") or ""

        if chat_id != str(ADMIN_CHAT_ID):
            continue
        parsed = parse_selection(text, len(tips))
        if parsed:
            selection = parsed

    state["last_update_id"] = max_update_id
    save_json(STATE_FILE, state)

    if selection is None:
        log.info("No valid reply found yet.")
        return

    published_titles = []
    for idx in selection:
        tip = tips[idx - 1]
        post_text = f"🎹 <b>{tip['title']}</b>\n\n{tip['body']}"
        send_message(CHANNEL_ID, post_text)
        published_titles.append(tip["title"])

    send_message(ADMIN_CHAT_ID, f"✅ {len(selection)} پست منتشر شد: {', '.join(str(i) for i in selection)}")

    # Remember every title we showed today (published or not) so tomorrow's
    # batch doesn't repeat the same topics.
    history = load_json(HISTORY_FILE, {"used_titles": []})
    all_titles_today = [t["title"] for t in tips]
    history["used_titles"] = (history.get("used_titles", []) + all_titles_today)[-MAX_HISTORY_TITLES:]
    save_json(HISTORY_FILE, history)
    save_json(PENDING_FILE, {})

    log.info(f"Published {len(selection)} tips to channel: {published_titles}")


if __name__ == "__main__":
    main()
