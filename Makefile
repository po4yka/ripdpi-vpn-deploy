PROVIDER ?= upcloud
ENV      ?= prod

TF_ROOT       := terraform/providers/$(PROVIDER)
TF_ENV        := ./scripts/terraform-env.sh
ANSIBLE_DIR   := ansible
RUNTIME_DIR   ?= $(if $(XDG_RUNTIME_DIR),$(XDG_RUNTIME_DIR),$(HOME)/.cache)/vpn-provision
SECRETS_FILE  ?= $(RUNTIME_DIR)/vpn-$(ENV).secrets.yaml
SOPS_FILE     ?= $(HOME)/.config/vpn-provision/$(ENV).secrets.sops.yaml
TFVARS        := $(TF_ROOT)/environments/$(ENV).tfvars
TFPLAN        := $(TF_ROOT)/$(ENV).tfplan

export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg
export PROVIDER ENV CLIENT PLAN HOST VANTAGE REALITY_TARGET_VANTAGE LIVENESS_CONFIG

.PHONY: help init validate plan apply inventory wait decrypt dry-run deploy deploy-canary verify security-verify security-audit clean \
        pre-deploy-check \
        rollback-xray rollback-config rotate-credentials check-prereqs \
        destroy backup-state burn-check diff-secrets emit-singbox emit-awg emit-bundle install-hooks \
        molecule-test smoke-test validate-target monitor-reality-target probe-sni-survival scan-targets blue-green \
        spot-check-secrets bootstrap-secrets probe-asn probe-matrix-control probe-matrix-cell probe-matrix-tools emit-probe-matrix-profile emit-qr check-certs \
        audit-permissions asn-drift check-ip-reputation issue-bootstrap \
        test-tls-policing probe-payload-throttle fleet-status drift-since-tag fleet-rotate \
        snell-refinement \
        protocol-liveness install-liveness-sentinel watch-spare promote-spare probing-summary tspu-canary \
        emit-sbom molecule-full-stack audit-log audit-log-append pyinfra-audit \
        setup-yubikey check-killswitch install-operator-crons \
        remove-operator-crons issue-sub-token sub-reads \
        test-unit snapshot-check snapshot-update validate-secrets \
        actionlint-check cloud-init-schema tf-test yamllint-check shellcheck \
        ci-fast bats-test vpnd-test vpnd-clippy vpnd-deny vpnd-msrv vpnd-mutants tf-policy \
        check

