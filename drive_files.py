"""Google Drive file find/download helpers (images, docx, etc.)."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from composio_tools import (
  dig,
  download_drive_file_bytes,
  download_url_bytes_via_drive_proxy,
  execute_tool,
  export_google_doc_text,
  guess_mimetype,
  stage_uploadable_for_linkedin,
  unwrap_data,
)
from linkedin_post_bot import extract_file_uploadable, log

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


def _drive_files_from_find(result: dict) -> list[dict]:
  data = unwrap_data(result)
  if isinstance(data, str):
    try:
      data = json.loads(data)
    except json.JSONDecodeError:
      pass

  if isinstance(data, dict):
    raw = data.get("files")
    if isinstance(raw, list):
      return [f for f in raw if isinstance(f, dict)]
    nested = dig(data, "data", "files")
    if isinstance(nested, list):
      return [f for f in nested if isinstance(f, dict)]
  return []


def find_drive_file(result: dict, *, filename: str) -> dict:
  files = _drive_files_from_find(result)
  if not files:
    raise RuntimeError(
      f"Google Drive file '{filename}' not found. "
      f"Response: {json.dumps(result)[:500]}"
    )

  for item in files:
    name = str(item.get("name", "")).strip()
    file_id = str(item.get("id", "")).strip()
    if name == filename and file_id:
      return item

  first = files[0]
  file_id = str(first.get("id", "")).strip()
  if not file_id:
    raise RuntimeError(f"No file id in Drive search result: {json.dumps(first)[:300]}")
  log("info", f"Exact name match missing; using first result: {first.get('name')!r}")
  return first


def find_drive_file_id(result: dict, *, filename: str) -> str:
  return str(find_drive_file(result, filename=filename)["id"])


def extract_download_uri(result: dict) -> str | None:
  data = unwrap_data(result)

  def walk(node: Any) -> str | None:
    if isinstance(node, dict):
      for key in ("downloadUri", "download_uri"):
        val = node.get(key)
        if isinstance(val, str) and val.startswith("http"):
          return val
      for val in node.values():
        found = walk(val)
        if found:
          return found
    elif isinstance(node, list):
      for item in node:
        found = walk(item)
        if found:
          return found
    return None

  return walk(data)


def fetch_drive_prompt_text(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  filename: str,
) -> str:
  """Read a Drive prompt file (Google Doc or .docx upload) as plain text."""
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
  file_meta = find_drive_file(find_result, filename=filename)
  file_id = str(file_meta.get("id", "")).strip()
  mime_type = str(file_meta.get("mimeType", "")).strip()
  log("info", f"Found Drive file id: {file_id} ({mime_type or 'unknown type'})")

  if mime_type == GOOGLE_DOC_MIME:
    log("info", "Exporting Google Doc as plain text...")
    return export_google_doc_text(
      client,
      drive_account_id=drive_account_id,
      file_id=file_id,
    )

  content, _ = _download_drive_file_by_id(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    file_id=file_id,
    filename=filename,
  )
  return _bytes_to_prompt_text(content, filename=filename)


def _bytes_to_prompt_text(content: bytes, *, filename: str) -> str:
  if filename.lower().endswith(".docx"):
    from docx import Document

    doc = Document(BytesIO(content))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
      raise RuntimeError(f"{filename} is empty")
    return "\n\n".join(paragraphs)

  text = content.decode("utf-8", errors="replace").strip()
  if not text:
    raise RuntimeError(f"{filename} is empty")
  return text


def _download_drive_file_by_id(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  file_id: str,
  filename: str,
) -> tuple[bytes, str]:
  for slug, args in (
    ("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": file_id}),
    ("GOOGLEDRIVE_DOWNLOAD_FILE_OPERATION", {"file_id": file_id}),
  ):
    log("info", f"Trying {slug}...")
    download_result = execute_tool(
      client,
      slug,
      args,
      user_id=user_id,
      connected_account_id=drive_account_id,
    )
    download_uri = extract_download_uri(download_result)
    if download_uri:
      log("info", "Fetching Drive downloadUri via Composio proxy...")
      return download_url_bytes_via_drive_proxy(
        client,
        drive_account_id=drive_account_id,
        url=download_uri,
      )

  log("info", "Downloading Drive file via Composio proxy...")
  return download_drive_file_bytes(
    client,
    drive_account_id=drive_account_id,
    file_id=file_id,
  )


def fetch_drive_file_content(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  filename: str,
) -> tuple[bytes, str]:
  """Download any Drive file as raw bytes (docx, png, etc.)."""
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
  return _download_drive_file_by_id(
    client,
    user_id=user_id,
    drive_account_id=drive_account_id,
    file_id=file_id,
    filename=filename,
  )


def fetch_drive_image_uploadable(
  client: Any,
  *,
  user_id: str,
  drive_account_id: str,
  filename: str,
) -> dict:
  """Download a Drive image and stage as LinkedIn FileUploadable."""
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

  for slug, args in (
    ("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": file_id}),
    ("GOOGLEDRIVE_DOWNLOAD_FILE_OPERATION", {"file_id": file_id}),
  ):
    log("info", f"Trying {slug}...")
    download_result = execute_tool(
      client,
      slug,
      args,
      user_id=user_id,
      connected_account_id=drive_account_id,
    )
    try:
      return extract_file_uploadable(download_result, default_name=filename)
    except RuntimeError:
      download_uri = extract_download_uri(download_result)
      if download_uri:
        log("info", "Staging image downloadUri via Composio proxy...")
        content, mimetype = download_url_bytes_via_drive_proxy(
          client,
          drive_account_id=drive_account_id,
          url=download_uri,
        )
        return stage_uploadable_for_linkedin(
          client,
          filename=filename,
          content=content,
          mimetype=mimetype or guess_mimetype(filename),
        )

  log("info", "Downloading image via Composio proxy...")
  content, mimetype = download_drive_file_bytes(
    client,
    drive_account_id=drive_account_id,
    file_id=file_id,
  )
  return stage_uploadable_for_linkedin(
    client,
    filename=filename,
    content=content,
    mimetype=mimetype or guess_mimetype(filename),
  )
