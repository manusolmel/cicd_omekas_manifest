#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from utility import (
    download_and_extract_zip,
    ensure_clean_dir,
    load_yaml,
    remove_path_if_exists,
    resolve_catalog_zip_url,
    resolve_omeka_s_cli_zip_url,
    resolve_release_zip_url,
    run,
)


def fetch_git_source(src: Mapping[str, Any], name: str, dest: Path) -> None:
    # git sources are resolved by cloning the repo and checking out the exact ref.
    print("REPO:", src.get("repo"))
    print("REF:", src.get("ref"))

    run(["git", "clone", "--no-checkout", src["repo"], str(dest)])
    run(["git", "-C", str(dest), "checkout", "--force", src["ref"]])


def fetch_release_zip_source(src: Mapping[str, Any], name: str, dest: Path) -> None:
    # release_zip follows manifest_rules: repo + version + asset.
    url = resolve_release_zip_url(src, name)
    print("URL:", url)
    download_and_extract_zip(url, dest)


def _require_version(src: Mapping[str, Any], group: str, name: str, source_type: str) -> str:
    # return a non-empty version string or raise a readable runtime error.
    version = src.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"{group}.{name}: source.type='{source_type}' requires a non-empty source.version")
    return version


def fetch_catalog_source(src: Mapping[str, Any], group: str, name: str, dest: Path) -> None:
    # catalog is resolved against the official Omeka add-ons API and pinned by version.
    version = _require_version(src, group, name, "catalog")
    url = resolve_catalog_zip_url(group, name, version)
    print("URL:", url)
    download_and_extract_zip(url, dest)


def fetch_omeka_s_cli_source(src: Mapping[str, Any], group: str, name: str, dest: Path) -> None:
    # omeka-s-cli mode uses the same official catalog backend used by the CLI.
    version = _require_version(src, group, name, "omeka-s-cli")
    url = resolve_omeka_s_cli_zip_url(group, name, version)
    print("URL:", url)
    download_and_extract_zip(url, dest)


def process_extensions(items: list[dict[str, Any]], group: str, label: str) -> None:
    for ext in items:
        name = ext["name"]
        src = ext.get("source", {})
        typ = src.get("type")

        print(f"build-context/{group}/{name}")
        print(f"{label} - TYPE:", typ)

        dest = Path(f"build-context/{group}") / name

        if typ == "git":
            # git clone expects destination path to not exist.
            remove_path_if_exists(dest)
            fetch_git_source(src, name, dest)

        elif typ == "release_zip":
            # zip flows reuse a clean directory where files are extracted.
            ensure_clean_dir(dest)
            fetch_release_zip_source(src, name, dest)

        elif typ == "catalog":
            ensure_clean_dir(dest)
            fetch_catalog_source(src, group, name, dest)

        elif typ == "omeka-s-cli":
            ensure_clean_dir(dest)
            fetch_omeka_s_cli_source(src, group, name, dest)

        else:
            raise RuntimeError(f"{group}.{name}: unsupported source.type '{typ}'")


def main() -> int:
    doc = load_yaml(Path("manifest.yml"))
    modules = doc.get("extensions", {}).get("modules", [])
    themes = doc.get("extensions", {}).get("themes", [])

    process_extensions(modules, "modules", "Module")
    process_extensions(themes, "themes", "Theme")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
