#!/bin/sh
# Synthetic local source repositories for the role's real git/make/install path.
# Never install role outputs here; no upstream source or working AWG is claimed.
set -eu
fixture=/opt/molecule-awg-fixture
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_ALLOW_PROTOCOL=file
export GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z
umask 077
mkdir -p "$fixture/amneziawg-go" "$fixture/amneziawg-tools/src"

cat > "$fixture/amneziawg-go/Makefile" <<'EOF'
.PHONY: all
all: amneziawg-go
amneziawg-go: fixture-go
	install -m 0755 fixture-go amneziawg-go
EOF
cat > "$fixture/amneziawg-go/fixture-go" <<'EOF'
#!/bin/sh
printf 'synthetic AmneziaWG Go fixture; no tunnel\n'
EOF
cat > "$fixture/amneziawg-tools/src/Makefile" <<'EOF'
.PHONY: all install
all: wg
wg: fixture-wg
	install -m 0755 fixture-wg wg
install: wg
	install -m 0755 wg /usr/bin/awg
	install -m 0755 fixture-awg-quick /usr/bin/awg-quick
EOF
cat > "$fixture/amneziawg-tools/src/fixture-wg" <<'EOF'
#!/bin/sh
printf 'synthetic AmneziaWG tools fixture; no tunnel\n'
EOF
cat > "$fixture/amneziawg-tools/src/fixture-awg-quick" <<'EOF'
#!/bin/sh
# The real systemd unit calls this no-TUN fixture, which records only lifecycle.
set -eu
[ "$#" -eq 2 ] && [ "$2" = awg0 ] || exit 2
case "$1" in
  up|down)
    test -f /etc/amneziawg/awg0.conf
    printf '%s %s\n' "$1" "$2" >> /run/molecule-awg-quick.events
    ;;
  strip) printf '[Interface]\n' ;;
  *) exit 2 ;;
esac
EOF
for repository in amneziawg-go amneziawg-tools; do
  git -C "$fixture/$repository" init --initial-branch=fixture
  git -C "$fixture/$repository" add .
  git -C "$fixture/$repository" -c user.name='Molecule source fixture' \
    -c user.email=fixture@example.invalid -c commit.gpgsign=false \
    commit -m 'Synthetic source inputs, not an upstream AWG build'
  git -C "$fixture/$repository" tag molecule-fixture-v1
done
