# The pinned cross-engine test image: Spark + Delta (the "another engine" of
# article 2) plus the external delta-rs writer under test. Jars are fetched
# and checksummed at build time so the test run itself is offline and
# deterministic -- no `--packages` download at runtime.
FROM apache/spark:4.2.0-python3@sha256:fc64959c04bd87b0ac686be9aaa9008b69cdb1afc695400528279c8b01f43d89

ARG DELTALAKE_VERSION=1.6.3
ARG DELTA_SPARK_VERSION=4.4.0

USER root

RUN set -eux; \
    cd /opt/spark/jars; \
    curl -fsSLO "https://repo1.maven.org/maven2/io/delta/delta-spark_2.13/${DELTA_SPARK_VERSION}/delta-spark_2.13-${DELTA_SPARK_VERSION}.jar"; \
    curl -fsSLO "https://repo1.maven.org/maven2/io/delta/delta-storage/${DELTA_SPARK_VERSION}/delta-storage-${DELTA_SPARK_VERSION}.jar"; \
    echo "c2ab26421b8de44a2161b5e0b7da7954049f1ca1  delta-spark_2.13-${DELTA_SPARK_VERSION}.jar" | sha1sum -c -; \
    echo "a068e489ce20d7f79bc4ca2d3392f12adbb69ddd  delta-storage-${DELTA_SPARK_VERSION}.jar" | sha1sum -c -

RUN pip install --no-cache-dir \
    "pyspark==4.2.0" \
    "delta-spark==${DELTA_SPARK_VERSION}" \
    "deltalake==${DELTALAKE_VERSION}" \
    "pyarrow==25.0.1" \
    "pytest==9.1.1"

ENV COMPAT_DELTALAKE_VERSION=${DELTALAKE_VERSION} \
    COMPAT_DELTA_SPARK_VERSION=${DELTA_SPARK_VERSION} \
    PYSPARK_PYTHON=python3

RUN mkdir -p /work && chown 185:185 /work

USER 185
WORKDIR /src
