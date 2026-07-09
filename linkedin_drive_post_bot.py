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

import json
import os
import sys
from typing import Any

from composio_tools import composio_client, dig, execute_tool, load_dotenv, require_env, unwrap_data
from linkedin_post_bot import (
  POST_PROMPT,
  extract_file_uploadable,
  extract_post_link,
  extract_text,
  linkedin_author_urn,
  log,
  publish_linkedin_post,
  send_done_email,
)

DEFAULT_DRIVE_IMAGE = "cursor-2025.png"


def find_drive_file_id(result: dict, *, filename: str) -> str:
  data = unwrap_data(result)
  if isinstance(data, str):
    try:
      data = json.loads(data)
    except json.JSONDecodeError:
      pass

  files: list[dict] = []
  if isinstance(data, dict):
    raw = data.get("files")
    if isinstance(raw, list):
      files = [f for f in raw if isinstance(f, dict)]
    elif isinstance(dig(data, "data", "files"), list):
      files = [f for f in dig(data, "data", "files") if isinstance(f, dict)]

  if not files:
    raise RuntimeError(
      f"Google Drive file '{filename}' not found. "
      f"Response: {json.dumps(result)[:500]}"
    )

  for item in files:
    name = str(item.get("name", "")).strip()
    file_id = str(item.get("id", "")).strip()
    if name == filename and file_id:
      return file_id

  first = files[0]
  file_id = str(first.get("id", "")).strip()
  if not file_id:
    raise RuntimeError(f"No file id in Drive search result: {json.dumps(first)[:300]}")
  log("info", f"Exact name match missing; using first result: {first.get('name')!r}")
  return file_id


def fetch_drive_image_uploadable(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  filename: str,
) -> dict:
  log("info", f"Searching Google Drive for '{filename}'...")
  find_result = execute_tool(
    client,
    "GOOGLEDRIVE_FIND_FILE",
    {
      "q": f"name = '{filename}' and trashed = false",
      "pageSize": 5,
    },
    user_id=user_id,
    connected_account_id=drive_account_id,
  )
  file_id = find_drive_file_id(find_result, filename=filename)
  log("info", f"Found Drive file id: {file_id}")

  log("info", "Downloading image from Google Drive...")
  download_result = execute_tool(
    client,
    "GOOGLEDRIVE_DOWNLOAD_FILE",
    {"fileId": file_id},
    user_id=user_id,
    connected_account_id=drive_account_id,
  )
  try:
    return extract_file_uploadable(download_result, default_name=filename)
  except RuntimeError:
    log("info", "Retrying download via GOOGLEDRIVE_DOWNLOAD_FILE_OPERATION...")
    download_result = execute_tool(
      client,
      "GOOGLEDRIVE_DOWNLOAD_FILE_OPERATION",
      {"file_id": file_id},
      user_id=user_id,
      connected_account_id=drive_account_id,
    )
    return extract_file_uploadable(download_result, default_name=filename)


def generate_post_text(client: Any, user_id: str) -> str:
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
