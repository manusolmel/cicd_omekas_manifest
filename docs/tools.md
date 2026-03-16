# Tools reference

All tools live in `tools/` and must be run from the **repository root**.

---

## `validate_manifest.py`

Validates the manifest schema before any fetch or build step.

```bash
python tools/validate_manifest.py manifest.yml
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Manifest is valid |
| `1` | Validation errors found, or file not found / parse error |
| `2` | Wrong number of arguments |

### What it checks

The validator runs seven passes and collects **all errors** before printing.

| Pass | What it checks |
|---|---|
| Required fields | All required paths exist (e.g. `base.tag`, `project.image.name`) |
| Exact values | `apiVersion` and `kind` match the spec |
| Types | Field types are correct (e.g. `extensions.modules` is a list) |
| List item structure | Each module/theme has `name`, `source`, and `source.type` |
| List element types | Elements inside known lists have the correct type |
| Source types | `source.type` is supported; required fields for that type are present |
| Registry namespace (CI only) | In CI, `project.image.name` must match `CI_PROJECT_NAMESPACE` (or use an explicit Deploy Token) |

Most validation rules are declared as pure data in `manifest_rules.py`.

---

## `fetch.py`

Downloads all modules and themes declared in `manifest.yml` into `build-context/`.

```bash
python tools/fetch.py
```

No arguments. Always reads `manifest.yml` from the current directory.

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

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All extensions fetched successfully |
| `1` | Any fetch operation failed |

---

## `write_build_env.py`

Reads image coordinates from the manifest and CI environment variables, then writes a dotenv file for the build job.

```bash
python tools/write_build_env.py manifest.yml
```

Writes `.ci/build.env`. See [pipeline.md](pipeline.md#image-tagging) for the variables and tagging logic.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | File written successfully |
| `1` | Manifest not found, parse error, or required field missing |
| `2` | Wrong number of arguments |
