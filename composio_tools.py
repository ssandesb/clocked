"""Shared Composio helpers for tool execution from GitHub Actions."""

from __future__ import annotations

import json
import mimetypes
import os
from typing import Any

import requests

_CONNECT_TIMEOUT = 5
_READ_TIMEOUT = 120

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


def _as_dict(value: Any) -> dict | None:
  if value is None:
    return None
  if hasattr(value, "model_dump"):
    return value.model_dump()
  if isinstance(value, dict):
    return value
  return None


def guess_mimetype(filename: str, fallback: str = "application/octet-stream") -> str:
  guessed, _ = mimetypes.guess_type(filename)
  return guessed or fallback


def stage_uploadable_for_linkedin(
  client: Any,
  *,
  filename: str,
  content: bytes,
  mimetype: str | None = None,
) -> dict:
  """Upload bytes into Composio storage for LINKEDIN_CREATE_LINKED_IN_POST."""
  from composio.core.models._files import _upload_bytes_to_s3

  mime = (mimetype or guess_mimetype(filename)).split(";")[0].strip()
  s3key = _upload_bytes_to_s3(
    client._client,
    filename=filename,
    content=content,
    mimetype=mime,
    tool="LINKEDIN_CREATE_LINKED_IN_POST",
    toolkit="linkedin",
  )
  return {"name": filename, "mimetype": mime, "s3key": s3key}


def _fetch_proxy_binary(proxy_response: Any) -> tuple[bytes, str]:
  payload = _as_dict(proxy_response) or {}
  binary = _as_dict(payload.get("binary_data"))
  if not binary:
    raise RuntimeError(f"Proxy response had no binary_data: {json.dumps(payload)[:500]}")

  status = payload.get("status")
  if status is not None and int(status) >= 400:
    raise RuntimeError(f"Proxy download failed with status {status}: {json.dumps(payload)[:500]}")

  url = str(binary.get("url", "")).strip()
  if not url:
    raise RuntimeError(f"Proxy binary_data missing url: {json.dumps(binary)[:300]}")

  response = requests.get(url, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT))
  if not response.ok:
    raise RuntimeError(f"Failed to fetch proxied file bytes (HTTP {response.status_code})")

  content_type = str(binary.get("content_type") or response.headers.get("content-type") or "application/octet-stream")
  return response.content, content_type.split(";")[0].strip()


def download_drive_file_bytes(
  client: Any,
  *,
  drive_account_id: str,
  file_id: str,
) -> tuple[bytes, str]:
  """Download a Drive file using Composio proxy + connected account OAuth."""
  proxy_response = client.tools.proxy(
    endpoint=f"https://www.googleapis.com/drive/v3/files/{file_id}",
    method="GET",
    connected_account_id=drive_account_id,
    parameters=[
      {"name": "alt", "value": "media", "type": "query"},
    ],
  )
  return _fetch_proxy_binary(proxy_response)


def download_url_bytes_via_drive_proxy(
  client: Any,
  *,
  drive_account_id: str,
  url: str,
) -> tuple[bytes, str]:
  """Fetch an authenticated Google URL using the Drive connected account."""
  proxy_response = client.tools.proxy(
    endpoint=url,
    method="GET",
    connected_account_id=drive_account_id,
  )
  return _fetch_proxy_binary(proxy_response)
