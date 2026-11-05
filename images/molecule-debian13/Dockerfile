# The source image is immutable. Security upgrades are applied during each
# owned-image refresh; the resulting GHCR digest is the only image Molecule uses.
FROM geerlingguy/docker-debian13-ansible@sha256:3331d8a03388f2fc6f49bee503cc3fc8d5ad6a48caf859324d958cc5b677b359

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    && apt-get clean
