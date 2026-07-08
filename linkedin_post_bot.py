#!/usr/bin/env python3
"""
Daily LinkedIn post automation (runs on GitHub Actions, triggered by cron-job.org).

Flow:
  1. Gemini (Composio) drafts ~50-word post about MCP servers
  2. Gemini generates a doodle-style MCP image
  3. LinkedIn post is published via Composio
  4. Gmail sends a done email with the post link
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from typing import Any

from composio_tools import composio_client, dig, execute_tool, load_dotenv, require_env, unwrap_data


POST_PROMPT = (
  "Write a LinkedIn post of exactly 50 words about MCP (Model Context Protocol) servers. "
  "Explain what they are, why they matter for AI agents, and one practical benefit. "
  "Professional but friendly tone. No hashtags. No markdown. Plain text only."
)

IMAGE_PROMPT = (
  "Hand-drawn doodle illustration on white background: a friendly MCP server hub "
  "connecting AI apps to tools (calendar, code, database icons). Simple sketch style, "
  "black ink lines, minimal color accents, clean infographic feel."
)


def log(level: str, msg: str) -> None:
  print(f"[{level.upper():7s}] {msg}", flush=True)


def extract_text(result: dict) -> str:
  data = unwrap_data(result)
  if isinstance(data, str):
    text = data.strip()
  elif isinstance(data, dict):
    text = (
      dig(data, "text")
      or dig(data, "content")
      or dig(data, "message")
      or json.dumps(data)
    )
    text = str(text).strip()
  else:
    text = str(data).strip()

  text = re.sub(r"^```(?:\w+)?\s*", "", text)
  text = re.sub(r"\s*```$", "", text)
  return text.strip()


def extract_image_url(result: dict) -> str:
  data = unwrap_data(result)
  candidates: list[str] = []

  def walk(node: Any) -> None:
    if isinstance(node, dict):
      for key in ("s3url", "s3_url", "url", "image_url", "download_url", "file_url"):
        val = node.get(key)
        if isinstance(val, str) and val.startswith("http"):
          candidates.append(val)
      for val in node.values():
        walk(val)
    elif isinstance(node, list):
      for item in node:
        walk(item)

  walk(data)
  if not candidates:
    raise RuntimeError(f"Gemini image response had no URL: {json.dumps(result)[:500]}")
  return candidates[0]


def linkedin_author_urn(my_info: dict) -> str:
  data = unwrap_data(my_info)
  if not isinstance(data, dict):
    raise RuntimeError(f"Unexpected LINKEDIN_GET_MY_INFO payload: {data!r}")

  person_id = (
    data.get("id")
    or dig(data, "data", "id")
    or dig(data, "profile", "id")
  )
  if not person_id:
    raise RuntimeError(f"Could not resolve LinkedIn person id from: {json.dumps(data)[:500]}")

  person_id = str(person_id).strip()
  if person_id.startswith("urn:li:person:"):
    return person_id
  return f"urn:li:person:{person_id}"


def extract_post_link(create_result: dict) -> str:
  data = unwrap_data(create_result)
  urn = None
  if isinstance(data, dict):
    urn = (
      data.get("id")
      or data.get("urn")
      or data.get("activity")
      or dig(data, "data", "id")
      or dig(data, "data", "urn")
      or dig(data, "headers", "x-restli-id")
    )
  if not urn:
    walk_text = json.dumps(create_result)
    match = re.search(r"urn:li:(?:activity|share|ugcPost):[A-Za-z0-9_-]+", walk_text)
    if match:
      urn = match.group(0)

  if not urn:
    return "https://www.linkedin.com/feed/"

  encoded = urllib.parse.quote(str(urn), safe="")
  return f"https://www.linkedin.com/feed/update/{encoded}/"


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


def generate_doodle_image(client: Any, user_id: str) -> str:
  log("info", "Generating MCP doodle image with Gemini...")
  result = execute_tool(
    client,
    "GEMINI_GENERATE_IMAGE",
    {
      "model": "gemini-2.5-flash-image",
      "prompt": IMAGE_PROMPT,
      "aspect_ratio": "1:1",
      "image_size": "1K",
    },
    user_id=user_id,
  )
  url = extract_image_url(result)
  log("info", f"Image ready: {url[:80]}...")
  return url


def publish_linkedin_post(
  client: Any,
  *,
  user_id: str,
  linkedin_account_id: str,
  commentary: str,
  image_url: str,
) -> str:
  log("info", "Resolving LinkedIn author...")
  my_info = execute_tool(
    client,
    "LINKEDIN_GET_MY_INFO",
    {},
    user_id=user_id,
    connected_account_id=linkedin_account_id,
  )
  author = linkedin_author_urn(my_info)

  log("info", "Publishing LinkedIn post...")
  create_result = execute_tool(
    client,
    "LINKEDIN_CREATE_LINKED_IN_POST",
    {
      "author": author,
      "commentary": commentary,
      "visibility": "PUBLIC",
      "lifecycleState": "PUBLISHED",
      "images": [image_url],
    },
    user_id=user_id,
    connected_account_id=linkedin_account_id,
  )
  link = extract_post_link(create_result)
  log("info", f"LinkedIn post published: {link}")
  return link


def send_done_email(
  client: Any,
  *,
  user_id: str,
  gmail_account_id: str,
  recipient: str,
  post_text: str,
  post_link: str,
) -> None:
  log("info", f"Sending confirmation email to {recipient}...")
  body = (
    "Your automated LinkedIn post is live.\n\n"
    f"Post link:\n{post_link}\n\n"
    "Post text:\n"
    f"{post_text}\n"
  )
  execute_tool(
    client,
    "GMAIL_SEND_EMAIL",
    {
      "recipient_email": recipient,
      "subject": "Done: LinkedIn MCP post published",
      "body": body,
    },
    user_id=user_id,
    connected_account_id=gmail_account_id,
  )
  log("info", "Email sent.")


def main() -> int:
  load_dotenv()

  user_id = require_env("COMPOSIO_USER_ID")
  linkedin_account_id = os.environ.get("COMPOSIO_LINKEDIN_CONNECTED_ACCOUNT_ID", "ca_v3V7Hx653dg3").strip()
  gmail_account_id = os.environ.get("COMPOSIO_GMAIL_CONNECTED_ACCOUNT_ID", "ca_0ju99DwEbuxD").strip()
  notify_email = os.environ.get("NOTIFY_EMAIL", "bajracharyasandeshh@gmail.com").strip()

  if not linkedin_account_id:
    raise RuntimeError("COMPOSIO_LINKEDIN_CONNECTED_ACCOUNT_ID is not set")
  if not gmail_account_id:
    raise RuntimeError("COMPOSIO_GMAIL_CONNECTED_ACCOUNT_ID is not set")

  client = composio_client()

  post_text = generate_post_text(client, user_id)
  image_url = generate_doodle_image(client, user_id)
  post_link = publish_linkedin_post(
    client,
    user_id=user_id,
    linkedin_account_id=linkedin_account_id,
    commentary=post_text,
    image_url=image_url,
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