help:
	@echo "vpn-deploy Makefile"
	@echo ""
	@echo "Variables (override on command line):"
	@echo "  PROVIDER  current: $(PROVIDER)  (upcloud | hetzner | vultr)"
	@echo "  ENV       current: $(ENV)       (prod | staging)"
	@echo ""
	@echo "── DAY-1 ──────────────────────────────────────────────────────────────"
	@echo "  check-prereqs              Verify required CLI tools are installed"
	@echo "  bootstrap-secrets …        Generate full crypto + SOPS-encrypt"
	@echo "  setup-yubikey [REENCRYPT=1]  Hardware-backed age identity on YubiKey"
	@echo "  scan-targets {SEEDS=…|CIDR=…|CRAWL=…}  Discover REALITY targets (RealiTLScanner)"
	@echo "  validate-target            9-step REALITY target audit (local hygiene only)"
	@echo "  monitor-reality-target     Daily ASN/path signal from an explicit filtered VANTAGE"
	@echo "  probe-sni-survival         EXIT_IP=… bare/www SNI survival probe (run on RU vantage)"
	@echo "  probe-asn HOST=…           Team Cymru ASN lookup"
	@echo "  install-hooks              Install pre-commit hooks"
	@echo ""
	@echo "── DEPLOY LIFECYCLE ───────────────────────────────────────────────────"
	@echo "  init                       terraform init in $(TF_ROOT)"
	@echo "  validate                   fmt + validate + gitleaks + ansible-lint"
	@echo "  decrypt                    sops --decrypt → $(SECRETS_FILE)"
	@echo "  plan                       terraform plan -out=$(TFPLAN)"
	@echo "  apply                      terraform apply $(TFPLAN)"
	@echo "  inventory                  Render Ansible inventory from TF outputs"
	@echo "  wait                       Wait for cloud-init to finish"
	@echo "  pre-deploy-check           spot-check-secrets + check-certs (auto for deploy/verify; SKIP_PRECHECK=1 to bypass)"
	@echo "  dry-run                    ansible-playbook --check --diff"
	@echo "  deploy                     ansible-playbook site.yml"
	@echo "  deploy-canary              Deploy ENV=canary through the normal deploy flow"
	@echo "  verify [TAG_ON_SUCCESS=1]  ansible-playbook verify.yml (+ optional known-good git tag)"
	@echo "  security-verify            Host hardening checks (SSH/sysctl/firewall/services)"
	@echo "  smoke-test                 End-to-end traffic test through every enabled profile"
	@echo "  clean                      shred $(SECRETS_FILE)"
	@echo ""
	@echo "── ROLLBACK / RECOVERY ────────────────────────────────────────────────"
	@echo "  rollback-xray ROLLBACK_XRAY_VERSION=vX.Y.Z"
	@echo "  rollback-config            Revert Xray to .prev config"
	@echo "  rotate-credentials         Rotate per-client UUIDs / passwords / peer keys"
	@echo "  destroy                    Safe terraform destroy (double confirmation)"
	@echo "  backup-state               age-encrypt the local terraform state"
	@echo "  drift-since-tag            Diff fleet against last vpn-deploy-known-good-* tag"
	@echo "  blue-green GREEN_ENV=<name>  Orchestrate single-host blue-green"
	@echo "  fleet-rotate PLAN=…        Coordinated rotation across fleet (--dry-run / --resume)"
	@echo "  protocol-liveness LIVENESS_CONFIG=…  Pull sentinel probes and evaluate quorum"
	@echo "  install-liveness-sentinel LIVENESS_CONFIG=… SENTINEL=… CLIENT=…  Secure sentinel onboarding"
	@echo "  watch-spare                Cron: probe blue, push OTP-gated promote alert"
	@echo "  promote-spare OTP=…        Consume OTP and swing traffic to GREEN_ENV"
	@echo ""
	@echo "── CLIENT / DELIVERY ──────────────────────────────────────────────────"
	@echo "  emit-singbox CLIENT=…      Full sing-box client JSON (multi-host + cohort aware)"
	@echo "  emit-awg CLIENT=…          AmneziaWG wg-quick .conf for a named peer"
	@echo "  emit-bundle CLIENT=…       RIPDPI-extended sing-box JSON (singbox + ripdpi object)"
	@echo "  emit-qr CLIENT=…           PNG QR for the client (TYPE=singbox|uri, OUT=path)"
	@echo "  issue-bootstrap CLIENT=…   Issue a one-time /bootstrap/<token> URL"
	@echo "  issue-sub-token CLIENT=…   Issue a long-lived /sub/<token> URL (FORMAT=singbox|ripdpi EXPIRES=… QR=1)"
	@echo "  sub-reads [SINCE=… ROUTE=… LIMIT=…]  Pull the server-side read-audit log"
	@echo "  check-killswitch BUNDLE=…  Validate the kill-switch properties of a bundle"
	@echo ""
	@echo "── PRE-DEPLOY GUARDS ──────────────────────────────────────────────────"
	@echo "  spot-check-secrets         Decrypted-secrets audit (placeholders, certs, …)"
	@echo "  check-certs                SAN / expiry / self-signed / modulus match"
	@echo "  audit-permissions          Local FS: age key 0600, no stray plaintext"
	@echo "  diff-secrets               Drift: deployed config vs current secrets"
	@echo ""
	@echo "── OBSERVABILITY / DEFENSIVE ──────────────────────────────────────────"
	@echo "  burn-check                 External IP reachability probe"
	@echo "  asn-drift                  Alert on VPS ASN reassignment"
	@echo "  check-ip-reputation        Spamhaus / optional FireHOL file / AbuseIPDB"
	@echo "  probing-summary            7-day Xray/nginx/honeypot rollup"
	@echo "  tspu-canary                Daily TSPU rule-drift probes (in-cohort box)"
	@echo "  test-tls-policing HOST=…   Probe the ~12-concurrent-TLS home-ISP rule"
	@echo "  probe-payload-throttle HOST=… Probe per-ASN ~16 KiB payload throttling"
	@echo "  snell-refinement BUNDLE=… CONFIG=… VANTAGE=…  Run staged Snell refinement matrix"
	@echo "  fleet-status [HOSTS=…]     Summary table across every host:env pair"
	@echo "  install-operator-crons     Wire all of the above into crontab as a managed block"
	@echo "  remove-operator-crons      Strip the vpn-deploy cron block"
	@echo ""
	@echo "── AUDIT / SUPPLY CHAIN ───────────────────────────────────────────────"
	@echo "  audit-log                  Decrypt and print the credential-issuance log"
	@echo "  audit-log-append ACTION=…  Append a record (operator-driven hook)"
	@echo "  emit-sbom                  CycloneDX SBOM of pinned binaries → sbom/<label>.json"
	@echo "  security-audit             Non-blocking host audit report (Lynis/listeners/systemd/nft/sshd/sysctl)"
	@echo "  pyinfra-audit              Experimental read-only host audit (requires PYINFRA_HOSTS=host[,host])"
	@echo ""
	@echo "── TEST / CI ──────────────────────────────────────────────────────────"
	@echo "  test-unit                  Run pytest unit tests (tests/unit/)"
	@echo "  snapshot-check             Diff every Jinja render against tests/snapshot/golden/"
	@echo "  snapshot-update            Refresh the goldens (run after intentional change)"
	@echo "  validate-secrets           jsonschema check (strict if SECRETS_FILE is set)"
	@echo "  validate-bundle            jsonschema + fingerprint check of a ripdpi bundle (BUNDLE=… or example)"
	@echo "  actionlint-check           Validate every GitHub Actions workflow"
	@echo "  cloud-init-schema          Render shared cloud-init and run cloud-init schema"
	@echo "  tf-test                    terraform test for all provider roots"
	@echo "  yamllint-check             Lint repository YAML with the CI configuration"
	@echo "  shellcheck                 Lint every operator shell script"
	@echo "  ci-fast                    Portable CI-parity bundle (excludes Molecule and validate)"
	@echo "  bats-test                  Run bats shell tests (tests/bats/)"
	@echo "  vpnd-test                  cargo test --release --locked inside vpnd/"
	@echo "  vpnd-clippy                cargo clippy --release --locked (deny warnings) inside vpnd/"
	@echo "  vpnd-deny                  cargo-deny policy against the committed lockfile"
	@echo "  vpnd-msrv                  cargo check --locked with Rust 1.88.0"
	@echo "  tf-policy                  terraform test + conftest OPA policy check for all providers"
	@echo "  molecule-test ROLE=<name>  Run one role's molecule scenario"
	@echo "  molecule-full-stack        site.yml end-to-end inside a Docker container"

