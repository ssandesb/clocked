"""Shared Composio -> GitHub attendance workflow dispatch."""

from __future__ import annotations

import json
import os
from typing import Any

from bots.lib.paths import REPO_ROOT

DEFAULT_OWNER = "ssandesb"
DEFAULT_REPO = "clocked"
DEFAULT_WORKFLOW = "attendance.yml"
DEFAULT_REF = "main"


def load_dotenv(path: str | None = None) -> None:
  env_path = path or str(REPO_ROOT / ".env")
  if not os.path.isfile(env_path):
    return
  with open(env_path, encoding="utf-8") as fh:
    for raw in fh:
      line = raw.strip()
      if not line or line.startswith("#") or "=" not in line:
        continue
      key, _, val = line.partition("=")
      key = key.strip()
      val = val.strip().strip("'").strip('"')
      if key and key not in os.environ:
        os.environ[key] = val


def execute_tool(client: Any, slug: str, arguments: dict, user_id: str | None) -> dict:
  kwargs: dict = {
    "slug": slug,
    "arguments": arguments,
    "dangerously_skip_version_check": True,
  }
  if user_id:
    kwargs["user_id"] = user_id
  result = client.tools.execute(**kwargs)
  if not isinstance(result, dict):
    result = {"data": result}
  if result.get("successful") is False:
    err = result.get("error") or result.get("data") or result
    raise RuntimeError(f"{slug} failed: {err}")
  return result


def dispatch_attendance(
  client: Any,
  action: str,
  *,
  owner: str | None = None,
  repo: str | None = None,
  workflow_id: str | None = None,
  ref: str | None = None,
  user_id: str | None = None,
  force: bool = True,
) -> dict:
  if action not in ("clock-in", "clock-out"):
    raise ValueError(f"action must be clock-in or clock-out, got {action!r}")

  owner = owner or os.environ.get("GITHUB_OWNER", DEFAULT_OWNER)
  repo = repo or os.environ.get("GITHUB_REPO", DEFAULT_REPO)
  workflow_id = workflow_id or os.environ.get("GITHUB_WORKFLOW", DEFAULT_WORKFLOW)
  ref = ref or os.environ.get("GITHUB_REF", DEFAULT_REF)

  inputs = {"action": action, "force": force}
  return execute_tool(
    client,
    "GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT",
    {
      "owner": owner,
      "repo": repo,
      "workflow_id": workflow_id,
      "ref": ref,
      "inputs": json.dumps(inputs),
    },
    user_id,
  )


def composio_client():
  from composio import Composio

  api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  if not api_key:
    raise RuntimeError("COMPOSIO_API_KEY is not set")
  return Composio(api_key=api_key)
