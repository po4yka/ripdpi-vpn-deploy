FROM ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13@sha256:3eaa352852855158e752c94f2ea9b47aa03ba014d5ea3e51c06e74c45a57ad08

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
