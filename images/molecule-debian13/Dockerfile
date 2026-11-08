# The source image is immutable. Security upgrades are applied during each
# owned-image refresh; the resulting GHCR digest is the only image Molecule uses.
FROM geerlingguy/docker-debian13-ansible@sha256:38d514c83f9c276260ce1a55b39a3c21f1b2e7887e028cb3b590b87345fea133

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    && apt-get clean
