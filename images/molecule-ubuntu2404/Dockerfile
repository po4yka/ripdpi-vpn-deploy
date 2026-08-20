FROM geerlingguy/docker-ubuntu2404-ansible@sha256:8f71d6ef6617ce600a0c9f210a21bff095ef9cf2b7c5ac437f838e697ad5bbe5

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
