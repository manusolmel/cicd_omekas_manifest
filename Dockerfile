ARG BASE_IMAGE
ARG BASE_TAG

FROM ${BASE_IMAGE}:${BASE_TAG}

ARG BUILD_DATE
ARG VCS_REF

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

COPY build-context/modules/ /var/www/html/modules/
COPY build-context/themes/  /var/www/html/themes/
