# Tools reference

All tools live in the `tools/` directory and must be run from the **repository root**. They share common helpers from `tools/utility.py`.

---

## `validate_manifest.py`

Validates the manifest schema before any fetch or build step. Used as the first step in the CI pipeline.

### Usage

```bash
python tools/validate_manifest.py <manifest.yml>
```

### Example

```bash
python tools/validate_manifest.py manifest.yml
# OK: manifest is valid

python tools/validate_manifest.py bad.yml
# Manifest validation FAILED:
# - Missing required key: base.tag
# - Invalid source.type: extensions.modules[0].source.type (got 'zip'; allowed: catalog, git, omeka-s-cli, release_zip)
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Manifest is valid |
| `1` | Validation errors found, or file not found / parse error |
| `2` | Wrong number of arguments |

### What it checks

The validator runs six passes in sequence and collects **all errors** before printing them — it does not stop at the first failure.

| Pass | What it checks |
|---|---|
| Required fields | All required paths exist (e.g. `base.tag`, `project.image.name`) |
| Exact values | `apiVersion` equals `"libnamic.omk/v1"`, `kind` equals `"OmekaSProject"` |
| Types | Field types match expected types (e.g. `extensions.modules` is a list) |
| List item structure | Each module/theme has `name`, `source`, and `source.type` |
| List element types | Elements inside known lists have the correct type (e.g. `build.target_tags` contains strings) |
| Source types | `source.type` is a supported value; required fields for that type are present and correctly typed |

### Source: `tools/validate_manifest.py`, `tools/manifest_rules.py`

Validation logic lives in `validate_manifest.py`. All rules (required paths, allowed types, required fields per source type) are declared as pure data in `manifest_rules.py` — no logic there.

---

## `fetch.py`

Downloads all modules and themes declared in `manifest.yml` into `build-context/`.

### Usage

```bash
python tools/fetch.py
```

No arguments. Always reads `manifest.yml` from the current directory and writes to `build-context/`.

### Output layout

```
build-context/
├── modules/
│   ├── Mapping/
│   ├── CSVImport/
│   └── ValueSuggest/
└── themes/
    ├── Default/
    └── Freedom/
