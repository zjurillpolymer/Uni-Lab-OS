# Build only the standalone product manual; the runtime image is not modified.
FROM python:3.11-slim AS builder

WORKDIR /src
ENV CONDA_PREFIX=/usr/local
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
    "sphinx>=7,<9" \
    "sphinx-rtd-theme>=2" \
    "myst-parser>=2" \
    sphinxcontrib-mermaid

RUN pip install --no-cache-dir "furo>=2024.8.6"

COPY docs/product_manual /src/manual

RUN sphinx-build -W --keep-going -b html \
    -d /tmp/unilabos-manual-doctrees \
    /src/manual /tmp/unilabos-manual-html

FROM nginx:1.27-alpine

COPY deploy/product-manual/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder --chown=101:101 /tmp/unilabos-manual-html /usr/share/nginx/html

USER 101:101
EXPOSE 8080
