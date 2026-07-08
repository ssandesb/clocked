"""Shared Composio helpers for tool execution from GitHub Actions."""

from __future__ import annotations

import json
import os
from typing import Any

def load_dotenv(path: str = ".env") -> None:
  if not os.path.isfile(path):
    return
  with open(path, encoding="utf-8") as fh:
    for raw in fh:
      line = raw.strip()
      if not line or line.startswith("#") or "=" not in line:
        continue
      key, _, val = line.partition("=")
      key = key.strip()
      val = val.strip().strip("'").strip('"')
      if key and key not in os.environ:
        os.environ[key] = val


def composio_client():
  from composio import Composio

  api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  if not api_key:
    raise RuntimeError("COMPOSIO_API_KEY is not set")
  return Composio(api_key=api_key)


def execute_tool(
  client: Any,
  slug: str,
  arguments: dict,
  *,
  user_id: str | None = None,
  connected_account_id: str | None = None,
) -> dict:
  kwargs: dict = {
    "slug": slug,
    "arguments": arguments,
    "dangerously_skip_version_check": True,
  }
  if user_id:
    kwargs["user_id"] = user_id
  if connected_account_id:
    kwargs["connected_account_id"] = connected_account_id
  result = client.tools.execute(**kwargs)
  if not isinstance(result, dict):
    result = {"data": result}
  if result.get("successful") is False:
    err = result.get("error") or result.get("data") or result
    raise RuntimeError(f"{slug} failed: {err}")
  return result


def require_env(name: str) -> str:
  value = os.environ.get(name, "").strip()
  if not value:
    raise RuntimeError(f"{name} is not set")
  return value


def unwrap_data(payload: Any) -> Any:
  """Normalize Composio tool responses that nest JSON in `data`."""
  if payload is None:
    return None
  if isinstance(payload, str):
    text = payload.strip()
    if not text:
      return payload
    try:
      return unwrap_data(json.loads(text))
    except json.JSONDecodeError:
      return payload
  if isinstance(payload, dict):
    if "data" in payload and len(payload) <= 3:
      return unwrap_data(payload.get("data"))
    if "response" in payload:
      return unwrap_data(payload.get("response"))
    if "text" in payload and isinstance(payload["text"], str):
      return payload["text"]
  return payload


def dig(payload: Any, *keys: str) -> Any:
  cur = payload
  for key in keys:
    if not isinstance(cur, dict):
      return None
    cur = cur.get(key)
  return cur
