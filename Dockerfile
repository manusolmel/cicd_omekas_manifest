# syntax=docker/dockerfile:1.7

# ARGs declared before FROM are only in scope for the FROM instruction.
# They must be supplied by the CI pipeline (see write_build_env.py → build_image job).
ARG BASE_IMAGE
ARG BASE_TAG

# Start from the Omeka S base image (core + PHP runtime).
FROM ${BASE_IMAGE}:${BASE_TAG}

# ARGs used after FROM must be re-declared; the pre-FROM scope does not carry over.
ARG BUILD_DATE
ARG VCS_REF

# OCI traceability labels — record when and from which commit this image was built.
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

# Copy extensions fetched by tools/fetch.py.
# Expected layout in build-context/:
#   modules/<ModuleName>/
#   themes/<ThemeName>/
COPY build-context/modules/ /var/www/html/modules/
COPY build-context/themes/  /var/www/html/themes/
