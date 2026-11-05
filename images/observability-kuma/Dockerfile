FROM --platform=$BUILDPLATFORM golang:1.27.3-bookworm@sha256:d9b6a1beb9474adc2a1ce842573639b44b2a0dd49b6669f51d3821baf9ec37c9 AS healthcheck
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY healthcheck.go ./
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -p 4 -trimpath -ldflags="-s -w" -o /healthcheck healthcheck.go

FROM louislam/uptime-kuma:2.5.9-slim-rootless@sha256:053a48927ee714b1da78c6810041a44a266bd8c06dc30ead5b3f459d0f219fb0
USER root
WORKDIR /app
COPY package.json package-lock.json ./
# Keep the exact upstream SQLite native module for the unchanged package version.
RUN cp -a node_modules/@louislam/sqlite3/lib/binding /tmp/sqlite3-binding \
    && npm ci --omit=dev --omit=optional --ignore-scripts --no-audit --no-fund \
    && rm -rf node_modules/@louislam/sqlite3/lib/binding \
    && mv /tmp/sqlite3-binding node_modules/@louislam/sqlite3/lib/binding \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
       apt=2.6.2 \
       libapt-pkg6.0=2.6.2 \
       libbrotli1=1.0.9-2+deb12u1 \
       libssl3=3.0.22-1~deb12u2 \
       openssl=3.0.22-1~deb12u2 \
    && apt-get purge -y apprise python3 python3.11 libpython3-stdlib libpython3.11-stdlib python3-jwt sqlite3 libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/* /root/.npm \
       /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
       /usr/bin/cloudflared
COPY --from=healthcheck /healthcheck /app/extra/healthcheck
USER 1000:1000
