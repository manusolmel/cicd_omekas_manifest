# CI/CD Pipeline

The pipeline is defined in [`.gitlab-ci.yml`](../.gitlab-ci.yml) and runs automatically on every push. It has three stages: **prepare**, **build**, and **test**.

```
push to GitLab
      │
      ▼
┌─────────────────┐
│  prepare_context │  stage: prepare
│                 │  image: python:3.12-alpine
│  1. validate    │
│  2. fetch       │
│  3. write_env   │
└────────┬────────┘
         │ artifacts:
         │   paths: build-context/
         │   dotenv: .ci/build.env
         ▼
┌─────────────────┐
│   build_image   │  stage: build
│                 │  image: docker:27.5.1 + dind
│  1. inspect     │
│  2. docker build│
│  3. docker push │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   smoke_test    │  stage: test
│                 │  image: docker:27.5.1 + dind
│  1. docker pull │
│  2. php -v      │
│  3. ls modules  │
│  4. ls themes   │
└─────────────────┘
```

---

## Stage 1 — `prepare_context`

Installs `git` and `pyyaml`, then runs the three Python tools in sequence:

```bash
python tools/validate_manifest.py manifest.yml
python tools/fetch.py
python tools/write_build_env.py manifest.yml
```

### Artifacts

| Artifact | Type | Contents |
|---|---|---|
| `build-context/` | path | Downloaded modules and themes |
| `.ci/build.env` | dotenv | `BASE_IMAGE`, `BASE_TAG`, `TARGET_IMAGE`, `BUILD_DATE`, `VCS_REF` |

`.ci/build.env` is declared as a `dotenv` artifact, so its variables are available in downstream jobs automatically.

---

## Stage 2 — `build_image`

Uses Docker-in-Docker (dind) without TLS.

1. `docker manifest inspect "$BASE_IMAGE:$BASE_TAG"` — verifies the base image exists before building.
2. `docker build --pull` with the variables from the dotenv artifact.
3. `docker push "$TARGET_IMAGE"` to the GitLab Container Registry.

---

## Stage 3 — `smoke_test`

Pulls the image pushed by `build_image` and checks:

1. `php -v` — PHP runtime works inside the image.
2. For each module in `build-context/modules/*/`, runs `ls` inside the container to confirm it exists at `/var/www/html/modules/<name>`.
3. Same for themes at `/var/www/html/themes/<name>`.

Module and theme names are resolved dynamically from the `build-context/` artifact.

---

## Image tagging

The tag appended to `TARGET_IMAGE` is resolved by `write_build_env.py`:

| Priority | Source | Example |
|---|---|---|
| 1 | `CI_COMMIT_TAG` | `v1.2.0` (only on git tags) |
| 2 | `CI_COMMIT_SHORT_SHA` | `ac4cb44` (every push) |
| 3 | fallback | `dev` (local builds) |

After a successful pipeline, the image is available at:

```
registry.gitlab.com/<namespace>/<repo>/<image-name>:<tag>
```
