FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ENV DEBIAN_FRONTEND=noninteractive container=docker
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv ca-certificates curl git make gcc libc6-dev libmnl-dev \
    iproute2 iptables python3 tcpdump procps && rm -rf /var/lib/apt/lists/*
COPY contract/awg-source-candidate.json /lab/contract/awg-source-candidate.json
COPY tests/integration/awg_source_candidate/build.py /lab/build.py
COPY sources/ /sources/
RUN python3 /lab/build.py
COPY ansible/roles/runtime-release/files/runtime_build_receipt.py /lab/runtime_build_receipt.py
COPY ansible/roles/amneziawg/templates/awg-quick@.service.j2 /lab/awg-quick@.service
COPY tests/integration/awg_source_candidate/acceptance.py /lab/acceptance.py
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