check-prereqs:
	@for tool in terraform ansible ansible-playbook ansible-lint sops age gitleaks jq ssh python3; do \
	  command -v $$tool >/dev/null 2>&1 || { echo "missing: $$tool"; exit 1; }; \
	done
	@python3 -c 'import yaml' >/dev/null 2>&1 || { echo "missing: Python module PyYAML"; exit 1; }
	@echo "all prereqs present"

init:
	PROVIDER=$(PROVIDER) ENV=$(ENV) $(TF_ENV) init

validate:
	@for provider in upcloud hetzner vultr; do \
	  terraform -chdir=terraform/providers/$$provider fmt -check -recursive; \
	  terraform -chdir=terraform/providers/$$provider validate; \
	done
	gitleaks detect --source . --redact --no-banner
	cd $(ANSIBLE_DIR) && ansible-lint
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/site.yml --syntax-check

decrypt:
	SECRETS_FILE="$(SECRETS_FILE)" SOPS_FILE="$(SOPS_FILE)" ./scripts/decrypt-secrets.sh

plan:
	@test -f "$(TFVARS)" || { echo "missing $(TFVARS) — copy from .example and fill"; exit 1; }
	PROVIDER=$(PROVIDER) ENV=$(ENV) $(TF_ENV) plan \
	  -var-file=environments/$(ENV).tfvars \
	  -out=$(ENV).tfplan

apply:
	PROVIDER=$(PROVIDER) ENV=$(ENV) $(TF_ENV) apply $(ENV).tfplan

inventory:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/render-inventory.sh

wait:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/wait-cloud-init.sh

pre-deploy-check:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	@if [ "$(SKIP_PRECHECK)" = "1" ]; then \
	  echo "pre-deploy-check: skipped (SKIP_PRECHECK=1)"; \
	else \
	  python3 ./scripts/validate-secrets.py $(SECRETS_FILE) --strict && \
	  VPN_SECRETS_FILE=$(SECRETS_FILE) python3 ./scripts/spot-check-secrets.py && \
	  VPN_SECRETS_FILE=$(SECRETS_FILE) ./scripts/check-certs.sh; \
	fi

