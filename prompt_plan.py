"""Parse daily prompt.docx text into a structured execution plan via Gemini."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from composio_tools import execute_tool
from linkedin_post_bot import extract_text, log

ImageSource = Literal["gemini", "drive", "none"]
PublishMode = Literal["draft", "publish"]

PLAN_PROMPT_TEMPLATE = """You convert a daily LinkedIn automation instruction into JSON only.

Today's instruction from prompt.docx:
---
{doc_text}
---

Return ONLY valid JSON (no markdown fences) matching this schema:
{{
  "caption_instruction": "string — what Gemini should write as the LinkedIn post caption",
  "image": {{
    "source": "gemini" | "drive" | "none",
    "drive_filename": "string or null — required when source is drive",
    "gemini_image_prompt": "string or null — doodle prompt when source is gemini"
  }},
  "publish_mode": "draft" | "publish"
}}

Rules:
- caption_instruction must reflect today's topic from the doc.
- publish_mode is "draft" when the doc says do not post, draft only, or save as draft; otherwise "publish".
- Default image.source is "gemini" when the doc asks for an AI/doodle image or says nothing about images.
- Use image.source "drive" when the doc says to use a specific file from Google Drive (set drive_filename).
- Use image.source "none" only when the doc explicitly says text-only with no image.
- gemini_image_prompt should match the caption topic (hand-drawn doodle style, white background).

Examples:

Doc: "Generate a LinkedIn post about MCP servers. Use a Gemini doodle image."
JSON: {{"caption_instruction":"Write a ~50 word LinkedIn post about MCP servers for AI agents. Professional, friendly, no hashtags.","image":{{"source":"gemini","drive_filename":null,"gemini_image_prompt":"Hand-drawn doodle on white: MCP server hub connecting AI apps to tools."}}}}

Doc: "Generate a LinkedIn post about blockchain. Use a Gemini doodle image."
JSON: {{"caption_instruction":"Write a ~50 word LinkedIn post about blockchain technology. Professional, friendly, no hashtags.","image":{{"source":"gemini","drive_filename":null,"gemini_image_prompt":"Hand-drawn doodle on white: blockchain nodes and linked blocks."}}}}

Doc: "Generate only a short caption. Use cursor-2025.png from Google Drive. Do not generate an AI image."
JSON: {{"caption_instruction":"Write a short professional LinkedIn caption. Plain text only, no hashtags.","image":{{"source":"drive","drive_filename":"cursor-2025.png","gemini_image_prompt":null}}}}
"""


@dataclass
class PromptPlan:
  caption_instruction: str
  image_source: ImageSource
  drive_filename: str | None
  gemini_image_prompt: str | None
  publish_mode: PublishMode = "publish"


def detect_publish_mode(doc_text: str) -> PublishMode:
  lower = doc_text.lower()
  if any(phrase in lower for phrase in ("do not post", "don't post", "draft only", "as a draft", "save as draft")):
    return "draft"
  return "publish"


def _extract_json_object(text: str) -> dict:
  text = text.strip()
  text = re.sub(r"^```(?:json)?\s*", "", text)
  text = re.sub(r"\s*```$", "", text)
  try:
    return json.loads(text)
  except json.JSONDecodeError:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
      raise
    return json.loads(match.group(0))


def normalize_plan(raw: dict) -> PromptPlan:
  caption = str(raw.get("caption_instruction", "")).strip()
  if not caption:
    raise ValueError("caption_instruction is required")

  image = raw.get("image") if isinstance(raw.get("image"), dict) else {}
  source = str(image.get("source", "gemini")).strip().lower()
  if source not in ("gemini", "drive", "none"):
    source = "gemini"

  drive_filename = image.get("drive_filename")
  if drive_filename is not None:
    drive_filename = str(drive_filename).strip() or None

  gemini_image_prompt = image.get("gemini_image_prompt")
  if gemini_image_prompt is not None:
    gemini_image_prompt = str(gemini_image_prompt).strip() or None

  if source == "drive" and not drive_filename:
    raise ValueError("drive_filename required when image.source is drive")

  if source == "gemini" and not gemini_image_prompt:
    gemini_image_prompt = (
      "Hand-drawn doodle illustration on white background matching the post topic. "
      "Simple sketch style, black ink lines, minimal color accents."
    )

  publish_mode = str(raw.get("publish_mode", "publish")).strip().lower()
  if publish_mode not in ("draft", "publish"):
    publish_mode = "publish"

  return PromptPlan(
    caption_instruction=caption,
    image_source=source,  # type: ignore[arg-type]
    drive_filename=drive_filename,
    gemini_image_prompt=gemini_image_prompt,
    publish_mode=publish_mode,  # type: ignore[arg-type]
  )


def fallback_plan(doc_text: str) -> PromptPlan:
  """Use doc text directly as caption instruction when Gemini JSON fails."""
  log("info", "Using fallback plan from raw prompt text.")
  return PromptPlan(
    caption_instruction=doc_text.strip(),
    image_source="gemini",
    drive_filename=None,
    gemini_image_prompt=(
      "Hand-drawn doodle illustration on white background matching the post topic. "
      "Simple sketch style, black ink lines, minimal color accents."
    ),
    publish_mode=detect_publish_mode(doc_text),
  )


def build_plan_from_doc(client: Any, user_id: str, doc_text: str) -> PromptPlan:
  log("info", "Interpreting prompt.docx with Gemini...")
  result = execute_tool(
    client,
    "GEMINI_GENERATE_CONTENT",
    {
      "model": "gemini-2.5-flash",
      "prompt": PLAN_PROMPT_TEMPLATE.format(doc_text=doc_text.strip()),
      "max_output_tokens": 512,
      "temperature": 0.2,
    },
    user_id=user_id,
  )
  raw_text = extract_text(result)
  if not raw_text:
    return fallback_plan(doc_text)

  try:
    raw = _extract_json_object(raw_text)
    plan = normalize_plan(raw)
    if detect_publish_mode(doc_text) == "draft":
      plan.publish_mode = "draft"
    log("info", f"Plan: image.source={plan.image_source}, publish_mode={plan.publish_mode}")
    return plan
  except (json.JSONDecodeError, ValueError, TypeError) as exc:
    log("info", f"Plan parse failed ({exc}); using fallback.")
    return fallback_plan(doc_text)
