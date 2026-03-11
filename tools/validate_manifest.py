#!/usr/bin/env python3

# CLI validator for Omeka S project manifests.

# This script validates only the *schema-level* expectations used by the CI/CD pipeline:
# - required keys exist
# - values have expected types
# - apiVersion/kind match the spec
# - extension sources declare supported types and required fields


from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import manifest_rules
from utility import (
    get_path as utility_get_path,
    load_yaml as utility_load_yaml,
    path_str as utility_path_str,
)


def load_yaml(path: Path) -> dict[str, Any]:
    # Load YAML from disk and ensure the root node is a mapping (dict).
    return utility_load_yaml(path)


def get_path(doc: Mapping[str, Any], keys: Sequence[str]) -> tuple[bool, Any]:

    # Safely navigate nested dicts.

    # Returns (exists, value). If any segment is missing or the structure is not a dict, exists=False.
    
    return utility_get_path(doc, keys)


def _path_str(path: Sequence[str]) -> str:
    # Render a tuple path like ('project','image','name') as 'project.image.name'.
    return utility_path_str(path)


def validate_required(doc: Mapping[str, Any]) -> list[str]:
    # Check presence of all REQUIRED_PATHS.
    errors: list[str] = []
    for path in manifest_rules.REQUIRED_PATHS:
        exists, _ = get_path(doc, path)
        if not exists:
            errors.append(f"Missing required key: {_path_str(path)}")
    return errors


def validate_exact_values(doc: Mapping[str, Any]) -> list[str]:
    # Check fields that must match an exact value (apiVersion/kind).
    errors: list[str] = []
    for path, expected in manifest_rules.EXACT_VALUES.items():
        exists, value = get_path(doc, path)
        if not exists:
            continue  # required check will report this
        if value != expected:
            errors.append(f"Invalid value for {_path_str(path)}: expected '{expected}', got '{value}'")
    return errors

def validate_registry_namespace(doc: Mapping[str, Any]) -> list[str]:
    # Only executed in CI. Verifies that the registry defined in the manifest matches
    # the namespace of the project running the pipeline.
    errors: list[str] = []

    ci_namespace = os.environ.get("CI_PROJECT_NAMESPACE")
    if not ci_namespace:
        return errors
    
    exists, image_name = get_path(doc, ("project", "image", "name"))
    if not exists or not isinstance(image_name, str):
        return errors
    
    expected_prefix = f"registry.gitlab.com/{ci_namespace}/"
    if not image_name.startswith(expected_prefix):
        errors.append(
            f"project.image.name apunta fuera del namespace '{ci_namespace}'. "
            f"Debe empezar por '{expected_prefix}' o usar un Deploy Token explícito."
        )
    return errors


def validate_types(doc: Mapping[str, Any]) -> list[str]:
    # Validate EXPECTED_TYPES for all paths that exist.
    errors: list[str] = []
    for path, expected_type in manifest_rules.EXPECTED_TYPES.items():
        exists, value = get_path(doc, path)
        if not exists:
            continue  # required/optional handled elsewhere
        if not isinstance(value, expected_type):
            errors.append(
                f"Invalid type for {_path_str(path)}: "
                f"expected {expected_type.__name__}, got {type(value).__name__}"
            )
    return errors


def validate_list_items(doc: Mapping[str, Any]) -> list[str]:
    
    # Validate list structure for modules/themes:
    # - list items must be dicts
    # - required keys inside each item must exist
    
    errors: list[str] = []

    for list_path, required_rel_paths in manifest_rules.LIST_ITEM_REQUIRED.items():
        exists, items = get_path(doc, list_path)
        if not exists:
            continue  # required/optional handled elsewhere
        if not isinstance(items, list):
            continue  # type error handled by validate_types

        prefix = _path_str(list_path)

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(
                    f"Invalid type for {prefix}[{i}]: expected dict, got {type(item).__name__}"
                )
                continue

            for rel_path in required_rel_paths:
                ok, _ = get_path(item, rel_path)
                if not ok:
                    errors.append(f"Missing required key: {prefix}[{i}].{_path_str(rel_path)}")

    return errors


def validate_list_element_types(doc: Mapping[str, Any]) -> list[str]:
    # Validate element types for known lists (e.g., build.target_tags is list[str]).
    errors: list[str] = []
    for list_path, elem_type in manifest_rules.LIST_ELEMENT_TYPES.items():
        exists, items = get_path(doc, list_path)
        if not exists:
            continue
        if not isinstance(items, list):
            continue  # validate_types will report list vs non-list

        prefix = _path_str(list_path)
        for i, item in enumerate(items):
            if not isinstance(item, elem_type):
                errors.append(
                    f"Invalid type for {prefix}[{i}]: expected {elem_type.__name__}, got {type(item).__name__}"
                )
    return errors


def validate_source_types(doc: Mapping[str, Any]) -> list[str]:
    
    # Validate extensions[*].source:
    # - source.type must be supported
    # - source must contain the required fields for that type
    # - required fields must have expected types (usually strings)
    
    errors: list[str] = []

    for list_path in [("extensions", "modules"), ("extensions", "themes")]:
        exists, items = get_path(doc, list_path)
        if not exists or not isinstance(items, list):
            continue

        prefix = _path_str(list_path)

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue  # validate_list_items reports this

            ok_source, source = get_path(item, ("source",))
            if not ok_source or not isinstance(source, dict):
                continue  # validate_list_items reports missing keys / validate_types reports types

            ok_type, source_type = get_path(source, ("type",))
            if not ok_type or not isinstance(source_type, str):
                continue  # validate_list_items reports missing, validate_types doesn't cover list items

            if source_type not in manifest_rules.SUPPORTED_SOURCE_TYPES:
                allowed = ", ".join(sorted(manifest_rules.SUPPORTED_SOURCE_TYPES))
                errors.append(
                    f"Invalid source.type: {prefix}[{i}].source.type "
                    f"(got '{source_type}'; allowed: {allowed})"
                )
                continue

            # Required fields for the specific source.type
            required_fields = manifest_rules.SOURCE_TYPE_REQUIRED.get(source_type, [])
            for rel_path in required_fields:
                ok, _ = get_path(source, rel_path)
                if not ok:
                    errors.append(f"Missing required key: {prefix}[{i}].source.{_path_str(rel_path)}")

            # Type checks for required fields
            type_rules = manifest_rules.SOURCE_TYPE_REQUIRED_TYPES.get(source_type, {})
            for rel_path, expected_type in type_rules.items():
                ok, value = get_path(source, rel_path)
                if not ok:
                    continue  # already reported missing above
                if not isinstance(value, expected_type):
                    errors.append(
                        f"Invalid type for {prefix}[{i}].source.{_path_str(rel_path)}: "
                        f"expected {expected_type.__name__}, got {type(value).__name__}"
                    )

    return errors


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if len(argv) != 1:
        print("Usage: python tools/validate_manifest.py <manifest.yml>", file=sys.stderr)
        return 2

    manifest_path = Path(argv[0])
    if not manifest_path.is_file():
        print(f"Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        doc = load_yaml(manifest_path)
    except Exception as e:
        print(f"ERROR reading/parsing manifest: {e}", file=sys.stderr)
        return 1

    errors: list[str] = []
    errors.extend(validate_required(doc))
    errors.extend(validate_exact_values(doc))
    errors.extend(validate_types(doc))
    errors.extend(validate_list_items(doc))
    errors.extend(validate_list_element_types(doc))
    errors.extend(validate_source_types(doc))
    errors.extend(validate_registry_namespace(doc))

    if errors:
        print("Manifest validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: manifest is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
