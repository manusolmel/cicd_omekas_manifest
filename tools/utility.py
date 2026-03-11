#!/usr/bin/env python3


from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


def run(cmd: list[str]) -> None:
    # run a shell command and fail fast if it exits with non-zero status."""
    subprocess.run(cmd, check=True)


def load_yaml(path: Path) -> dict[str, Any]:
    
    # load YAML from disk and enforce that the root is a mapping.

    # the validator and fetch scripts both assume dictionary-style access.
    
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("The root of the YAML document must be a mapping (key-value pairs).")
    return data


def get_path(doc: Mapping[str, Any], keys: Sequence[str]) -> tuple[bool, Any]:
    
    # Traverse nested dictionaries safely.

    # Returns:
    # - (True, value) when the full path exists
    # - (False, None) if any segment is missing or a non-mapping is found
    
    cur: Any = doc
    for k in keys:
        if not isinstance(cur, Mapping):
            return False, None
        if k not in cur:
            return False, None
        cur = cur[k]
    return True, cur


def path_str(path: Sequence[str]) -> str:
    # Render tuple paths as dotted strings.
    return ".".join(path)


def remove_path_if_exists(dest: Path) -> None:
    # Remove a file/folder path if it already exists.
    if dest.exists():
        run(["rm", "-rf", str(dest)])


def ensure_clean_dir(dest: Path) -> None:
    # Ensure a directory exists and is empty before writing downloaded contents.
    remove_path_if_exists(dest)
    dest.mkdir(parents=True, exist_ok=True)


def flatten_single_top_level_dir(dest: Path) -> None:
    
    # Normalize extracted ZIP layouts.

    # Many release ZIPs contain a single root folder (repo-name-version/...). If that
    # happens, move its contents up to `dest` so downstream copy steps are predictable.
    
    children = [p for p in dest.iterdir() if p.is_dir()]
    files = [p for p in dest.iterdir() if p.is_file()]

    if len(children) == 1 and len(files) == 0:
        root = children[0]
        for item in root.iterdir():
            item.rename(dest / item.name)
        root.rmdir()


def download_and_extract_zip(url: str, dest: Path) -> None:
    # Download a ZIP file, extract it into `dest`, normalize layout, and clean temp file.
    zip_path = dest / "download.zip"
    urllib.request.urlretrieve(url, zip_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)

    flatten_single_top_level_dir(dest)
    zip_path.unlink(missing_ok=True)


def normalize_repo_url(repo: str) -> str:
    # Strip '.git' suffix to normalize repository base URL for release URLs.
    return repo[:-4] if repo.endswith(".git") else repo


def build_release_zip_url(repo: str, version: str, asset: str) -> str:
    
    # Build a release asset URL from repo/version/asset.

    # GitLab and GitHub formats differ, so this function selects the right pattern based on the host.
    
    repo = normalize_repo_url(repo).rstrip("/")
    asset = urllib.parse.quote(asset)

    host = urllib.parse.urlparse(repo).netloc.lower()
    if "gitlab" in host:
        return f"{repo}/-/releases/{version}/downloads/{asset}"
    if "github" in host:
        return f"{repo}/releases/download/{version}/{asset}"

    # Generic fallback for forges that follow GitHub-style release URLs.
    return f"{repo}/releases/download/{version}/{asset}"


def resolve_release_zip_url(src: Mapping[str, Any], name: str) -> str:

    # Resolve the ZIP download URL for a release source.

    # Expected format:
    # - `repo` + `version` + `asset`

    repo = src.get("repo")
    version = src.get("version")
    asset = src.get("asset")

    missing: list[str] = []
    if not isinstance(repo, str) or not repo.strip():
        missing.append("repo")
    if not isinstance(version, str) or not version.strip():
        missing.append("version")
    if not isinstance(asset, str) or not asset.strip():
        missing.append("asset")

    if missing:
        fields = ", ".join(missing)
        raise RuntimeError(f"release_zip missing '{fields}' for {name}")

    return build_release_zip_url(repo, version, asset)


def _resolve_catalog_api_url(group: str) -> str:
    # Return the official Omeka add-ons API URL for modules/themes.
    if group == "modules":
        return "https://omeka.org/add-ons/json/s_module.json"
    if group == "themes":
        return "https://omeka.org/add-ons/json/s_theme.json"
    raise RuntimeError(f"Unsupported extension group '{group}' for catalog resolution")


def _resolve_catalog_entry(
    entries: Mapping[str, Any], group: str, name: str
) -> tuple[str, Mapping[str, Any]]:
    # Resolve an add-on entry by name.

    # The catalog API keys are not always consistently cased (for example: "default"),
    # so we allow exact match first and then case-insensitive fallback.  
    exact = entries.get(name)
    if isinstance(exact, Mapping):
        return name, exact

    folded = name.casefold()
    for key, value in entries.items():
        if isinstance(key, str) and isinstance(value, Mapping) and key.casefold() == folded:
            return key, value

    raise RuntimeError(f"{group}.{name}: add-on not found in official Omeka catalog")


@lru_cache(maxsize=2)
def _load_catalog_entries(group: str) -> Mapping[str, Any]:
    # Load and cache official Omeka catalog entries for modules/themes.
    api_url = _resolve_catalog_api_url(group)
    try:
        with urllib.request.urlopen(api_url, timeout=30) as response:
            data = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"failed to read catalog API '{api_url}': {exc}") from exc

    if not isinstance(data, Mapping):
        raise RuntimeError("invalid catalog API payload (expected mapping root)")

    return data


def _version_candidates(version: str) -> list[str]:
    
    # Build acceptable version lookup keys.

    # Catalog entries can index versions either as "1.2.3" or "v1.2.3".
    
    raw = version.strip()
    if not raw:
        return []

    candidates: list[str] = [raw]
    if raw[0].lower() == "v":
        candidates.append(raw[1:])
    else:
        candidates.append(f"v{raw}")

    # Preserve order while deduplicating.
    return list(dict.fromkeys(candidates))


def resolve_catalog_zip_url(group: str, name: str, version: str) -> str:

    # Resolve a deterministic ZIP URL from the official Omeka add-ons catalog.

    # Resolution is version-pinned: the caller must provide an explicit version.

    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"{group}.{name}: catalog source requires a non-empty 'version'")

    try:
        data = _load_catalog_entries(group)
    except RuntimeError as exc:
        raise RuntimeError(f"{group}.{name}: {exc}") from exc

    entry_name, entry = _resolve_catalog_entry(data, group, name)
    versions = entry.get("versions")
    if not isinstance(versions, Mapping):
        raise RuntimeError(f"{group}.{name}: catalog entry '{entry_name}' has no valid 'versions' map")

    selected: Mapping[str, Any] | None = None
    for candidate in _version_candidates(version):
        value = versions.get(candidate)
        if isinstance(value, Mapping):
            selected = value
            break

    if selected is None:
        available = ", ".join(sorted(str(k) for k in versions.keys()))
        raise RuntimeError(
            f"{group}.{name}: version '{version}' not found in catalog entry '{entry_name}' "
            f"(available: {available})"
        )

    download_url = selected.get("download_url")
    if not isinstance(download_url, str) or not download_url.strip():
        raise RuntimeError(
            f"{group}.{name}: catalog entry '{entry_name}' version '{version}' has no download URL"
        )

    return download_url


def resolve_omeka_s_cli_zip_url(group: str, name: str, version: str) -> str:
    
    # Resolve download URL with the same catalog backend used by omeka-s-cli.

    # The CLI also uses the official Omeka add-ons API for modules/themes.
    
    return resolve_catalog_zip_url(group, name, version)
