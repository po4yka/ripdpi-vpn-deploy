FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ENV DEBIAN_FRONTEND=noninteractive container=docker
COPY tests/integration/awg_source_candidate/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources
ADD --checksum=sha256:641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a \
    https://snapshot.ubuntu.com/ubuntu/20261015T000000Z/pool/main/c/ca-certificates/ca-certificates_20240203_all.deb /tmp/bootstrap-ca.deb
RUN dpkg-deb -x /tmp/bootstrap-ca.deb /tmp/bootstrap-ca \
    && mkdir -p /etc/ssl/certs \
    && cat /tmp/bootstrap-ca/usr/share/ca-certificates/mozilla/*.crt > /etc/ssl/certs/ca-certificates.crt \
    && apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv ca-certificates curl git make gcc libc6-dev libmnl-dev \
    iproute2 iptables python3 tcpdump procps \
    && rm -rf /var/lib/apt/lists/* /tmp/bootstrap-ca /tmp/bootstrap-ca.deb
COPY tests/integration/awg_source_candidate/sources.json /lab/sources.json
COPY tests/integration/awg_source_candidate/build.py /lab/build.py
COPY sources/ /sources/
RUN python3 /lab/build.py
COPY ansible/roles/runtime-release/files/runtime_build_receipt.py /lab/runtime_build_receipt.py
COPY ansible/roles/amneziawg/templates/awg-quick@.service.j2 /lab/awg-quick@.service
COPY tests/integration/awg_source_candidate/acceptance.py /lab/acceptance.py
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
