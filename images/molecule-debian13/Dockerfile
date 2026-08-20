# The source image is immutable. Security upgrades are applied during each
# owned-image refresh; the resulting GHCR digest is the only image Molecule uses.
FROM geerlingguy/docker-debian13-ansible@sha256:cddf7cf7310a35fd4833b4fb278704a3d1216a2a92f8d869909cf935bcfe87cb

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