dry-run: pre-deploy-check
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/site.yml --check --diff

deploy: pre-deploy-check
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/site.yml $(if $(strip $(ANSIBLE_TAGS)),--tags "$(ANSIBLE_TAGS)")
	@ENV=$(ENV) PROVIDER=$(PROVIDER) ./scripts/audit-log.sh append-best-effort \
	  --action site-deploy \
	  --note "playbook=site.yml warp_outbound_role=conditional"

deploy-canary:
	$(MAKE) ENV=canary deploy

verify: pre-deploy-check
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/verify.yml
	@if [ "$(TAG_ON_SUCCESS)" = "1" ]; then \
	  tag="vpn-deploy-known-good-$$(date +%Y-%m-%d-%H%M)"; \
	  git tag "$$tag" && echo "tagged: $$tag"; \
	fi

security-verify: pre-deploy-check
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/security-verify.yml

security-audit:
	VPN_SECRETS_FILE=$(SECRETS_FILE) ansible-playbook $(ANSIBLE_DIR)/playbooks/security-audit.yml

pyinfra-audit:
	@test -n "$(PYINFRA_HOSTS)" || { echo "PYINFRA_HOSTS=host[,host...] required"; exit 1; }
	@command -v pyinfra >/dev/null 2>&1 || { echo "missing: pyinfra (optional; see requirements.in and pyinfra/README.md)"; exit 1; }
	pyinfra pyinfra/inventory.py pyinfra/deploys/read_only_audit.py

clean:
	@if [ -f "$(SECRETS_FILE)" ]; then \
	  shred -u $(SECRETS_FILE) 2>/dev/null || rm -f $(SECRETS_FILE); \
	  echo "shredded $(SECRETS_FILE)"; \
	fi

rollback-xray:
	@test -n "$(ROLLBACK_XRAY_VERSION)" || { echo "ROLLBACK_XRAY_VERSION required"; exit 1; }
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ROLLBACK_XRAY_VERSION=$(ROLLBACK_XRAY_VERSION) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/rollback-xray.yml

rollback-config:
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/rollback-config.yml

rotate-credentials:
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/rotate-credentials.yml
	@ENV=$(ENV) PROVIDER=$(PROVIDER) ./scripts/audit-log.sh append-best-effort \
	  --action rotate-credentials \
	  --note "playbook=rotate-credentials.yml secrets_file=$(notdir $(SECRETS_FILE))"

DESTROY_ARGS ?=

destroy:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/destroy.sh $(DESTROY_ARGS)

backup-state:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/backup-tf-state.sh

burn-check:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/burn-check.sh

diff-secrets:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	PROVIDER=$(PROVIDER) ENV=$(ENV) SECRETS_FILE=$(SECRETS_FILE) ./scripts/diff-secrets.sh

emit-singbox:
	@test -n "$${CLIENT:-}" || { echo "CLIENT=<name> required"; exit 1; }
	./scripts/emit-singbox.sh "$${CLIENT}"

emit-awg:
	@test -n "$${CLIENT:-}" || { echo "CLIENT=<name> required"; exit 1; }
	./scripts/emit-awg.sh "$${CLIENT}"

emit-bundle:
	@test -n "$${CLIENT:-}" || { echo "CLIENT=<name> required"; exit 1; }
	./scripts/emit-bundle.sh "$${CLIENT}"

install-hooks:
	python3 -m pip install --require-hashes --no-deps -r requirements.txt
	pre-commit install
	pre-commit install --hook-type commit-msg

test-unit:
	python3 -m pytest tests/unit/ -q

snapshot-check:
	python3 scripts/render-snapshots.py

snapshot-update:
	python3 scripts/render-snapshots.py --update

validate-secrets:
	@if [ -f "$(SECRETS_FILE)" ]; then \
	  python3 scripts/validate-secrets.py $(SECRETS_FILE) --strict; \
	else \
	  python3 scripts/validate-secrets.py; \
	fi

# Validate a RIPDPI bundle's ripdpi object against contract/ripdpi-bundle.schema.json
# (the cross-repo contract with the Android client). BUNDLE=<file> to check a real
# emitted bundle; defaults to the committed contract/ripdpi-bundle.example.json.
validate-bundle:
	python3 scripts/validate-bundle.py $(BUNDLE)

