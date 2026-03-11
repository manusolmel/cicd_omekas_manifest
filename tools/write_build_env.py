#!/usr/bin/env python3

# Reads image coordinates from the manifest and writes a KEY=value dotenv file

# Variables:
#   BASE_IMAGE    base image name (manifest base.image)
#   BASE_TAG      base image tag  (manifest base.tag)
#   TARGET_IMAGE  full target image ref  (<project.image.name>:<tag>)
#   BUILD_DATE    ISO 8601 UTC build timestamp
#   VCS_REF       full commit SHA (CI_COMMIT_SHA or 'unknown')


from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from utility import get_path, load_yaml


def _require_str(doc: dict, keys: tuple[str, ...]) -> str:
    # Read a required string field from the manifest or exit with an error.

    # Uses sys.exit instead of raising so that missing fields abort immediately
    
    ok, val = get_path(doc, keys)
    if not ok or not isinstance(val, str) or not val.strip():
        print(f"ERROR: missing manifest value at {'.'.join(keys)}", file=sys.stderr)
        sys.exit(1)
    return val


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if len(argv) != 1:
        print("Usage: python tools/write_build_env.py <manifest.yml>", file=sys.stderr)
        return 2

    manifest_path = Path(argv[0])
    if not manifest_path.is_file():
        print(f"Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        doc = load_yaml(manifest_path)
    except Exception as e:
        print(f"ERROR reading manifest: {e}", file=sys.stderr)
        return 1

    base_image = _require_str(doc, ("base", "image"))
    base_tag = _require_str(doc, ("base", "tag"))
    project_image = _require_str(doc, ("project", "image", "name"))

    # Tag priority: release tag > short SHA > 'dev' 
    image_tag = (
        os.environ.get("CI_COMMIT_TAG")
        or os.environ.get("CI_COMMIT_SHORT_SHA")
        or "dev"
    )
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    vcs_ref = os.environ.get("CI_COMMIT_SHA", "unknown")
    target_image = f"{project_image}:{image_tag}"

    output_path = Path(".ci/build.env")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"BASE_IMAGE={base_image}",
        f"BASE_TAG={base_tag}",
        f"TARGET_IMAGE={target_image}",
        f"BUILD_DATE={build_date}",
        f"VCS_REF={vcs_ref}",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
