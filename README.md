# CI/CD Pipeline for Omeka S

[![pipeline status](https://gitlab.com/manusolmel/cicd_omekas_manifest/badges/main/pipeline.svg)](https://gitlab.com/manusolmel/cicd_omekas_manifest/-/pipelines)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-27.5-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![GitLab CI](https://img.shields.io/badge/GitLab-CI%2FCD-FC6D26?style=flat-square&logo=gitlab&logoColor=white)](https://docs.gitlab.com/ee/ci/)
[![OCI](https://img.shields.io/badge/OCI-image%20spec-0db7ed?style=flat-square&logo=opencontainers&logoColor=white)](https://specs.opencontainers.org/image-spec/)
[![YAML](https://img.shields.io/badge/manifest-YAML-CB171E?style=flat-square&logo=yaml&logoColor=white)]()

Reproducible CI/CD pipeline that builds **Omeka S** container images from declarative YAML manifests.

Given a `manifest.yml`, the pipeline validates it, fetches all declared modules and themes, builds a Docker image on top of a configurable base, runs smoke tests, and pushes to the GitLab Container Registry, automated on every push.

> Full implementation specification: [`spec.md`](spec.md)

---

## How it works

```
manifest.yml
      │
      ▼
┌──────────────────────────────────────────────────┐
│  prepare_context                  stage: prepare   │
│                                                    │
│  1. validate   tools/validate_manifest.py          │
│  2. fetch      tools/fetch.py                      │
│                └── build-context/{modules,themes}  │
│  3. write_env  tools/write_build_env.py            │
│                └── .ci/build.env                   │
└───────────────────────┬──────────────────────────┘
                        │ artifacts: build-context/ + .ci/build.env
                        ▼
┌──────────────────────────────────────────────────┐
│  build_image                        stage: build  │
│                                                   │
│  1. inspect    docker manifest inspect base:tag   │
│  2. build      docker build --pull …              │
│  3. save       docker save → .ci/image.tar        │
└───────────────────────┬──────────────────────────┘
                        │ artifacts: .ci/image.tar
                        ▼
┌──────────────────────────────────────────────────┐
│  smoke_test                          stage: test  │
│                                                   │
│  1. load       docker load -i .ci/image.tar       │
│  2. php -v     confirms PHP runtime               │
│  3. ls …       confirms each module/theme copied  │
└───────────────────────┬──────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│  publish_image                   stage: publish   │
│                                                   │
│  1. load       docker load -i .ci/image.tar       │
│  2. push       docker push $TARGET_IMAGE          │
└───────────────────────┬──────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│  deploy_k8s                       stage: deploy   │
│                                                   │
│  1. config     build kubeconfig from CI variables │
│  2. set image  kubectl set image deployment/omeka │
│  3. wait       kubectl rollout status             │
└──────────────────────────────────────────────────┘
```

The pipeline runs automatically on every push via `.gitlab-ci.yml`.
`deploy_k8s` runs on `main` and `feature/k8s-deploy`.

---

## Quick start (local)

**Requirements:** Python 3.12+, `pip install pyyaml`, `git`, Docker 

```bash
# 1. Validate the manifest
python tools/validate_manifest.py manifest.yml

# 2. Fetch all extensions → build-context/
python tools/fetch.py

# 3. Generate build variables → .ci/build.env
python tools/write_build_env.py manifest.yml

# 4. Build the image locally (optional)
source .ci/build.env
docker build \
  --file Dockerfile \
  --tag "$TARGET_IMAGE" \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --build-arg BASE_TAG="$BASE_TAG" \
  --build-arg BUILD_DATE="$BUILD_DATE" \
  --build-arg VCS_REF="$VCS_REF" \
  .
```

>Use manifests in `manifest_test/` for testing.

---

## Manifest

The manifest is the single source of truth for each project image:

```yaml
apiVersion: "libnamic.omk/v1"
kind: "OmekaSProject"

project:
  name: "archivo-municipal"
  description: "Instancia Omeka S para Archivo Municipal"
  image:
    name: "registry.gitlab.com/<namespace>/<repo>/<image-name>"

base:
  image: "registry.gitlab.com/<namespace>/omeka-s-base"
  tag: "4.1.1-php8.2-bookworm-2026.02"

extensions:
  modules:
    - name: "Mapping"
      source:
        type: "catalog"
        version: "2.2.0"
    - name: "CSVImport"
      source:
        type: "git"
        repo: "https://github.com/omeka-s-modules/CSVImport.git"
        ref: "v2.6.2"
  themes:
    - name: "Default"
      source:
        type: "catalog"
        version: "1.9.2"
```

Each extension declares a `source.type` that tells the pipeline how to fetch it:

| Source type | Required fields | How it works |
|---|---|---|
| `catalog` | `version` | Resolves the download URL from the [official Omeka add-ons API](https://omeka.org/add-ons/) |
| `git` | `repo`, `ref` | Clones the repo and checks out the exact ref (tag or commit SHA) |
| `release_zip` | `repo`, `version`, `asset` | Downloads a ZIP asset from a GitHub/GitLab release page |
| `omeka-s-cli` | `version` | Same as `catalog` — uses the same official API backend |

See `sample_manifest.yml` for a template with all source types.

---

## Project structure

```
.
├── manifest.yml                  # Active manifest (read by the pipeline)
├── sample_manifest.yml           # Reference template with placeholders
├── Dockerfile                    # Project image definition
├── .gitlab-ci.yml                # Pipeline: prepare → build → test → publish → deploy
│
├── tools/
│   ├── validate_manifest.py      # CLI: validates manifest schema
│   ├── fetch.py                  # CLI: downloads extensions to build-context/
│   ├── write_build_env.py        # CLI: writes build variables to .ci/build.env
│   ├── manifest_rules.py         # Data: validation rules (no logic)
│   └── utility.py                # Shared helpers for all tools
|
├── manifest_test/                # Collection of YAML manifests for testing scenarios
│   
├── k8s/                          # Kubernetes deployment manifests
│   ├── 00-namespace.yml          # Namespace `omeka`
│   ├── 01-mariadb-secret.yml     # MariaDB credentials Secret
│   ├── 02-database-ini-configmap.yml  # Omeka database.ini ConfigMap
│   ├── 03-mariadb.yml            # MariaDB PVC + Deployment + Service
│   ├── 04-omeka.yml              # Omeka PVC + Deployment + Service
│   ├── 05-ingress.yml            # Ingress for public access
│   └── 06-gitlab-deployer-rbac.yml # ServiceAccount + RBAC for CI deploy job
|
|
└── docs/
    ├── pipeline.md               # CI/CD pipeline reference
    └── tools.md                  # CLI tools reference
```

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/pipeline.md`](docs/pipeline.md) | CI/CD stages, jobs, artifact flow, image tagging |
| [`docs/tools.md`](docs/tools.md) | CLI reference for all Python tools |
| [`spec.md`](spec.md) | Full implementation specification |

---
