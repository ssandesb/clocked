#!/usr/bin/env python3
"""
Prompt-driven LinkedIn post (runs on GitHub Actions).

Flow:
  1. Read prompt from Google Drive (Google Doc or .docx)
  2. Gemini converts doc text → JSON execution plan
  3. Gemini writes caption; image from Gemini, Drive, or none
  4. LinkedIn publish + Gmail notification
"""

from __future__ import annotations

import os
from typing import Any

from bots.lib.composio_tools import composio_client, execute_tool, load_dotenv, require_env
from bots.lib.drive_files import fetch_drive_image_uploadable, fetch_drive_prompt_text
from bots.linkedin.post_bot import (
  extract_file_uploadable,
  extract_text,
  log,
  publish_linkedin_post,
  send_done_email,
)
from bots.linkedin.prompt_plan import PromptPlan, build_plan_from_doc

DEFAULT_PROMPT_DOC = "prompt"


def fetch_prompt_text(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  filename: str,
) -> str:
  log("info", f"Downloading {filename} from Google Drive...")
  text = fetch_drive_prompt_text(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    filename=filename,
  )
  log("info", f"Read prompt ({len(text)} chars).")
  return text


def generate_caption(client: Any, user_id: str, instruction: str) -> str:
  log("info", "Generating LinkedIn caption with Gemini...")
  result = execute_tool(
    client,
    "GEMINI_GENERATE_CONTENT",
    {
      "model": "gemini-2.5-flash",
      "prompt": (
        f"{instruction}\n\n"
        "Output plain text only. No markdown. No hashtags. Suitable for LinkedIn."
      ),
      "max_output_tokens": 512,
      "temperature": 0.7,
    },
    user_id=user_id,
  )
  text = extract_text(result)
  if not text:
    raise RuntimeError("Gemini returned empty caption")
  log("info", f"Caption ready ({len(text.split())} words).")
  return text


def generate_gemini_image(client: Any, user_id: str, image_prompt: str) -> dict:
  log("info", "Generating image with Gemini...")
  result = execute_tool(
    client,
    "GEMINI_GENERATE_IMAGE",
    {
      "model": "gemini-2.5-flash-image",
      "prompt": image_prompt,
      "aspect_ratio": "1:1",
      "image_size": "1K",
    },
    user_id=user_id,
  )
  return extract_file_uploadable(result, default_name="gemini-image.png")


def resolve_image_uploadable(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  plan: PromptPlan,
) -> dict | None:
  if plan.image_source == "none":
    log("info", "Plan: text-only post (no image).")
    return None

  if plan.image_source == "drive":
    filename = plan.drive_filename or ""
    if not filename:
      raise RuntimeError("Plan requires drive_filename for drive image source")
    return fetch_drive_image_uploadable(
      client,
      user_id=user_id,
      drive_account_id=drive_account_id,
      filename=filename,
    )

  prompt = plan.gemini_image_prompt or "Hand-drawn doodle on white background."
  return generate_gemini_image(client, user_id, prompt)


def main() -> int:
  load_dotenv()

  user_id = require_env("COMPOSIO_USER_ID")
  linkedin_account_id = require_env("COMPOSIO_LINKEDIN_CONNECTED_ACCOUNT_ID")
  gmail_account_id = require_env("COMPOSIO_GMAIL_CONNECTED_ACCOUNT_ID")
  drive_account_id = require_env("COMPOSIO_GOOGLE_DRIVE_CONNECTED_ACCOUNT_ID")
  notify_email = require_env("NOTIFY_EMAIL")
  prompt_doc = os.environ.get("PROMPT_DOC_NAME", DEFAULT_PROMPT_DOC).strip() or DEFAULT_PROMPT_DOC

  client = composio_client()

  doc_text = fetch_prompt_text(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    filename=prompt_doc,
  )
  plan = build_plan_from_doc(client, user_id, doc_text)
  caption = generate_caption(client, user_id, plan.caption_instruction)
  image_uploadable = resolve_image_uploadable(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    plan=plan,
  )
  post_link = publish_linkedin_post(
    client,
    user_id=user_id,
    linkedin_account_id=linkedin_account_id,
    commentary=caption,
    image_uploadable=image_uploadable,
    lifecycle_state="DRAFT" if plan.publish_mode == "draft" else "PUBLISHED",
  )
  send_done_email(
    client,
    user_id=user_id,
    gmail_account_id=gmail_account_id,
    recipient=notify_email,
    post_text=caption,
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
