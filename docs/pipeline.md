# CI/CD Pipeline

The pipeline is defined in [`.gitlab-ci.yml`](../.gitlab-ci.yml) and runs automatically on every push. It has four stages: **prepare**, **build**, **test**, and **publish**.

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
│  3. docker save │
└────────┬────────┘
         │ artifacts:
         │   paths: .ci/image.tar
         ▼
┌─────────────────┐
│   smoke_test    │  stage: test
│                 │  image: docker:27.5.1 + dind
│  1. docker load │
│  2. php -v      │
│  3. ls modules  │
│  4. ls themes   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  publish_image  │  stage: publish
│                 │  image: docker:27.5.1 + dind
│  1. docker load │
│  2. docker push │
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
3. `docker save "$TARGET_IMAGE" -o .ci/image.tar` — exports the image as a tar artifact so downstream stages can use it without a registry.

The image is **not pushed** in this stage. It is passed to the next stages via artifact.

---

## Stage 3 — `smoke_test`

Loads the image from the tar artifact and checks:

1. `docker load -i .ci/image.tar` — loads the image locally.
2. `php -v` — PHP runtime works inside the image.
3. For each module in `build-context/modules/*/`, runs `ls` inside the container to confirm it exists at `/var/www/html/modules/<n>`.
4. Same for themes at `/var/www/html/themes/<n>`.

Module and theme names are resolved dynamically from the `build-context/` artifact. If any check fails, the pipeline stops and the image is never published.

---

## Stage 4 — `publish_image`

Loads the image from the tar artifact and pushes it:

1. `docker load -i .ci/image.tar`
2. `docker push "$TARGET_IMAGE"` to the GitLab Container Registry.

This stage only runs if `smoke_test` passed, so no untested image reaches the registry.

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
