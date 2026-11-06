FROM geerlingguy/docker-ubuntu2404-ansible@sha256:29e6f9d736c3401815d98f626a41c55a54a4ef1edb9d1d1223018746d3acba14

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    && apt-get clean