```

Each extension gets its own subdirectory named after the `name` field in the manifest. The Dockerfile copies this layout directly into the container.

### Behaviour per source type

**`catalog` and `omeka-s-cli`**

Queries the official Omeka add-ons API to resolve the download URL for the given version, then downloads and extracts the ZIP.

```
GET https://omeka.org/add-ons/json/s_module.json  (for modules)
GET https://omeka.org/add-ons/json/s_theme.json   (for themes)
```

The API response is cached in memory for the duration of the run (using `@lru_cache`), so multiple catalog extensions only trigger one HTTP request per group.

`omeka-s-cli` is functionally identical to `catalog` — it uses the same API. The type name reflects that this is the same backend used by Libnamic's [omeka-s-cli](https://github.com/libnamic/omeka-s-cli) tool.

**`git`**

Clones the repository with `--no-checkout`, then checks out the exact ref. The destination directory must not exist beforehand (it is removed if it does).

```bash
git clone --no-checkout <repo> build-context/modules/<Name>
git -C build-context/modules/<Name> checkout --force <ref>
```

**`release_zip`**

Constructs the release asset URL from `repo`, `version`, and `asset`, then downloads and extracts the ZIP.

URL patterns:
- GitHub: `<repo>/releases/download/<version>/<asset>`
- GitLab: `<repo>/-/releases/<version>/downloads/<asset>`

After extraction, if the ZIP contains a single top-level directory (common in GitHub releases), its contents are moved up one level so the final layout is always `build-context/<group>/<Name>/<files>` with no extra nesting.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All extensions fetched successfully |
| `1` | Any fetch operation failed (network error, bad URL, version not found, etc.) |

---

## `write_build_env.py`

Reads image coordinates from the manifest and GitLab CI environment variables, then writes a dotenv file consumed by the `build_image` CI job.

### Usage

```bash
python tools/write_build_env.py <manifest.yml>
```

### Example

```bash
python tools/write_build_env.py manifest.yml
# Wrote .ci/build.env
```

### Output

Writes `.ci/build.env` with plain `KEY=value` lines (no shell quoting). GitLab reads this file directly via `artifacts:reports:dotenv` — it is not sourced by a shell.

```
BASE_IMAGE=registry.gitlab.com/practicas_libnamic/omeka-s-base
BASE_TAG=4.1.1-php8.2-bookworm-2026.02
TARGET_IMAGE=registry.gitlab.com/practicas_libnamic/.../omeka-proyecto:ac4cb44
BUILD_DATE=2026-03-10T10:09:38Z
VCS_REF=ac4cb44f1e0a0f3...
```

### Variables written

| Variable | Source |
|---|---|
| `BASE_IMAGE` | `base.image` from manifest |
| `BASE_TAG` | `base.tag` from manifest |
| `TARGET_IMAGE` | `project.image.name` from manifest + computed tag |
| `BUILD_DATE` | Current UTC time (ISO 8601) |
| `VCS_REF` | `CI_COMMIT_SHA` environment variable, or `"unknown"` |

### Image tag priority

The tag appended to `TARGET_IMAGE` is resolved in this order:

1. `CI_COMMIT_TAG` — set by GitLab when the push is a git tag (e.g. `v1.2.0`)
2. `CI_COMMIT_SHORT_SHA` — set on every GitLab push (e.g. `ac4cb44`)
3. `"dev"` — fallback for local runs outside CI

### Exit codes

| Code | Meaning |
|---|---|
| `0` | File written successfully |
| `1` | Manifest not found, parse error, or required field missing |
| `2` | Wrong number of arguments |

---

## `utility.py`

Shared helpers used by all three tools. Not a CLI — imported as a module.

| Function | Used by | Description |
|---|---|---|
| `load_yaml(path)` | validate, fetch, write_build_env | Loads a YAML file and asserts the root is a dict |
| `get_path(doc, keys)` | validate, fetch, write_build_env | Safely traverses nested dicts; returns `(exists, value)` |
| `path_str(path)` | validate | Renders a key tuple as a dotted string (e.g. `"base.tag"`) |
| `run(cmd)` | fetch | Runs a subprocess and raises on non-zero exit |
| `ensure_clean_dir(dest)` | fetch | Removes and recreates a directory |
| `remove_path_if_exists(dest)` | fetch | Removes a file or directory if it exists |
| `download_and_extract_zip(url, dest)` | fetch | Downloads a ZIP, extracts it, normalizes single-root layout |
| `flatten_single_top_level_dir(dest)` | fetch | Moves contents up if the ZIP had one root folder |
| `build_release_zip_url(repo, version, asset)` | fetch | Constructs GitHub/GitLab release asset URL |
| `resolve_release_zip_url(src, name)` | fetch | Validates and delegates to `build_release_zip_url` |
| `resolve_catalog_zip_url(group, name, version)` | fetch | Queries Omeka catalog API and returns the download URL |
| `resolve_omeka_s_cli_zip_url(group, name, version)` | fetch | Alias for `resolve_catalog_zip_url` |

---

## `manifest_rules.py`

Pure data module — contains only constants, no logic. Imported by `validate_manifest.py`.

| Constant | Contents |
|---|---|
| `REQUIRED_PATHS` | List of key-path tuples that must exist in the manifest |
| `EXACT_VALUES` | Dict of path → expected value (for `apiVersion` and `kind`) |
| `EXPECTED_TYPES` | Dict of path → Python type (e.g. `("extensions", "modules"): list`) |
| `LIST_ITEM_REQUIRED` | Required keys inside each module/theme item |
| `LIST_ELEMENT_TYPES` | Expected type for elements of known lists |
| `SUPPORTED_SOURCE_TYPES` | Set of valid `source.type` values |
| `SOURCE_TYPE_REQUIRED` | Required fields per source type |
| `SOURCE_TYPE_REQUIRED_TYPES` | Expected types for those required fields |
