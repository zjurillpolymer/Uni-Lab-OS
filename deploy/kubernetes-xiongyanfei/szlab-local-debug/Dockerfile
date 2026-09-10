ARG BASE_IMAGE=tangshaodong/uni-lab-os-szlab:40bd6065-0098f5a-real-connection-status-20260815
ARG OTEL_RUNTIME_IMAGE=uni-lab-demo-edge:trace-20260802-2@sha256:3859d094f74c4cfbf8e38792c8cbb2c5be9a250b09a5c0edcc0d88f8d787fc5f
FROM ${OTEL_RUNTIME_IMAGE} AS otel-runtime
FROM ${BASE_IMAGE}

ARG OS_REVISION=unknown
ARG SZLAB_REVISION=unknown
LABEL io.unilabos.commit=${OS_REVISION} \
      io.unilabos.szlab.commit=${SZLAB_REVISION} \
      io.unilabos.runtime-mode=local-debug

USER root

# 两个固定源码树使用全新目录并通过 PYTHONPATH 优先导入，避免在基础镜像旧目录
# 上做合并 COPY 后残留已从新提交删除的文件。
COPY unilabos /opt/runtime-src/os/unilabos
COPY --from=szlab package.yaml pyproject.toml /opt/runtime-src/szlab/
COPY --from=szlab szlab_poly_studio /opt/runtime-src/szlab/szlab_poly_studio
COPY --from=szlab deployment /opt/runtime-src/szlab/deployment

# 节点上的已验证 Trace 镜像与本镜像使用同一 Python 3.11 运行时；复用其
# OTel wheel 产物，避免部署构建依赖不稳定的外部 Python 镜像源。
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/opentelemetry /opt/conda/lib/python3.11/site-packages/opentelemetry
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/opentelemetry_*.dist-info /opt/conda/lib/python3.11/site-packages/
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/google /opt/conda/lib/python3.11/site-packages/google
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/googleapis_common_protos-*.dist-info /opt/conda/lib/python3.11/site-packages/
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/grpc /opt/conda/lib/python3.11/site-packages/grpc
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/grpcio-*.dist-info /opt/conda/lib/python3.11/site-packages/
COPY --from=otel-runtime /opt/conda/lib/python3.11/site-packages/protobuf-*.dist-info /opt/conda/lib/python3.11/site-packages/

RUN ( /opt/conda/bin/python -c 'import multipart' \
      || /opt/conda/bin/pip install --no-cache-dir 'python-multipart>=0.0.9,<1' ) \
    && chown -R 57439:57439 /opt/runtime-src

ENV MAMBA_SKIP_ACTIVATE=1 \
    PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPATH=/opt/runtime-src/os:/opt/runtime-src/szlab

USER 57439:57439
WORKDIR /opt/runtime-src/szlab
