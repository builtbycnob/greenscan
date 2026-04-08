"""Telegram delivery via raw httpx (no bot framework needed for send-only)."""

import logging

import httpx
import telegramify_markdown

from pipeline.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_MESSAGE_LENGTH = 4000  # safe limit under 4096


async def send_brief(brief_markdown: str) -> bool:
    """Send the daily brief to all configured Telegram recipients.

    Splits long messages at paragraph boundaries.
    Returns True if all parts sent to all recipients successfully.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        logger.warning("Telegram not configured, printing to stdout")
        print("\n" + brief_markdown)
        return False

    chunks = _split_message(brief_markdown)
    success = True

    async with httpx.AsyncClient(timeout=30.0) as client:
        for chat_id in settings.telegram_chat_ids:
            for chunk in chunks:
                ok = await _send_message(client, chunk, chat_id)
                if not ok:
                    success = False

    return success


async def send_alert(message: str) -> bool:
    """Send a short alert message (score-5 signal) to all recipients."""
    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        logger.warning("Telegram not configured, printing alert to stdout")
        print(f"\n🚨 ALERT: {message}")
        return False

    success = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chat_id in settings.telegram_chat_ids:
            ok = await _send_message(client, f"🚨 *CRITICAL SIGNAL*\n\n{message}", chat_id)
            if not ok:
                success = False
    return success


async def send_failure_alert(error: str, step: str) -> bool:
    """Send pipeline failure notification to all recipients."""
    msg = f"⚠️ *Pipeline Failure*\n\nStep: {step}\nError: {error}"
    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        logger.error(f"Pipeline failure (Telegram not configured): {step}: {error}")
        return False

    success = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chat_id in settings.telegram_chat_ids:
            ok = await _send_message(client, msg, chat_id)
            if not ok:
                success = False
    return success


async def _send_message(client: httpx.AsyncClient, text: str, chat_id: str) -> bool:
    """Send a single message to a specific chat via Telegram Bot API."""
    try:
        converted = telegramify_markdown.markdownify(text)
    except Exception:
        converted = text

    url = f"{TELEGRAM_API.format(token=settings.telegram_bot_token)}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": converted,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }

    try:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram error: {data}")
            # Retry without parse_mode if markdown fails
            payload["parse_mode"] = None
            payload["text"] = text
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram plaintext fallback also failed: {data}")
                return False
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def _split_message(text: str) -> list[str]:
    """Split long messages at paragraph boundaries."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > MAX_MESSAGE_LENGTH:
            if current:
                chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph

    if current.strip():
        chunks.append(current.strip())

    return chunks
