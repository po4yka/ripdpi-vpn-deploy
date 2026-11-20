FROM ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404@sha256:4f260aba1e82b795e58e515edf52c1f97fb3aceb3a90bcc251c3b7449aebd06a

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
