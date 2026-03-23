# CI/CD Pipeline

The pipeline is defined in [`.gitlab-ci.yml`](../.gitlab-ci.yml) and runs automatically on every push. It has five stages: **prepare**, **build**, **test**, **publish** and **deploy**.

```
push to GitLab
      │
      ▼
┌─────────────────┐
│  prepare_context│  stage: prepare
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
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   deploy_k8s    │  stage: deploy
│                 │  image: bitnami/kubectl:latest
│  1. set-cluster │
│  2. set image   │
│  3. wait rollout│
└─────────────────┘
```

---
## Runner configuration

All jobs run on a self-hosted GitLab Runner deployed inside the Kubernetes cluster (namespace `gitlab-runner`, tag `k8s`). This is enforced with `default: tags: [k8s]` in the pipeline configuration.

The self-hosted runner is required because the deploy stage needs network access to the Kubernetes API server (`https://192.168.1.50:6443`), which is not reachable from GitLab.com shared runners.

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
| `.ci/build.env` | dotenv | `BASE_IMAGE`, `BASE_TAG`, `BASE_DIGEST`, `TARGET_IMAGE`, `BUILD_DATE`, `VCS_REF` |

`.ci/build.env` is declared as a `dotenv` artifact, so its variables are available in downstream jobs automatically.

---

## Stage 2 — `build_image`

Uses Docker-in-Docker (dind) without TLS.

1. Resolves the digest of `"$BASE_IMAGE:$BASE_TAG"` and verifies it matches `BASE_DIGEST`.
2. `docker manifest inspect "$BASE_IMAGE@$BASE_DIGEST"` — verifies the pinned base image reference exists.
3. `docker build --pull` with the variables from the dotenv artifact (including `BASE_DIGEST`).
4. `docker save "$TARGET_IMAGE" -o .ci/image.tar` — exports the image as a tar artifact so downstream stages can use it without a registry.

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
## Stage 5 — `deploy_k8s` 

Updates the kubernetes Deployment with the newly published image. This job is manual and only runs on `main`.

### Kubernetes manifests in this repo

The `k8s/` folder contains the cluster resources used by this pipeline:

| File | Purpose |
|---|---|
| `k8s/00-namespace.yml` | Creates namespace `omeka` |
| `k8s/01-mariadb-secret.yml` | MariaDB credentials Secret |
| `k8s/02-database-ini-configmap.yml` | Omeka `database.ini` ConfigMap |
| `k8s/03-mariadb.yml` | MariaDB PVC + Deployment + Service |
| `k8s/04-omeka.yml` | Omeka PVC + Deployment + Service |
| `k8s/05-ingress.yml` | Ingress for host routing |
| `k8s/06-gitlab-deployer-rbac.yml` | ServiceAccount, token Secret, Role, RoleBinding |

### Initial cluster bootstrap

Apply manifests in order:

```bash
kubectl apply -f k8s/00-namespace.yml
kubectl apply -f k8s/01-mariadb-secret.yml
kubectl apply -f k8s/02-database-ini-configmap.yml
kubectl apply -f k8s/03-mariadb.yml
kubectl apply -f k8s/04-omeka.yml
kubectl apply -f k8s/05-ingress.yml
kubectl apply -f k8s/06-gitlab-deployer-rbac.yml
```

### Prerequisites

**In the cluster:**
- A `ServiceAccount` named `gitlab-deployer` in the `omeka` namespace
- A `Role` with permissions to get/list/patch/update Deployments and get/list Pods
- A `RoleBinding` linking the two
- A token Secret for the ServiceAccount

These are defined in `k8s/06-gitlab-deployer-rbac.yml`.

**In GitLab (Settings → CI/CD → Variables):**

| Variable | Contents | Options |
|---|---|---|
| `KUBE_TOKEN` | Token from the `gitlab-deployer-token` Secret | Masked |
| `KUBE_API_URL` | `https://192.168.1.50:6443` | - - -  |

### What it does

1. **Build kubeconfig** — the job container starts with no Kubernetes configuration. Three `kubectl config` commands construct a kubeconfig in memory: set the cluster URL (with `--insecure-skip-tls-verify`), set the credentials (bearer token), and create + activate a context.

2. **`kubectl set image deployment/omeka omeka="$TARGET_IMAGE" -n omeka`** — tells Kubernetes to update the container image in the Deployment. Kubernetes starts a rolling update: creates a new pod with the new image, waits for it to become Ready, then terminates the old pod.

3. **`kubectl rollout status deployment/omeka -n omeka --timeout=120s`** — waits up to 120 seconds for the rollout to complete. If the new pod fails to start, the command exits with an error and the pipeline is marked as failed.

The CI job updates the Deployment image and waits for rollout. It does not create the full infrastructure from scratch.

### Security model

The ServiceAccount follows the principle of least privilege: it can only read and update Deployments and Pods in the `omeka` namespace. It cannot access other namespaces, create or delete resources, or read Secrets.

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

## Registry Restriction

The variables `CI_REGISTRY_USER` and `CI_REGISTRY_PASSWORD` that GitLab automatically injects only have write permissions for the registry of the repository where the pipeline is running.

Therefore, `project.image.name` in the manifest must point to the same namespace:

`registry.gitlab.com/<your-namespace>/<repo>/<image>`

If the image needs to be pushed to a different namespace than the project
running the pipeline, a **Deploy Token** must be used.
