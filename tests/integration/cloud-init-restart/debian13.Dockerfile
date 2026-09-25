FROM ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13@sha256:c3474ef1c942fd947b0efe59f7d84067966cdd27580cd8b68a54afefac0170c8

SHELL ["/bin/sh", "-euxc"]

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        cloud-init \
        openssh-server \
        python3 \
    && for unit in \
        cloud-init-local.service \
        cloud-init-network.service \
        cloud-init.service \
        cloud-config.service \
        cloud-final.service \
        cloud-init.target; do \
          if test -e "/lib/systemd/system/${unit}"; then \
            systemctl enable "${unit}"; \
          fi; \
       done \
    && cloud-init clean --logs --machine-id \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/lib/cloud/instances/*

STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
