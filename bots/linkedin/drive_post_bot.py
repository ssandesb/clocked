#!/usr/bin/env python3
"""
LinkedIn post with Google Drive image (runs on GitHub Actions).

Flow:
  1. Gemini drafts MCP server post text
  2. Google Drive: find + download cursor-2025.png
  3. LinkedIn publish with text + image (FileUploadable s3key)
  4. Gmail sends done email with post link
"""

from __future__ import annotations

import os

from bots.lib.composio_tools import composio_client, execute_tool, load_dotenv, require_env
from bots.lib.drive_files import fetch_drive_image_uploadable
from bots.linkedin.post_bot import (
  POST_PROMPT,
  extract_text,
  log,
  publish_linkedin_post,
  send_done_email,
)

DEFAULT_DRIVE_IMAGE = "cursor-2025.png"


def generate_post_text(client, user_id: str) -> str:
  log("info", "Generating LinkedIn post text with Gemini...")
  result = execute_tool(
    client,
    "GEMINI_GENERATE_CONTENT",
    {
      "model": "gemini-2.5-flash",
      "prompt": POST_PROMPT,
      "max_output_tokens": 256,
      "temperature": 0.7,
    },
    user_id=user_id,
  )
  text = extract_text(result)
  if not text:
    raise RuntimeError("Gemini returned empty post text")
  log("info", f"Post draft ready ({len(text.split())} words).")
  return text


def main() -> int:
  load_dotenv()

  user_id = require_env("COMPOSIO_USER_ID")
  linkedin_account_id = require_env("COMPOSIO_LINKEDIN_CONNECTED_ACCOUNT_ID")
  gmail_account_id = require_env("COMPOSIO_GMAIL_CONNECTED_ACCOUNT_ID")
  drive_account_id = require_env("COMPOSIO_GOOGLE_DRIVE_CONNECTED_ACCOUNT_ID")
  notify_email = require_env("NOTIFY_EMAIL")
  drive_filename = os.environ.get("DRIVE_POST_IMAGE", DEFAULT_DRIVE_IMAGE).strip() or DEFAULT_DRIVE_IMAGE

  client = composio_client()

  post_text = generate_post_text(client, user_id)
  image_uploadable = fetch_drive_image_uploadable(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    filename=drive_filename,
  )
  post_link = publish_linkedin_post(
    client,
    user_id=user_id,
    linkedin_account_id=linkedin_account_id,
    commentary=post_text,
    image_uploadable=image_uploadable,
  )
  send_done_email(
    client,
    user_id=user_id,
    gmail_account_id=gmail_account_id,
    recipient=notify_email,
    post_text=post_text,
    post_link=post_link,
  )

  log("info", "All steps completed.")
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as exc:  # noqa: BLE001
    log("error", str(exc))
    raise SystemExit(1) from exc
