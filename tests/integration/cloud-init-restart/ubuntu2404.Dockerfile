FROM ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404@sha256:c9277039a651a9a211ab0d1676c7001c78cf95a5ea83d46e1542c386cfe6f040

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