actionlint-check:
	@command -v actionlint >/dev/null 2>&1 || { echo "missing: actionlint" >&2; exit 1; }
	actionlint

cloud-init-schema:
	@command -v cloud-init >/dev/null 2>&1 || { echo "missing: cloud-init" >&2; exit 1; }
	@rendered="$$(mktemp -t cloud-init.rendered.XXXXXX)"; \
	  trap 'rm -f "$$rendered"' 0; \
	  python3 scripts/render-cloud-init-ci.py > "$$rendered"; \
	  cloud-init schema --config-file "$$rendered"

tf-test:
	@command -v terraform >/dev/null 2>&1 || { echo "missing: terraform" >&2; exit 1; }
	@for provider in upcloud hetzner vultr; do \
	  echo "== terraform test: $$provider =="; \
	  terraform -chdir=terraform/providers/$$provider init -backend=false >/dev/null && \
	  terraform -chdir=terraform/providers/$$provider test || exit 1; \
	done

yamllint-check:
	@command -v yamllint >/dev/null 2>&1 || { echo "missing: yamllint" >&2; exit 1; }
	yamllint -c .yamllint.yml .

shellcheck:
	@command -v shellcheck >/dev/null 2>&1 || { echo "missing: shellcheck" >&2; exit 1; }
	shellcheck -s bash -S warning scripts/*.sh

vpnd-deny:
	@command -v cargo-deny >/dev/null 2>&1 || { echo "missing: cargo-deny" >&2; exit 1; }
	cd vpnd && cargo deny --locked check --config deny.toml

vpnd-msrv:
	@command -v cargo >/dev/null 2>&1 || { echo "missing: cargo" >&2; exit 1; }
	cd vpnd && cargo +1.88.0 check --locked

# Portable pre-PR bundle for operators. Mirrors required CI jobs that can run
# without provider credentials, GitHub services, or Molecule containers.
# `make check` adds validate (fmt, gitleaks, ansible-lint). Missing local
# tooling is a failure rather than a misleading green gate.
ci-fast:
	@$(MAKE) actionlint-check
	@$(MAKE) cloud-init-schema
	@$(MAKE) tf-test
	@$(MAKE) yamllint-check
	@$(MAKE) shellcheck
	@$(MAKE) vpnd-deny
	@$(MAKE) vpnd-msrv
	@echo "== render check =="; python3 scripts/check-templates-render.py
	@echo "== AmneziaWG arm64 version floor =="; python3 scripts/check-amneziawg-arm64-version-floor.py
	@echo "== Xray breaking-change guard =="; python3 scripts/check-xray-breaking-changes.py
	@echo "== secrets coverage =="; python3 scripts/check-secrets-coverage.py
	@echo "== deploy-profile tier guard =="; python3 scripts/check-deploy-profile.py
	@echo "== snapshot diff =="; python3 scripts/render-snapshots.py
	@echo "== schema validation =="; python3 scripts/validate-secrets.py
	@echo "== bundle contract =="; python3 scripts/validate-bundle.py
	@command -v ansible-playbook >/dev/null 2>&1 || { echo "missing: ansible-playbook" >&2; exit 1; }
	@echo "== ansible syntax =="; cd $(ANSIBLE_DIR) && ansible-playbook playbooks/site.yml --syntax-check -i 'localhost,'
	@echo "== unit tests =="; python3 -m pytest tests/unit/ -q
	@echo "== bats shell tests =="; bats tests/bats/
	@command -v cargo >/dev/null 2>&1 || { echo "missing: cargo" >&2; exit 1; }
	@echo "== vpnd clippy =="; cd vpnd && cargo clippy --release --all-targets --locked -- -D warnings
	@echo "== vpnd tests =="; cd vpnd && cargo test --release --locked
	@echo "ci-fast: OK"

# Union gate: everything in validate + everything in ci-fast.
# Run this before any commit touching Ansible, Terraform, or Python to get
# the same signal that CI produces without waiting for a remote run.
check: validate ci-fast  ## Full local gate: validate + ci-fast (superset of both)

molecule-test:
	@test -n "$(ROLE)" || { echo "ROLE=<role-name> required (e.g. baseline, firewall, xray)"; exit 1; }
	cd $(ANSIBLE_DIR)/roles/$(ROLE) && molecule test

molecule-full-stack:
	cd $(ANSIBLE_DIR) && molecule -c molecule/full-stack/molecule.yml test

smoke-test:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/smoke-test.yml

validate-target:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	SOPS_FILE=$(SOPS_FILE) ENV=$(ENV) ./scripts/validate-reality-target.sh

monitor-reality-target:
	@test -n "$(VANTAGE)" || { echo "usage: make monitor-reality-target VANTAGE=<technical-filtered-label> [ACCEPT_BASELINE=1]"; exit 1; }
	SOPS_FILE=$(SOPS_FILE) ENV=$(ENV) ./scripts/monitor-reality-target.sh \
	  $(if $(filter 1 yes true,$(ACCEPT_BASELINE)),--accept-baseline)

# Run this from the FILTERED (RU) vantage — it decides which SNI variant survives.
# EXIT_IP=<vps-ip> make probe-sni-survival   (VANTAGE defaults to "filtered")
probe-sni-survival:
	@test -n "$(EXIT_IP)" || { echo "set EXIT_IP=<vps-ip> — run this from the filtered RU vantage"; exit 1; }
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	VANTAGE="$${VANTAGE:-filtered}" ./scripts/probe-sni-survival.sh "$(EXIT_IP)" --secrets "$(SECRETS_FILE)"

bootstrap-secrets:
	@test -n "$(TARGET)$(SERVER_NAME)" || { \
	  echo "usage: make bootstrap-secrets TARGET=mirror.example.com:443 SERVER_NAME=mirror.example.com"; \
	  echo "  optional: CLIENTS=phone,laptop ENV=prod XHTTP_HOST=vpn.example.com"; \
	  exit 1; }
	./scripts/bootstrap-secrets.sh \
	  $(if $(ENV),--env $(ENV)) \
	  $(if $(CLIENTS),--clients $(CLIENTS)) \
	  --target $(TARGET) --server-name $(SERVER_NAME) \
	  $(if $(XHTTP_HOST),--xhttp-host $(XHTTP_HOST))

spot-check-secrets:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	VPN_SECRETS_FILE=$(SECRETS_FILE) python3 ./scripts/spot-check-secrets.py

probe-asn:
	@test -n "$${HOST:-}" || { echo "usage: make probe-asn HOST=mirror.example.com"; exit 1; }
	./scripts/probe-asn.sh "$${HOST}"

# Direct control probe invoked once per matrix tick.
probe-matrix-control:
	@if test -n "$(MATRIX_CONFIG)"; then python3 ./scripts/probe-matrix-driver.py control --config "$(MATRIX_CONFIG)"; else printf '%s\n' '{"verdict":"error","rtt_ms":null,"error_kind":"request-invalid"}'; fi

probe-matrix-tools:
	@mkdir -p "$(RUNTIME_DIR)/probe-matrix/bin"
	@cd tools/probe-matrix-mtproto && CGO_ENABLED=0 go build -trimpath -o "$(RUNTIME_DIR)/probe-matrix/bin/probe-matrix-mtproto" .

emit-probe-matrix-profile:
	@test -n "$(TARGET_ID)" -a -n "$(PROFILE_OUTPUT)" -a -n "$(PROFILE_VARS)" || { echo "usage: make emit-probe-matrix-profile TARGET_ID=... PROFILE_OUTPUT=... PROFILE_VARS=/absolute/host-vars.yml"; exit 1; }
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run make decrypt"; exit 1; }
	@endpoint="$$(PROVIDER="$(PROVIDER)" ENV="$(ENV)" $(TF_ENV) output -raw server_ipv4)"; \
	python3 ./scripts/emit-probe-matrix-profile.py --target-id "$(TARGET_ID)" --endpoint "$$endpoint" --vars-file "$(PROFILE_VARS)" --secrets-file "$(SECRETS_FILE)" --output "$(PROFILE_OUTPUT)"

# Per-cell probe invoked by `vpnd probe-matrix`. Emits one JSON line on stdout.
probe-matrix-cell:
	@if test -n "$(MATRIX_CONFIG)" -a -n "$(TARGET_ID)" -a -n "$(PROTOCOL)" -a -n "$(CONTROL_VERDICT)"; then MATRIX_CONFIG="$(MATRIX_CONFIG)" TARGET_ID="$(TARGET_ID)" PROTOCOL="$(PROTOCOL)" CONTROL_VERDICT="$(CONTROL_VERDICT)" ./scripts/probe-matrix-cell.sh; else printf '%s\n' '{"verdict":"error","rtt_ms":null,"error_kind":"request-invalid"}'; fi

# Per-ASN ~16 KiB payload-throttling probe. Emits one JSON verdict line
# on stdout keyed to the target ASN. Run from a filtered client path,
# NOT the VPS. See scripts/probe-payload-throttle.sh.
probe-payload-throttle:
	@test -n "$(HOST)" || { echo "usage: make probe-payload-throttle HOST=endpoint [PORT=443] [SIZES=1024,4096,8192,16384,24576,32768] [ASN=AS64500]"; exit 1; }
	@./scripts/probe-payload-throttle.sh --host $(HOST) \
	  $(if $(PORT),--port $(PORT)) \
	  $(if $(SIZES),--sizes $(SIZES)) \
	  $(if $(ASN),--asn $(ASN))

snell-refinement:
	@test -n "$(BUNDLE)" -a -n "$(CONFIG)" -a -n "$(VANTAGE)" || { echo "usage: make snell-refinement BUNDLE=sing-box.json CONFIG=snell-refinement.yaml VANTAGE=technical-id"; exit 1; }
	python3 ./scripts/snell-refinement.py --bundle "$(BUNDLE)" --config "$(CONFIG)" --vantage "$(VANTAGE)" --state-dir "$${XDG_STATE_HOME:-$${HOME}/.local/state}/vpn-deploy/snell-refinement"

emit-qr:
	@test -n "$(CLIENT)" || { echo "usage: make emit-qr CLIENT=phone [TYPE=singbox|uri] [OUT=phone.png]"; exit 1; }
	./scripts/emit-qr.sh $(CLIENT) \
	  $(if $(TYPE),--type $(TYPE)) \
	  $(if $(OUT),--out $(OUT))

check-certs:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	VPN_SECRETS_FILE=$(SECRETS_FILE) ./scripts/check-certs.sh

audit-permissions:
	./scripts/audit-permissions.sh

asn-drift:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/asn-drift.sh

check-ip-reputation:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/check-ip-reputation.sh

issue-bootstrap:
	@test -n "$${CLIENT:-}" || { echo "usage: make issue-bootstrap CLIENT=phone"; exit 1; }
	./scripts/issue-bootstrap.sh "$${CLIENT}"

issue-sub-token:
	@test -n "$${CLIENT:-}" || { echo "usage: make issue-sub-token CLIENT=phone [FORMAT=singbox|ripdpi] [EXPIRES=YYYY-MM-DD] [QR=1]"; exit 1; }
	./scripts/issue-sub-token.sh "$${CLIENT}" \
	  $(if $(FORMAT),--format $(FORMAT)) \
	  $(if $(EXPIRES),--expires $(EXPIRES)) \
	  $(if $(filter 1 yes true,$(QR)),--qr)

sub-reads:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/sub-reads.sh \
	  $(if $(SINCE),--since $(SINCE)) \
	  $(if $(ROUTE),--route $(ROUTE)) \
	  $(if $(LIMIT),--limit $(LIMIT))

test-tls-policing:
	@test -n "$(HOST)" || { echo "usage: make test-tls-policing HOST=vpn.example.com [STEPS=1,4,8,12,16,24]"; exit 1; }
	./scripts/test-tls-policing.sh --host $(HOST) \
	  $(if $(PORT),--port $(PORT)) \
	  $(if $(STEPS),--steps $(STEPS))

fleet-status:
	./scripts/fleet-status.sh

drift-since-tag:
	PROVIDER=$(PROVIDER) ENV=$(ENV) VPN_SECRETS_FILE=$(SECRETS_FILE) \
	  ./scripts/drift-since-tag.sh

fleet-rotate:
	@test -n "$${PLAN:-}" || { echo "usage: make fleet-rotate PLAN=~/.config/vpn-provision/fleet.yaml [RESUME=1] [DRY_RUN=1]"; exit 1; }
	./scripts/fleet-rotate.sh --plan "$${PLAN}" \
	  $(if $(filter 1 yes true,$(RESUME)),--resume) \
	  $(if $(filter 1 yes true,$(DRY_RUN)),--dry-run)

watch-spare:
	PROVIDER=$(PROVIDER) BLUE_ENV=$(ENV) LIVENESS_CONFIG="$(LIVENESS_CONFIG)" ./scripts/warm-spare-watcher.sh

promote-spare:
	@test -n "$(OTP)" || { echo "usage: make promote-spare OTP=<value>"; exit 1; }
	PROVIDER=$(PROVIDER) BLUE_ENV=$(ENV) LIVENESS_CONFIG="$(LIVENESS_CONFIG)" ./scripts/promote-spare.sh $(OTP)

protocol-liveness:
	@test -n "$(LIVENESS_CONFIG)" || { echo "usage: make protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml"; exit 1; }
	python3 ./scripts/protocol-liveness.py --config "$(LIVENESS_CONFIG)"

install-liveness-sentinel:
	@test -n "$(LIVENESS_CONFIG)" -a -n "$(SENTINEL)" -a -n "$(CLIENT)" || { echo "usage: make install-liveness-sentinel LIVENESS_CONFIG=… SENTINEL=… CLIENT=…"; exit 1; }
	@echo "If the sentinel policy requires AWG, paste the one-time private key for $(CLIENT), then press Enter:"
	@./scripts/install-liveness-sentinel.sh --config "$(LIVENESS_CONFIG)" --sentinel "$(SENTINEL)" --client "$(CLIENT)" --awg-private-key-stdin

probing-summary:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/probing-summary.sh

tspu-canary:
	./scripts/tspu-canary.sh

emit-sbom:
	VPN_SECRETS_FILE=$(SECRETS_FILE) SBOM_LABEL=$(ENV) python3 ./scripts/emit-sbom.py

audit-log:
	./scripts/audit-log.sh read

audit-log-append:
	@test -n "$(ACTION)" || { echo "usage: make audit-log-append ACTION=… [CLIENT=…] [NOTE=…]"; exit 1; }
	ENV=$(ENV) PROVIDER=$(PROVIDER) ./scripts/audit-log.sh append \
	  --action $(ACTION) \
	  $(if $(CLIENT),--client $(CLIENT)) \
	  $(if $(NOTE),--note "$(NOTE)")

setup-yubikey:
	./scripts/setup-yubikey-age.sh $(if $(filter 1 yes true,$(REENCRYPT)),--reencrypt)

check-killswitch:
	@test -n "$(BUNDLE)" || { echo "usage: make check-killswitch BUNDLE=phone.singbox.json"; exit 1; }
	python3 ./scripts/check-singbox-killswitch.py $(BUNDLE)

install-operator-crons:
	PROVIDER=$(PROVIDER) ENV=$(ENV) LIVENESS_CONFIG="$(LIVENESS_CONFIG)" ./scripts/install-operator-crons.sh \
	  $(if $(filter 1 yes true,$(DRY_RUN)),--dry-run)

remove-operator-crons:
	./scripts/install-operator-crons.sh --remove

scan-targets:
	@test -n "$(SEEDS)$(CIDR)$(CRAWL)" || { \
	  echo "scan-targets needs one of:"; \
	  echo "  make scan-targets SEEDS=path/to/seeds.txt"; \
	  echo "  make scan-targets CIDR=107.172.103.0/24"; \
	  echo "  make scan-targets CRAWL=https://launchpad.net/ubuntu/+archivemirrors"; \
	  exit 1; }
	./scripts/scan-reality-targets.sh \
	  $(if $(SEEDS),--seeds $(SEEDS)) \
	  $(if $(CIDR),--cidr $(CIDR)) \
	  $(if $(CRAWL),--crawl $(CRAWL)) \
	  $(if $(THREADS),--threads $(THREADS)) \
	  $(if $(TIMEOUT),--timeout $(TIMEOUT)) \
	  $(if $(TOP),--top $(TOP)) \
	  $(if $(VALIDATE),--validate)

blue-green:
	@test -n "$(GREEN_ENV)" || { echo "GREEN_ENV=<name> required (e.g. green, spare2)"; exit 1; }
	PROVIDER=$(PROVIDER) BLUE_ENV=$(ENV) GREEN_ENV=$(GREEN_ENV) ./scripts/blue-green.sh

bats-test:
	bats tests/bats/

vpnd-test:
	cd vpnd && cargo test --release --locked

vpnd-clippy:
	cd vpnd && cargo clippy --release --all-targets --locked -- -D warnings

vpnd-mutants:
	cd vpnd && cargo mutants --no-shuffle

tf-policy:
	@for p in upcloud hetzner vultr; do \
	  echo "== $$p =="; \
	  terraform -chdir=terraform/providers/$$p init -backend=false >/dev/null && \
	  terraform -chdir=terraform/providers/$$p test; \
	done
	conftest verify --rego-version v0 -p terraform/policy/
