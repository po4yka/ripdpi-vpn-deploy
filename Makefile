PROVIDER ?= upcloud
ENV      ?= prod

# This target accepts operator paths and aliases.  Keep them literal before
# included Makefiles, exported variables, or eager source-identity recipes can
# evaluate command-line Make syntax.
ifneq ($(filter network-exposure-review,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error network exposure review requires exactly one Make goal)
endif
_NETWORK_EXPOSURE_ALLOWED_COMMAND_VARIABLES := NETWORK_EXPOSURE_CONFIG ANSIBLE_LIMIT
_NETWORK_EXPOSURE_COMMAND_VARIABLES := $(foreach variable,$(.VARIABLES),$(if $(filter command line override,$(origin $(variable))),$(variable)))
_NETWORK_EXPOSURE_FORBIDDEN_COMMAND_VARIABLES := $(filter-out $(_NETWORK_EXPOSURE_ALLOWED_COMMAND_VARIABLES),$(_NETWORK_EXPOSURE_COMMAND_VARIABLES))
ifneq ($(strip $(_NETWORK_EXPOSURE_FORBIDDEN_COMMAND_VARIABLES)),)
$(error network exposure review accepts command-line values only for NETWORK_EXPOSURE_CONFIG and ANSIBLE_LIMIT)
endif
_NETWORK_EXPOSURE_LITERAL_INPUTS := $(value NETWORK_EXPOSURE_CONFIG)$(value ANSIBLE_LIMIT)$(value ENV)$(value PROVIDER)$(value HOME)$(value DEPLOY_SOURCE_REVISION)$(value DEPLOYABLE_SOURCE_DIGEST)
override NETWORK_EXPOSURE_CONFIG := $(value NETWORK_EXPOSURE_CONFIG)
override ANSIBLE_LIMIT := $(value ANSIBLE_LIMIT)
override ENV := $(value ENV)
override PROVIDER := $(value PROVIDER)
override HOME := $(value HOME)
override DEPLOY_SOURCE_REVISION :=
override DEPLOYABLE_SOURCE_DIGEST :=
MAKEOVERRIDES :=
ifneq ($(findstring $$,$(_NETWORK_EXPOSURE_LITERAL_INPUTS)),)
$(error network exposure review inputs must be literal values)
endif
ifneq ($(findstring ",$(_NETWORK_EXPOSURE_LITERAL_INPUTS)),)
$(error network exposure review inputs must be literal values)
endif
ifneq ($(findstring ',$(_NETWORK_EXPOSURE_LITERAL_INPUTS)),)
$(error network exposure review inputs must be literal values)
endif
endif

# Tailnet promotion accepts one private config path and ambient provider
# capabilities. Capture them before includes and eager assignments can expand
# command-line Make syntax.
ifneq ($(filter tailnet-network-promote,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error Tailnet network promotion requires exactly one Make goal)
endif
_TAILNET_NETWORK_ALLOWED_COMMAND_VARIABLES := TAILNET_NETWORK_CONFIG
_TAILNET_NETWORK_COMMAND_VARIABLES := $(foreach variable,$(.VARIABLES),$(if $(filter command line override,$(origin $(variable))),$(variable)))
_TAILNET_NETWORK_FORBIDDEN_COMMAND_VARIABLES := $(filter-out $(_TAILNET_NETWORK_ALLOWED_COMMAND_VARIABLES),$(_TAILNET_NETWORK_COMMAND_VARIABLES))
ifneq ($(filter-out undefined environment,$(origin UPCLOUD_TOKEN)),)
$(error Tailnet network promotion provider credentials must come from the environment)
endif
ifneq ($(strip $(_TAILNET_NETWORK_FORBIDDEN_COMMAND_VARIABLES)),)
$(error Tailnet network promotion accepts command-line values only for TAILNET_NETWORK_CONFIG)
endif
_TAILNET_NETWORK_LITERAL_INPUTS := $(value ENV)$(value PROVIDER)$(value HOME)$(value DEPLOY_SOURCE_REVISION)$(value DEPLOYABLE_SOURCE_DIGEST)
override TAILNET_NETWORK_CONFIG := $(value TAILNET_NETWORK_CONFIG)
override ENV := $(value ENV)
override PROVIDER := $(value PROVIDER)
override HOME := $(value HOME)
override DEPLOY_SOURCE_REVISION :=
override DEPLOYABLE_SOURCE_DIGEST :=
override UPCLOUD_TOKEN := $(value UPCLOUD_TOKEN)
export TAILNET_NETWORK_CONFIG UPCLOUD_TOKEN
unexport UPCLOUD_USERNAME UPCLOUD_PASSWORD UPCLOUD_API_USERNAME UPCLOUD_API_PASSWORD
unexport MAKEFLAGS MFLAGS
MAKEOVERRIDES :=
ifneq ($(findstring $$,$(_TAILNET_NETWORK_LITERAL_INPUTS)),)
$(error Tailnet network promotion inputs must be literal values)
endif
ifneq ($(findstring ",$(_TAILNET_NETWORK_LITERAL_INPUTS)),)
$(error Tailnet network promotion inputs must be literal values)
endif
ifneq ($(findstring ',$(_TAILNET_NETWORK_LITERAL_INPUTS)),)
$(error Tailnet network promotion inputs must be literal values)
endif
endif

# Disposable liveness lifecycle inputs are controller data, not Make syntax.
# Capture them before trusted includes and eager source-identity assignments.
_DISPOSABLE_LIVENESS_GOALS := prepare-disposable-liveness install-disposable-liveness-sentinel protocol-liveness-disposable deonboard-disposable-liveness
ifneq ($(filter $(_DISPOSABLE_LIVENESS_GOALS),$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error disposable liveness requires exactly one Make goal)
endif
ifneq ($(filter prepare-disposable-liveness,$(MAKECMDGOALS)),)
_DISPOSABLE_LIVENESS_ALLOWED_COMMAND_VARIABLES := EXECUTOR_PROFILE EXECUTOR_MANIFEST
else ifneq ($(filter install-disposable-liveness-sentinel,$(MAKECMDGOALS)),)
_DISPOSABLE_LIVENESS_ALLOWED_COMMAND_VARIABLES := LIVENESS_CONFIG SENTINEL CLIENT EXECUTOR_MANIFEST EXECUTOR_BINDING STAGING_CLEANUP_MANIFEST HOSTS COHORTS
ifneq ($(strip $(value SOPS_FILES)),)
$(error disposable install requires one shared staging secrets file)
endif
else ifneq ($(filter protocol-liveness-disposable,$(MAKECMDGOALS)),)
_DISPOSABLE_LIVENESS_ALLOWED_COMMAND_VARIABLES := LIVENESS_CONFIG EXECUTOR_MANIFEST EXECUTOR_BINDING
else
_DISPOSABLE_LIVENESS_ALLOWED_COMMAND_VARIABLES := EXECUTOR_MANIFEST EXECUTOR_BINDING STAGING_POST_DESTROY_EVIDENCE LIVENESS_SENTINEL_REGISTRY LIVENESS_CONFIG SOPS_FILE DEONBOARD_EVIDENCE
endif
_DISPOSABLE_LIVENESS_COMMAND_VARIABLES := $(foreach variable,$(.VARIABLES),$(if $(filter command line override,$(origin $(variable))),$(variable)))
_DISPOSABLE_LIVENESS_FORBIDDEN_COMMAND_VARIABLES := $(filter-out $(_DISPOSABLE_LIVENESS_ALLOWED_COMMAND_VARIABLES),$(_DISPOSABLE_LIVENESS_COMMAND_VARIABLES))
ifneq ($(strip $(_DISPOSABLE_LIVENESS_FORBIDDEN_COMMAND_VARIABLES)),)
$(error disposable liveness accepts only its documented command-line fields)
endif
_DISPOSABLE_LIVENESS_LITERAL_INPUTS := $(value EXECUTOR_PROFILE)$(value EXECUTOR_MANIFEST)$(value EXECUTOR_BINDING)$(value STAGING_CLEANUP_MANIFEST)$(value STAGING_POST_DESTROY_EVIDENCE)$(value DEONBOARD_EVIDENCE)$(value LIVENESS_CONFIG)$(value LIVENESS_SENTINEL_REGISTRY)$(value SENTINEL)$(value CLIENT)$(value SOPS_FILE)$(value HOSTS)$(value COHORTS)$(value ENV)$(value PROVIDER)$(value HOME)$(value DEPLOY_SOURCE_REVISION)$(value DEPLOYABLE_SOURCE_DIGEST)
override EXECUTOR_PROFILE := $(value EXECUTOR_PROFILE)
override EXECUTOR_MANIFEST := $(value EXECUTOR_MANIFEST)
override EXECUTOR_BINDING := $(value EXECUTOR_BINDING)
override STAGING_CLEANUP_MANIFEST := $(value STAGING_CLEANUP_MANIFEST)
override STAGING_POST_DESTROY_EVIDENCE := $(value STAGING_POST_DESTROY_EVIDENCE)
override DEONBOARD_EVIDENCE := $(value DEONBOARD_EVIDENCE)
override LIVENESS_CONFIG := $(value LIVENESS_CONFIG)
override LIVENESS_SENTINEL_REGISTRY := $(value LIVENESS_SENTINEL_REGISTRY)
override SENTINEL := $(value SENTINEL)
override CLIENT := $(value CLIENT)
override SOPS_FILE := $(value SOPS_FILE)
override HOSTS := $(value HOSTS)
override COHORTS := $(value COHORTS)
override ENV := $(value ENV)
override PROVIDER := $(value PROVIDER)
override HOME := $(value HOME)
override DEPLOY_SOURCE_REVISION :=
override DEPLOYABLE_SOURCE_DIGEST :=
MAKEOVERRIDES :=
unexport MAKEFLAGS MFLAGS
ifneq ($(findstring $$,$(_DISPOSABLE_LIVENESS_LITERAL_INPUTS)),)
$(error disposable liveness inputs must be literal values)
endif
ifneq ($(findstring ",$(_DISPOSABLE_LIVENESS_LITERAL_INPUTS)),)
$(error disposable liveness inputs must be literal values)
endif
ifneq ($(findstring ',$(_DISPOSABLE_LIVENESS_LITERAL_INPUTS)),)
$(error disposable liveness inputs must be literal values)
endif
endif

-include .fleet.mk

# Capture deployment labels before the eager Terraform path assignments below.
# The included fleet file remains trusted executable Make configuration.
ifneq ($(filter deploy dry-run deploy-canary backup-configure install-ssh-recovery staging-cleanup-manifest staging-destroy $(_DISPOSABLE_LIVENESS_GOALS),$(MAKECMDGOALS)),)
override ENV := $(value ENV)
override PROVIDER := $(value PROVIDER)
endif

# Staging credentials are ambient capabilities, never Make expressions. Reject
# every non-environment origin before eager assignments or child-environment
# construction can expand attacker-controlled Make syntax.
ifneq ($(filter staging-cleanup-manifest staging-destroy,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error staging cleanup requires exactly one Make goal)
endif
ifneq ($(filter-out undefined environment,$(origin UPCLOUD_USERNAME) $(origin UPCLOUD_PASSWORD) $(origin UPCLOUD_API_USERNAME) $(origin UPCLOUD_API_PASSWORD) $(origin UPCLOUD_TOKEN)),)
$(error staging cleanup credentials must come from the environment)
endif
_STAGING_PRIMARY_CREDENTIALS := $(if $(value UPCLOUD_USERNAME),1,0)$(if $(value UPCLOUD_PASSWORD),1,0)
_STAGING_ALIAS_CREDENTIALS := $(if $(value UPCLOUD_API_USERNAME),1,0)$(if $(value UPCLOUD_API_PASSWORD),1,0)
_STAGING_TOKEN_CREDENTIAL := $(if $(value UPCLOUD_TOKEN),1,0)
ifeq ($(_STAGING_PRIMARY_CREDENTIALS)$(_STAGING_ALIAS_CREDENTIALS)$(_STAGING_TOKEN_CREDENTIAL),11000)
override UPCLOUD_USERNAME := $(value UPCLOUD_USERNAME)
override UPCLOUD_PASSWORD := $(value UPCLOUD_PASSWORD)
export UPCLOUD_USERNAME UPCLOUD_PASSWORD
unexport UPCLOUD_TOKEN
else ifeq ($(_STAGING_PRIMARY_CREDENTIALS)$(_STAGING_ALIAS_CREDENTIALS)$(_STAGING_TOKEN_CREDENTIAL),00110)
override UPCLOUD_USERNAME := $(value UPCLOUD_API_USERNAME)
override UPCLOUD_PASSWORD := $(value UPCLOUD_API_PASSWORD)
export UPCLOUD_USERNAME UPCLOUD_PASSWORD
unexport UPCLOUD_TOKEN
else ifeq ($(_STAGING_PRIMARY_CREDENTIALS)$(_STAGING_ALIAS_CREDENTIALS)$(_STAGING_TOKEN_CREDENTIAL),00001)
override UPCLOUD_TOKEN := $(value UPCLOUD_TOKEN)
export UPCLOUD_TOKEN
unexport UPCLOUD_USERNAME UPCLOUD_PASSWORD
else
$(error staging cleanup requires exactly one UpCloud credential mode)
endif
unexport UPCLOUD_API_USERNAME UPCLOUD_API_PASSWORD
endif

# Tailnet enrollment is an ambient one-node capability. Reject command-line
# Make data before it can enter implicit exports or recipe expansion.
ifneq ($(filter deploy dry-run deploy-canary tailnet-network-promote,$(MAKECMDGOALS)),)
ifneq ($(filter-out undefined environment,$(origin TAILSCALE_AUTH_KEY)),)
$(error Tailnet enrollment credentials must come from the environment)
endif
ifneq ($(origin TAILSCALE_AUTH_KEY),undefined)
override TAILSCALE_AUTH_KEY := $(value TAILSCALE_AUTH_KEY)
export TAILSCALE_AUTH_KEY
endif
endif

HOSTS   ?=
COHORTS ?=
SOPS_FILES ?=
AWG_EVIDENCE_INVENTORY ?=
AWG_EVIDENCE_VARS ?=
ANSIBLE_LIMIT ?=
ANSIBLE_EXTRA_VARS_FILE ?=
DEPLOY_SSH_CONTEXTS_FILE ?=
DEPLOY_PROMOTION_CONFIG_FILE ?=
NETWORK_EXPOSURE_CONFIG ?=

TF_ROOT       := terraform/providers/$(PROVIDER)
TF_ENV        := ./scripts/terraform-env.sh
ANSIBLE_DIR   := ansible
RUNTIME_DIR   ?= $(if $(XDG_RUNTIME_DIR),$(XDG_RUNTIME_DIR),$(if $(TMPDIR),$(TMPDIR),/tmp)/vpn-provision-$(shell id -u))
CLOUD_INIT_IMAGE ?= ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90
SECRETS_FILE  ?= $(RUNTIME_DIR)/vpn-$(ENV).secrets.yaml
SOPS_FILE     ?= $(HOME)/.config/vpn-provision/$(ENV).secrets.sops.yaml
TFVARS        := $(TF_ROOT)/environments/$(ENV).tfvars
TFPLAN        := $(TF_ROOT)/$(ENV).tfplan
ZIZMOR_VERSION := 1.29.0
PROMTOOL_VERSION := 3.14.0
DEPLOY_SOURCE_REVISION ?= $(shell ./scripts/deploy-source-identity.sh --revision 2>/dev/null)
DEPLOYABLE_SOURCE_DIGEST ?= $(shell ./scripts/deploy-source-identity.sh --digest 2>/dev/null)

export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg
export NETWORK_EXPOSURE_CONFIG
export PROVIDER ENV CLIENT PLAN HOST VANTAGE REALITY_TARGET_VANTAGE LIVENESS_CONFIG DEPLOY_SOURCE_REVISION DEPLOYABLE_SOURCE_DIGEST
INSPECT_HOSTS ?=
INSPECT_INVENTORY ?= $(ANSIBLE_DIR)/inventory/generated.ini
INSPECT_KNOWN_HOSTS ?= $(HOME)/.ssh/known_hosts
export INSPECT_HOSTS INSPECT_INVENTORY INSPECT_KNOWN_HOSTS

.PHONY: help init validate plan apply inventory wait decrypt require-inventory require-clean-source validate-ansible-extra-vars dry-run deploy tailnet-network-promote backup-configure deploy-canary os-maintenance verify source-drift security-verify security-audit clean \
        pre-deploy-check network-exposure-review \
        rollback-xray rollback-config rotate-credentials check-prereqs \
        destroy backup-state burn-check diff-secrets emit-singbox emit-awg emit-bundle install-hooks \
        molecule-test smoke-test validate-target monitor-reality-target probe-sni-survival scan-targets blue-green \
        spot-check-secrets bootstrap-secrets probe-asn probe-matrix-control probe-matrix-cell probe-matrix-tools emit-probe-matrix-profile emit-qr check-certs \
        audit-permissions asn-drift check-ip-reputation issue-bootstrap \
        test-tls-policing probe-payload-throttle fleet-status drift-since-tag fleet-rotate \
        snell-refinement \
        protocol-liveness monitor-protocol-liveness install-liveness-sentinel \
        prepare-disposable-liveness install-disposable-liveness-sentinel protocol-liveness-disposable deonboard-disposable-liveness \
        watch-spare promote-spare probing-summary xray-diagnostics tspu-canary \
        emit-sbom molecule-full-stack audit-log audit-log-append pyinfra-audit \
        setup-yubikey check-killswitch install-operator-crons \
        remove-operator-crons issue-sub-token sub-reads \
        observability-render observability-validate observability-status \
        observability-drill observability-deploy observability-rotate observability-rollback \
        observability-remove observability-silence-create observability-silence-delete \
        awg-evidence-provision \
        test-native-runtime test-probe-matrix-mtproto test-unit snapshot-check snapshot-update validate-secrets \
        actionlint-check zizmor-check zizmor-test cloud-init-schema tf-test yamllint-check shellcheck \
        ci-fast bats-test vpnd-test vpnd-clippy vpnd-deny vpnd-msrv vpnd-mutants tf-policy tf-policy-verify \
        task-tools task-check task-list task-ready task-graph task-federation \
        check

help:
	@echo "vpn-deploy Makefile"
	@echo ""
	@echo "Variables (override on command line):"
	@echo "  PROVIDER  current: $(PROVIDER)  (upcloud | hetzner | vultr | scaleway)"
	@echo "  ENV       current: $(ENV)       (prod | staging)"
	@echo "  ANSIBLE_LIMIT             Optional host/group limit for live Ansible targets"
	@echo "  ANSIBLE_EXTRA_VARS_FILE   Optional limited same-owner mode-0600 YAML; requires ANSIBLE_LIMIT"
	@echo "  DEPLOY_SSH_CONTEXTS_FILE  Required mode-0600 JSON mapping: exact alias → 2–8 SSH contexts"
	@echo "  DEPLOY_PROMOTION_CONFIG_FILE  Deploy-only mode-0600 JSON mapping: exact alias → promotion proof config"
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
	@echo "  task-tools                 Install pinned mdtask and OpenSpec tools"
	@echo "  task-check                 Validate task, mdtask, OpenSpec, board, and history contracts"
	@echo "  task-list                  List portfolio tasks"
	@echo "  task-ready                 Show the unblocked execution frontier"
	@echo "  task-graph                 Render the local task dependency graph"
	@echo "  task-federation PEER_ROOT=…  Validate the combined RIPDPI backlog graph"
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
	@echo "  backup-configure          Configure one exact ANSIBLE_LIMIT during an exclusive stopped-backup window; never runs backups or timers"
	@echo "  dry-run                    Serial exact-node check; requires DEPLOY_SSH_CONTEXTS_FILE"
	@echo "  deploy                     Serial exact-node transaction; also requires DEPLOY_PROMOTION_CONFIG_FILE"
	@echo "  deploy-canary              Deploy ENV=canary through the normal deploy flow"
	@echo "  os-maintenance             Rolling full OS upgrade + required reboot + verification"
	@echo "  verify [TAG_ON_SUCCESS=1]  ACTIVE checks; watchdog may restart services (+ optional tag)"
	@echo "  inspect INSPECT_HOSTS=…    Passive SSH observation of exact comma-separated inventory names"
	@echo "  source-drift               Require live deployable digest to match the clean checkout"
	@echo "  security-verify            Host hardening checks (SSH/sysctl/firewall/services)"
	@echo "  staging-cleanup-manifest   Bind one ci-staging UpCloud state to a private cleanup manifest"
	@echo "  staging-destroy            Destroy only the exact manifest-bound staging resources"
	@echo "  awg-evidence-provision     Provision the three-host AWG evidence lane (after decrypt)"
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
	@echo "  monitor-protocol-liveness LIVENESS_CONFIG=…  Persist and alert on protocol-liveness transitions"
	@echo "  install-liveness-sentinel LIVENESS_CONFIG=… SENTINEL=… CLIENT=…  Secure sentinel onboarding"
	@echo "  prepare-disposable-liveness EXECUTOR_PROFILE=… EXECUTOR_MANIFEST=…  Create one no-mount executor"
	@echo "  install-disposable-liveness-sentinel …  Bind and onboard one disposable sentinel from stdin"
	@echo "  protocol-liveness-disposable …  Evaluate one exact executor-bound report"
	@echo "  deonboard-disposable-liveness …  Remove the exact assignment after guarded provider absence"
	@echo "  watch-spare                Cron: probe blue, push OTP-gated promote alert"
	@echo "  promote-spare OTP=…        Consume OTP and swing traffic to GREEN_ENV"
	@echo ""
	@echo "── CLIENT / DELIVERY ──────────────────────────────────────────────────"
	@echo "  emit-singbox CLIENT=…      Official sing-box P0/P2 JSON (multi-host + cohort aware)"
	@echo "  emit-awg CLIENT=…          AmneziaWG wg-quick .conf for a named peer"
	@echo "  emit-bundle CLIENT=…       RIPDPI P0/P1/P2 JSON with ripdpi extension"
	@echo "  emit-qr CLIENT=…           PNG QR for the client (TYPE=singbox|uri, OUT=path)"
	@echo "  issue-bootstrap CLIENT=…   Issue a one-time /bootstrap/<token> URL"
	@echo "  issue-sub-token CLIENT=…   Issue a long-lived /sub/<token> URL (FORMAT=singbox|ripdpi EXPIRES=… QR=1)"
	@echo "  client-drift CLIENT=…      Compare a device's last delivery identity with current inputs"
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
	@echo "  observability-{render,validate,status}  Exact-host configuration/read surface"
	@echo "  observability-{drill,deploy,rotate,rollback,remove}  Confirmed exact-host lifecycle"
	@echo "  burn-check                 External IP reachability probe"
	@echo "  asn-drift                  Alert on VPS ASN reassignment"
	@echo "  check-ip-reputation        Spamhaus / optional FireHOL file / AbuseIPDB"
	@echo "  probing-summary            7-day Xray/nginx/honeypot rollup"
	@echo "  xray-diagnostics           Fresh redacted Xray counters via local StatsService"
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
	@echo "  test-unit                  Run portable pytest tests; selected skips fail"
	@echo "  test-native-runtime        Run native integration tests in disposable Linux root environment"
	@echo "  test-probe-matrix-mtproto   Run the compiled Go helper tests"
	@echo "  snapshot-check             Diff every Jinja render against tests/snapshot/golden/"
	@echo "  snapshot-update            Refresh the goldens (run after intentional change)"
	@echo "  validate-secrets           jsonschema check (strict if SECRETS_FILE is set)"
	@echo "  validate-bundle            jsonschema + fingerprint check of a ripdpi bundle (BUNDLE=… or example)"
	@echo "  actionlint-check           Validate every GitHub Actions workflow"
	@echo "  zizmor-check               Audit owned GitHub automation (strict, offline)"
	@echo "  cloud-init-schema          Render shared cloud-init and run cloud-init schema"
	@echo "  tf-test                    terraform test for all provider roots"
	@echo "  yamllint-check             Lint repository YAML with the CI configuration"
	@echo "  shellcheck                 Lint every operator shell script"
	@echo "  ci-fast                    Portable CI-parity bundle (excludes native Linux lane, Molecule and validate)"
	@echo "  bats-test                  Run bats shell tests (tests/bats/)"
	@echo "  vpnd-test                  cargo test --release --locked inside vpnd/"
	@echo "  vpnd-clippy                cargo clippy --release --locked (deny warnings) inside vpnd/"
	@echo "  vpnd-deny                  cargo-deny policy against the committed lockfile"
	@echo "  vpnd-msrv                  cargo check --locked with Rust 1.88.0"
	@echo "  tf-policy                  terraform test + conftest OPA policy check for all providers"
	@echo "  tf-policy-verify           Run pinned Conftest policy tests without provider credentials"
	@echo "  network-exposure-review    Validate signed policy without changing managed hosts"
	@echo "  molecule-test ROLE=<name>  Run one role's molecule scenario"
	@echo "  molecule-full-stack        site.yml end-to-end inside a Docker container"

check-prereqs:
	@for tool in terraform ansible ansible-playbook ansible-lint sops age gitleaks jq ssh python3; do \
	  command -v $$tool >/dev/null 2>&1 || { echo "missing: $$tool"; exit 1; }; \
	done
	@terraform version -json | python3 -c 'import json, sys; version = tuple(int(part) for part in json.load(sys.stdin)["terraform_version"].split(".")[:2]); sys.exit(0 if version >= (1, 15) else 1)' || { echo "Terraform >= 1.15 required (run: mise exec -- make check-prereqs)"; exit 1; }
	@python3 -c 'import yaml' >/dev/null 2>&1 || { echo "missing: Python module PyYAML"; exit 1; }
	@echo "all prereqs present"

init:
	PROVIDER=$(PROVIDER) ENV=$(ENV) $(TF_ENV) init

validate:
	@for provider in upcloud hetzner vultr scaleway; do \
	  terraform -chdir=terraform/providers/$$provider fmt -check -recursive || exit 1; \
	  terraform -chdir=terraform/providers/$$provider validate || exit 1; \
	done
	gitleaks git --redact --no-banner .
	gitleaks git --staged --redact --no-banner .
	ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg ansible-lint $(ANSIBLE_DIR)
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
	PROVIDER=$(PROVIDER) ENV=$(ENV) HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" ./scripts/render-inventory.sh

network-exposure-review:
	@exec /usr/bin/env -i \
	  PATH="$$PATH" HOME="$$HOME" \
	  LANG="$${LANG:-C}" LC_ALL="$${LC_ALL:-}" LC_CTYPE="$${LC_CTYPE:-}" TZ="$${TZ:-UTC}" \
	  PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
	  NETWORK_EXPOSURE_CONFIG='$(NETWORK_EXPOSURE_CONFIG)' ANSIBLE_LIMIT='$(ANSIBLE_LIMIT)' \
	  python3 ./scripts/network-exposure-review-controller.py

wait:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/wait-cloud-init.sh

require-inventory:
	@test -s "$(ANSIBLE_DIR)/inventory/generated.ini" || { echo "missing generated inventory — run 'make inventory'"; exit 1; }
	@ansible-inventory --list | python3 -c 'import json, sys; document = json.load(sys.stdin); hosts = document.get("vpn", {}).get("hosts", []); raise SystemExit(0 if hosts else 1)' || { echo "generated inventory has no vpn hosts — run 'make inventory'"; exit 1; }

require-clean-source:
	@test -n "$(DEPLOY_SOURCE_REVISION)" && test -n "$(DEPLOYABLE_SOURCE_DIGEST)" || { echo "cannot derive deploy source identity"; exit 1; }
	@test -z "$$(git status --porcelain --untracked-files=normal)" || { echo "deployment and live source verification require a clean git checkout"; exit 1; }

validate-ansible-extra-vars:
	@if [ -n "$(ANSIBLE_EXTRA_VARS_FILE)" ]; then \
	  test -n "$(ANSIBLE_LIMIT)" || { echo "ANSIBLE_EXTRA_VARS_FILE requires ANSIBLE_LIMIT"; exit 1; }; \
	  test -f "$(ANSIBLE_EXTRA_VARS_FILE)" || { echo "missing $(ANSIBLE_EXTRA_VARS_FILE)"; exit 1; }; \
	  ANSIBLE_EXTRA_VARS_FILE="$(ANSIBLE_EXTRA_VARS_FILE)" python3 -c 'import os, stat; p = os.environ["ANSIBLE_EXTRA_VARS_FILE"]; s = os.stat(p, follow_symlinks=False); ok = stat.S_ISREG(s.st_mode) and not os.path.islink(p) and s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o600; raise SystemExit(0 if ok else 1)' || { echo "ANSIBLE_EXTRA_VARS_FILE must be a same-owner regular non-symlink file with mode 0600"; exit 1; }; \
	  python3 ./scripts/validate-ansible-extra-vars.py "$(ANSIBLE_EXTRA_VARS_FILE)" || exit 1; \
	fi

pre-deploy-check:
	@test -f "$(SECRETS_FILE)" || { echo "missing $(SECRETS_FILE) — run 'make decrypt'"; exit 1; }
	@if [ "$(SKIP_PRECHECK)" = "1" ]; then \
	  echo "pre-deploy-check: skipped (SKIP_PRECHECK=1)"; \
	else \
	  python3 ./scripts/validate-secrets.py $(SECRETS_FILE) --strict && \
	  VPN_SECRETS_FILE=$(SECRETS_FILE) python3 ./scripts/spot-check-secrets.py && \
	  VPN_SECRETS_FILE=$(SECRETS_FILE) ./scripts/check-certs.sh; \
	fi

# Preserve literal operator inputs before Make exports them. Source identity is
# recomputed inside the controller's closed environment, after its privacy gate.
ifneq ($(filter deploy dry-run deploy-canary,$(MAKECMDGOALS)),)
override ANSIBLE_LIMIT := $(value ANSIBLE_LIMIT)
override ANSIBLE_TAGS := $(value ANSIBLE_TAGS)
override SKIP_PRECHECK := $(value SKIP_PRECHECK)
override SECRETS_FILE := $(if $(filter file default undefined,$(origin SECRETS_FILE)),$(SECRETS_FILE),$(value SECRETS_FILE))
override ANSIBLE_EXTRA_VARS_FILE := $(if $(filter file default undefined,$(origin ANSIBLE_EXTRA_VARS_FILE)),$(ANSIBLE_EXTRA_VARS_FILE),$(value ANSIBLE_EXTRA_VARS_FILE))
override INSPECT_KNOWN_HOSTS := $(if $(filter file default undefined,$(origin INSPECT_KNOWN_HOSTS)),$(INSPECT_KNOWN_HOSTS),$(value INSPECT_KNOWN_HOSTS))
override DEPLOY_SSH_CONTEXTS_FILE := $(value DEPLOY_SSH_CONTEXTS_FILE)
override DEPLOY_PROMOTION_CONFIG_FILE := $(value DEPLOY_PROMOTION_CONFIG_FILE)
override TAILNET_NETWORK_CONFIG := $(value TAILNET_NETWORK_CONFIG)
endif
deploy dry-run deploy-canary: override DEPLOY_SOURCE_REVISION :=
deploy dry-run deploy-canary: override DEPLOYABLE_SOURCE_DIGEST :=
deploy dry-run: export DEPLOY_LIMIT = $(ANSIBLE_LIMIT)
deploy dry-run: export DEPLOY_TAGS = $(ANSIBLE_TAGS)
deploy dry-run: export DEPLOY_SKIP_PRECHECK = $(SKIP_PRECHECK)
deploy dry-run: export DEPLOY_SECRETS_FILE = $(SECRETS_FILE)
deploy dry-run: export DEPLOY_EXTRA_VARS_FILE = $(ANSIBLE_EXTRA_VARS_FILE)
deploy dry-run: export DEPLOY_KNOWN_HOSTS = $(INSPECT_KNOWN_HOSTS)
deploy dry-run: export DEPLOY_SSH_CONTEXTS_FILE := $(DEPLOY_SSH_CONTEXTS_FILE)
deploy dry-run: export DEPLOY_PROMOTION_CONFIG_FILE := $(DEPLOY_PROMOTION_CONFIG_FILE)
deploy dry-run: export DEPLOY_ENV = $(ENV)
deploy dry-run: export DEPLOY_PROVIDER = $(PROVIDER)
dry-run:
	@python3 scripts/deploy-controller.py dry-run

deploy:
	@python3 scripts/deploy-controller.py deploy

tailnet-network-promote:
	@test -n "$$TAILNET_NETWORK_CONFIG" || { echo "TAILNET_NETWORK_CONFIG required"; exit 1; }
	@python3 scripts/tailnet-network-controller.py --config "$$TAILNET_NETWORK_CONFIG"

# Capture caller data as simple variables before implicit environment export can
# expand Make functions. Repository-defined default paths still resolve normally.
ifneq ($(filter backup-configure,$(MAKECMDGOALS)),)
ifneq ($(MAKECMDGOALS),backup-configure)
$(error backup-configure must be invoked as the only Make goal)
endif
override ANSIBLE_LIMIT := $(value ANSIBLE_LIMIT)
override SECRETS_FILE := $(if $(filter file default undefined,$(origin SECRETS_FILE)),$(SECRETS_FILE),$(value SECRETS_FILE))
override ANSIBLE_EXTRA_VARS_FILE := $(if $(filter file default undefined,$(origin ANSIBLE_EXTRA_VARS_FILE)),$(ANSIBLE_EXTRA_VARS_FILE),$(value ANSIBLE_EXTRA_VARS_FILE))
override DEPLOY_SOURCE_REVISION :=
override DEPLOYABLE_SOURCE_DIGEST :=
endif
backup-configure: export BACKUP_CONFIGURE_INVENTORY = $(ANSIBLE_DIR)/inventory/generated.ini
backup-configure: export BACKUP_CONFIGURE_HOST = $(ANSIBLE_LIMIT)
backup-configure: export BACKUP_CONFIGURE_SECRETS_FILE = $(SECRETS_FILE)
backup-configure: export BACKUP_CONFIGURE_EXTRA_VARS_FILE = $(ANSIBLE_EXTRA_VARS_FILE)
backup-configure:
	@python3 scripts/backup-configure.py controller

deploy-canary: export CANARY_SECRETS_FILE = $(SECRETS_FILE)
deploy-canary: export CANARY_SOPS_FILE = $(SOPS_FILE)
deploy-canary:
	@case "$${CANARY_SECRETS_FILE##*/}" in vpn-canary.secrets.yaml) ;; \
	  *) echo "refusing deploy-canary: SECRETS_FILE must name vpn-canary.secrets.yaml" >&2; exit 2 ;; esac
	@case "$${CANARY_SOPS_FILE##*/}" in canary.secrets.sops.yaml) ;; \
	  *) echo "refusing deploy-canary: SOPS_FILE must name canary.secrets.sops.yaml" >&2; exit 2 ;; esac
	$(MAKE) ENV=canary deploy

os-maintenance: require-clean-source require-inventory validate-ansible-extra-vars pre-deploy-check
	ansible-playbook $(ANSIBLE_DIR)/playbooks/os-maintenance.yml \
	  $(if $(strip $(ANSIBLE_LIMIT)),--limit "$(ANSIBLE_LIMIT)") \
	  $(if $(strip $(ANSIBLE_EXTRA_VARS_FILE)),--extra-vars "@$(ANSIBLE_EXTRA_VARS_FILE)")
	$(MAKE) verify ANSIBLE_LIMIT="$(ANSIBLE_LIMIT)" ANSIBLE_EXTRA_VARS_FILE="$(ANSIBLE_EXTRA_VARS_FILE)"
	$(MAKE) security-verify ANSIBLE_LIMIT="$(ANSIBLE_LIMIT)" ANSIBLE_EXTRA_VARS_FILE="$(ANSIBLE_EXTRA_VARS_FILE)"
	@ENV=$(ENV) PROVIDER=$(PROVIDER) ./scripts/audit-log.sh append-best-effort \
	  --action os-maintenance \
	  --note "playbook=os-maintenance.yml serial=1 verified=true"

verify: require-clean-source require-inventory validate-ansible-extra-vars pre-deploy-check
	@if [ "$(TAG_ON_SUCCESS)" = "1" ] && [ -n "$(ANSIBLE_LIMIT)" ]; then \
	  echo "TAG_ON_SUCCESS=1 requires an unbounded fleet verification"; \
	  exit 1; \
	fi
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/verify.yml \
	  $(if $(strip $(ANSIBLE_LIMIT)),--limit "$(ANSIBLE_LIMIT)") \
	  $(if $(strip $(ANSIBLE_EXTRA_VARS_FILE)),--extra-vars "@$(ANSIBLE_EXTRA_VARS_FILE)")
	$(MAKE) source-drift ANSIBLE_LIMIT="$(ANSIBLE_LIMIT)" ANSIBLE_EXTRA_VARS_FILE="$(ANSIBLE_EXTRA_VARS_FILE)"
	@if [ "$(TAG_ON_SUCCESS)" = "1" ]; then \
	  tag="vpn-deploy-known-good-$$(date +%Y-%m-%d-%H%M)"; \
	  git tag "$$tag" && echo "tagged: $$tag"; \
	fi

source-drift: require-clean-source require-inventory validate-ansible-extra-vars
	ansible-playbook $(ANSIBLE_DIR)/playbooks/source-drift.yml \
	  $(if $(strip $(ANSIBLE_LIMIT)),--limit "$(ANSIBLE_LIMIT)") \
	  $(if $(strip $(ANSIBLE_EXTRA_VARS_FILE)),--extra-vars "@$(ANSIBLE_EXTRA_VARS_FILE)")

security-verify: require-inventory validate-ansible-extra-vars pre-deploy-check
	VPN_SECRETS_FILE=$(SECRETS_FILE) \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/security-verify.yml \
	  $(if $(strip $(ANSIBLE_LIMIT)),--limit "$(ANSIBLE_LIMIT)") \
	  $(if $(strip $(ANSIBLE_EXTRA_VARS_FILE)),--extra-vars "@$(ANSIBLE_EXTRA_VARS_FILE)")

security-audit:
	VPN_SECRETS_FILE=$(SECRETS_FILE) ansible-playbook $(ANSIBLE_DIR)/playbooks/security-audit.yml

xray-diagnostics: require-inventory validate-ansible-extra-vars
	ansible-playbook $(ANSIBLE_DIR)/playbooks/xray-diagnostics.yml \
	  $(if $(strip $(ANSIBLE_LIMIT)),--limit "$(ANSIBLE_LIMIT)") \
	  $(if $(strip $(ANSIBLE_EXTRA_VARS_FILE)),--extra-vars "@$(ANSIBLE_EXTRA_VARS_FILE)")

awg-evidence-provision: pre-deploy-check
	@test -f "$(ANSIBLE_DIR)/inventory/generated.ini" || { echo "missing generated inventory — run 'make inventory'"; exit 1; }
	@test -n "$(AWG_EVIDENCE_INVENTORY)" || { echo "AWG_EVIDENCE_INVENTORY=<file> required"; exit 1; }
	@test -f "$(AWG_EVIDENCE_INVENTORY)" || { echo "missing $(AWG_EVIDENCE_INVENTORY)"; exit 1; }
	@test -n "$(AWG_EVIDENCE_VARS)" || { echo "AWG_EVIDENCE_VARS=<mode-0600-file> required"; exit 1; }
	@test -f "$(AWG_EVIDENCE_VARS)" || { echo "missing $(AWG_EVIDENCE_VARS)"; exit 1; }
	@AWG_EVIDENCE_VARS="$(AWG_EVIDENCE_VARS)" python3 -c 'import os, stat; p = os.environ["AWG_EVIDENCE_VARS"]; s = os.stat(p, follow_symlinks=False); ok = stat.S_ISREG(s.st_mode) and not os.path.islink(p) and s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o600; raise SystemExit(0 if ok else 1)' || { echo "AWG_EVIDENCE_VARS must be a same-owner regular non-symlink file with mode 0600"; exit 1; }
	VPN_SECRETS_FILE="$(SECRETS_FILE)" \
	ansible-playbook $(ANSIBLE_DIR)/playbooks/provision-real-vps-awg-nat.yml \
	  -i "$(ANSIBLE_DIR)/inventory/generated.ini" \
	  -i "$(AWG_EVIDENCE_INVENTORY)" \
	  --extra-vars "@$(AWG_EVIDENCE_VARS)"

pyinfra-audit:
	@test -n "$(PYINFRA_HOSTS)" || { echo "PYINFRA_HOSTS=host[,host...] required"; exit 1; }
	@command -v pyinfra >/dev/null 2>&1 || { echo "missing: pyinfra (optional; see requirements.in and pyinfra/README.md)"; exit 1; }
	pyinfra pyinfra/inventory.py pyinfra/deploys/read_only_audit.py

clean: export CLEAN_SECRETS_FILE = $(SECRETS_FILE)
clean:
	@set -eu; \
	if [ -L "$$CLEAN_SECRETS_FILE" ]; then \
	  rm -f -- "$$CLEAN_SECRETS_FILE" 2>/dev/null || { echo "failed to remove decrypted secrets" >&2; exit 1; }; \
	elif [ -f "$$CLEAN_SECRETS_FILE" ]; then \
	  shred -u -- "$$CLEAN_SECRETS_FILE" 2>/dev/null || \
	    rm -f -- "$$CLEAN_SECRETS_FILE" 2>/dev/null || { echo "failed to remove decrypted secrets" >&2; exit 1; }; \
	fi

.PHONY: check-ci-deploy-gate
check-ci-deploy-gate:
	python3 scripts/check-ci-deploy-gate.py

# This goal treats caller fields as literal data, not make/shell programs.
ifneq ($(filter install-ssh-recovery,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error install-ssh-recovery requires exactly one goal)
endif
# Source identity is derived only inside the sanitized controller environment.
override DEPLOY_SOURCE_REVISION :=
override DEPLOYABLE_SOURCE_DIGEST :=
override ANSIBLE_DEBUG := $(value ANSIBLE_DEBUG)
export ANSIBLE_DEBUG
override SSH_RECOVERY_TARGET := $(value ANSIBLE_LIMIT)
override SSH_RECOVERY_WINDOW := $(value SSH_RECOVERY_EXCLUSIVE_WINDOW)
override SSH_RECOVERY_INVENTORY := $(value SSH_RECOVERY_INVENTORY)
override SSH_RECOVERY_KNOWN_HOSTS := $(value SSH_RECOVERY_KNOWN_HOSTS)
unexport ANSIBLE_LIMIT SSH_RECOVERY_EXCLUSIVE_WINDOW
unexport MAKEFLAGS MFLAGS
MAKEOVERRIDES :=
export SSH_RECOVERY_TARGET SSH_RECOVERY_WINDOW SSH_RECOVERY_INVENTORY SSH_RECOVERY_KNOWN_HOSTS
endif

.PHONY: install-ssh-recovery
# The controller checks debug, exact inventory and clean source before Ansible.
install-ssh-recovery:
	@python3 ./scripts/install-sshd-recovery.py

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

# These staging goals treat caller fields as literal data. Keep them separate
# from the free-form generic destroy surface and reject mixed goal execution.
ifneq ($(filter staging-cleanup-manifest staging-destroy,$(MAKECMDGOALS)),)
export STAGING_CLEANUP_MANIFEST STAGING_CLEANUP_STATE STAGING_CLEANUP_HOSTNAME STAGING_POST_DESTROY_EVIDENCE
unexport MAKEFLAGS MFLAGS
MAKEOVERRIDES :=
endif

.PHONY: staging-cleanup-manifest staging-destroy
staging-cleanup-manifest: override STAGING_CLEANUP_MANIFEST := $(value STAGING_CLEANUP_MANIFEST)
staging-cleanup-manifest: override STAGING_CLEANUP_STATE := $(value STAGING_CLEANUP_STATE)
staging-cleanup-manifest: override STAGING_CLEANUP_HOSTNAME := $(value STAGING_CLEANUP_HOSTNAME)
staging-destroy: override STAGING_CLEANUP_MANIFEST := $(value STAGING_CLEANUP_MANIFEST)
staging-destroy: override STAGING_POST_DESTROY_EVIDENCE := $(value STAGING_POST_DESTROY_EVIDENCE)
staging-cleanup-manifest staging-destroy: override DEPLOY_SOURCE_REVISION :=
staging-cleanup-manifest staging-destroy: override DEPLOYABLE_SOURCE_DIGEST :=

staging-cleanup-manifest:
	@./scripts/staging-cleanup-guard.py create-manifest \
	  --output "$${STAGING_CLEANUP_MANIFEST}" \
	  --provider "$${PROVIDER}" \
	  --environment "$${ENV}" \
	  --workspace "$${ENV}" \
	  --state "$${STAGING_CLEANUP_STATE}" \
	  --hostname "$${STAGING_CLEANUP_HOSTNAME}"

staging-destroy:
	@./scripts/destroy.sh --non-interactive \
	  --staging-manifest "$${STAGING_CLEANUP_MANIFEST}" \
	  --post-destroy-evidence "$${STAGING_POST_DESTROY_EVIDENCE}"

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
	@HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
	  VPN_SECRETS_FILE="$(SECRETS_FILE)" \
	  ./scripts/emit-singbox.sh "$${CLIENT}"

emit-awg:
	@test -n "$${CLIENT:-}" || { echo "CLIENT=<name> required"; exit 1; }
	@SOPS_FILE="$(SOPS_FILE)" ./scripts/emit-awg.sh "$${CLIENT}"

emit-bundle:
	@test -n "$${CLIENT:-}" || { echo "CLIENT=<name> required"; exit 1; }
	@HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
	  ./scripts/emit-bundle.sh "$${CLIENT}"

install-hooks:
	python3 -m pip install --require-hashes --no-deps -r requirements.txt
	pre-commit install
	pre-commit install --hook-type commit-msg

# Explicit Linux-only lane; run as root in a disposable runner/container.
test-native-runtime:
	@test "$$(uname -s)" = Linux && test "$$(id -u)" = 0 || { echo "native runtime tests require a disposable Linux root environment" >&2; exit 1; }
	env -u MAKELEVEL -u MAKEFLAGS -u MFLAGS -u MAKEOVERRIDES python3 -m pytest tests/unit/ -m native_runtime --fail-on-skip -v

test-probe-matrix-mtproto:
	cd tools/probe-matrix-mtproto && go test -mod=readonly -count=1 -v -timeout=2m -p=2 ./...

# Tests invoke operator Make targets and parse their stdout as JSON. Do not
# inherit recursive Make directory chatter, overrides or jobserver descriptors.
test-unit:
	env -u MAKELEVEL -u MAKEFLAGS -u MFLAGS -u MAKEOVERRIDES python3 -m pytest tests/unit/ scripts/tests/ -m "not native_runtime" --fail-on-skip -q

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

zizmor-check:
	@command -v zizmor >/dev/null 2>&1 || { echo "missing: zizmor $(ZIZMOR_VERSION) (run: mise install)" >&2; exit 1; }
	@test "$$(zizmor --version)" = "zizmor $(ZIZMOR_VERSION)" || { echo "zizmor $(ZIZMOR_VERSION) required (run: mise install)" >&2; exit 1; }
	@case "$${ZIZMOR_FORMAT:-plain}" in \
	  plain|github) ;; \
	  *) echo "ZIZMOR_FORMAT must be plain or github (SARIF does not fail on findings)" >&2; exit 1 ;; \
	esac
	zizmor --offline --strict-collection --no-config --persona=regular \
	  --format="$${ZIZMOR_FORMAT:-plain}" \
	  --collect=workflows --collect=actions --collect=dependabot --collect=pre-commit \
	  .github .pre-commit-config.yaml

zizmor-test:
	python3 tests/zizmor_gate_runtime.py

cloud-init-schema:
	@set -eu; \
	  rendered="$$(mktemp -t cloud-init.rendered.XXXXXX)"; \
	  trap 'rm -f "$$rendered"' 0; \
	  python3 scripts/render-cloud-init-ci.py > "$$rendered"; \
	  if command -v cloud-init >/dev/null 2>&1; then \
	    cloud-init schema --config-file "$$rendered"; \
	  elif command -v docker >/dev/null 2>&1; then \
	    python3 scripts/cloud-init-schema-container.py \
	      --image "$(CLOUD_INIT_IMAGE)" --config "$$rendered" --timeout 240; \
	  else \
	    echo "missing: cloud-init (or docker fallback)" >&2; \
	    exit 1; \
	  fi

tf-test:
	@command -v terraform >/dev/null 2>&1 || { echo "missing: terraform" >&2; exit 1; }
	@for provider in upcloud hetzner vultr scaleway; do \
	  echo "== terraform test: $$provider =="; \
	  terraform -chdir=terraform/providers/$$provider init -backend=false >/dev/null && \
	  terraform -chdir=terraform/providers/$$provider test || exit 1; \
	done

tf-policy-verify:
	@command -v conftest >/dev/null 2>&1 || { echo "missing: conftest (see mise.toml)" >&2; exit 1; }
	conftest verify --rego-version v0 -p terraform/policy/

tf-conftest:
	@command -v conftest >/dev/null 2>&1 || { echo "missing: conftest" >&2; exit 1; }
	@./scripts/tf-policy-test.sh -p "$(PROVIDER)" -e "$(ENV)"

yamllint-check:
	@command -v yamllint >/dev/null 2>&1 || { echo "missing: yamllint" >&2; exit 1; }
	yamllint -c .yamllint.yml .

shellcheck:
	@command -v shellcheck >/dev/null 2>&1 || { echo "missing: shellcheck" >&2; exit 1; }
	shellcheck -s bash -S warning scripts/*.sh terraform/exception/*/*.sh

vpnd-deny:
	@command -v cargo-deny >/dev/null 2>&1 || { echo "missing: cargo-deny" >&2; exit 1; }
	cd vpnd && cargo deny --locked check --config deny.toml

vpnd-msrv:
	@command -v cargo >/dev/null 2>&1 || { echo "missing: cargo" >&2; exit 1; }
	cd vpnd && cargo +1.88.0 check --locked

task-tools:
	npm ci --prefix tools/tasking --ignore-scripts

task-check:
	OPENSPEC_TELEMETRY=0 ./taskctl validate

task-list:
	OPENSPEC_TELEMETRY=0 ./taskctl list

task-ready:
	OPENSPEC_TELEMETRY=0 ./taskctl ready

task-graph:
	OPENSPEC_TELEMETRY=0 ./taskctl graph

task-federation:
	@test -n "$(PEER_ROOT)" || { echo "PEER_ROOT=<RIPDPI checkout> required" >&2; exit 1; }
	OPENSPEC_TELEMETRY=0 ./taskctl federation validate --peer-root "$(PEER_ROOT)"

# Portable pre-PR bundle for operators. Mirrors portable required CI jobs that can run
# without provider credentials, GitHub services, or Molecule containers.
# Native Linux runtime coverage is a separate required CI lane.
# `make check` adds validate (fmt, gitleaks, ansible-lint). Missing local
# tooling is a failure rather than a misleading green gate.
.PHONY: liveness-profile-check
liveness-profile-check:
	python3 scripts/check-liveness-profile-compatibility.py --sing-box-version 1.13.16 --xray-version 26.3.27

ci-fast:
	@$(MAKE) test-probe-matrix-mtproto
	@$(MAKE) actionlint-check
	@$(MAKE) zizmor-check
	@$(MAKE) zizmor-test
	@$(MAKE) cloud-init-schema
	@$(MAKE) tf-test
	@$(MAKE) tf-policy-verify
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
	@$(MAKE) liveness-profile-check
	@command -v promtool >/dev/null 2>&1 || { echo "missing: promtool $(PROMTOOL_VERSION) (run: mise install)" >&2; exit 1; }
	@promtool --version 2>&1 | grep -F "version $(PROMTOOL_VERSION)" >/dev/null || { echo "promtool $(PROMTOOL_VERSION) required (run: mise install)" >&2; exit 1; }
	@$(MAKE) test-unit
	@echo "== bats shell tests =="; bats tests/bats/
	@command -v cargo >/dev/null 2>&1 || { echo "missing: cargo" >&2; exit 1; }
	@echo "== vpnd clippy =="; cd vpnd && cargo clippy --release --all-targets --locked -- -D warnings
	@echo "== vpnd tests =="; cd vpnd && cargo test --release --locked
	@echo "ci-fast: OK"

# Union gate: everything in validate + everything in ci-fast.
# Run this before any commit touching Ansible, Terraform, or Python to get
# the same signal that CI produces without waiting for a remote run.
check: task-check validate ci-fast  ## Full local gate: task contract + validate + ci-fast

molecule-test:
	@test -n "$(ROLE)" || { echo "ROLE=<role-name> required (e.g. baseline, firewall, xray)"; exit 1; }
	cd $(ANSIBLE_DIR)/roles/$(ROLE) && molecule test

molecule-full-stack:
	cd $(ANSIBLE_DIR) && molecule -c molecule/full-stack/molecule.yml test -s full-stack

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
	HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
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
	HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
	./scripts/issue-bootstrap.sh "$${CLIENT}"

issue-sub-token:
	@test -n "$${CLIENT:-}" || { echo "usage: make issue-sub-token CLIENT=phone [FORMAT=singbox|ripdpi] [EXPIRES=YYYY-MM-DD] [QR=1]"; exit 1; }
	HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
	./scripts/issue-sub-token.sh "$${CLIENT}" \
	  $(if $(FORMAT),--format $(FORMAT)) \	  $(if $(EXPIRES),--expires $(EXPIRES)) \
	  $(if $(filter 1 yes true,$(QR)),--qr)

sub-reads:
	PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/sub-reads.sh \
	  $(if $(SINCE),--since $(SINCE)) \
	  $(if $(ROUTE),--route $(ROUTE)) \
	  $(if $(LIMIT),--limit $(LIMIT))

client-drift:
	@test -n "$${CLIENT:-}" || { echo "usage: make client-drift CLIENT=phone"; exit 1; }
	SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" ENV=$(ENV) \
	./scripts/client-drift.py "$${CLIENT}"

test-tls-policing:
	@test -n "$(HOST)" || { echo "usage: make test-tls-policing HOST=vpn.example.com [STEPS=1,4,8,12,16,24]"; exit 1; }
	./scripts/test-tls-policing.sh --host $(HOST) \
	  $(if $(PORT),--port $(PORT)) \
	  $(if $(STEPS),--steps $(STEPS))

fleet-status:
	./scripts/fleet-status.sh

.PHONY: inspect
inspect:
	python3 scripts/fleet-inspect.py

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

monitor-protocol-liveness:
	@test -n "$(LIVENESS_CONFIG)" || { echo "usage: make monitor-protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml"; exit 1; }
	SOPS_FILE="$(SOPS_FILE)" python3 ./scripts/monitor-protocol-liveness.py --config "$(LIVENESS_CONFIG)"

install-liveness-sentinel:
	@test -n "$(LIVENESS_CONFIG)" -a -n "$(SENTINEL)" -a -n "$(CLIENT)" || { echo "usage: make install-liveness-sentinel LIVENESS_CONFIG=… SENTINEL=… CLIENT=…"; exit 1; }
	@HOSTS="$(HOSTS)" COHORTS="$(COHORTS)" SOPS_FILE="$(SOPS_FILE)" SOPS_FILES="$(SOPS_FILES)" \
	  ./scripts/install-liveness-sentinel.sh --config "$(LIVENESS_CONFIG)" --sentinel "$(SENTINEL)" --client "$(CLIENT)" --awg-private-key-stdin

ifneq ($(filter $(_DISPOSABLE_LIVENESS_GOALS),$(MAKECMDGOALS)),)
export EXECUTOR_PROFILE EXECUTOR_MANIFEST EXECUTOR_BINDING STAGING_CLEANUP_MANIFEST STAGING_POST_DESTROY_EVIDENCE DEONBOARD_EVIDENCE LIVENESS_CONFIG LIVENESS_SENTINEL_REGISTRY SENTINEL CLIENT SOPS_FILE
unexport HOSTS COHORTS SOPS_FILES ANSIBLE_LIMIT ANSIBLE_EXTRA_VARS_FILE DESTROY_ARGS
endif

prepare-disposable-liveness:
	@test -n "$${EXECUTOR_PROFILE}" -a -n "$${EXECUTOR_MANIFEST}" || { echo "usage: make prepare-disposable-liveness EXECUTOR_PROFILE=… EXECUTOR_MANIFEST=…"; exit 1; }
	@build-gate -- python3 ./scripts/disposable_liveness_executor.py prepare \
	  --profile "$${EXECUTOR_PROFILE}" \
	  --manifest "$${EXECUTOR_MANIFEST}" \
	  --ttl-seconds 21600

install-disposable-liveness-sentinel: export HOSTS := $(HOSTS)
install-disposable-liveness-sentinel: export COHORTS := $(COHORTS)
install-disposable-liveness-sentinel:
	@test -n "$${LIVENESS_CONFIG}" -a -n "$${SENTINEL}" -a -n "$${CLIENT}" \
	  -a -n "$${EXECUTOR_MANIFEST}" -a -n "$${EXECUTOR_BINDING}" \
	  -a -n "$${STAGING_CLEANUP_MANIFEST}" -a -n "$${HOSTS}" -a -n "$${COHORTS}" || { echo "usage: make install-disposable-liveness-sentinel LIVENESS_CONFIG=… SENTINEL=… CLIENT=… EXECUTOR_MANIFEST=… EXECUTOR_BINDING=… STAGING_CLEANUP_MANIFEST=… HOSTS=… COHORTS=…"; exit 1; }
	@python3 ./scripts/install_liveness_sentinel.py \
	  --config "$${LIVENESS_CONFIG}" \
	  --sentinel "$${SENTINEL}" \
	  --client "$${CLIENT}" \
	  --awg-private-key-stdin \
	  --executor-manifest "$${EXECUTOR_MANIFEST}" \
	  --executor-binding "$${EXECUTOR_BINDING}" \
	  --cleanup-manifest "$${STAGING_CLEANUP_MANIFEST}"

protocol-liveness-disposable:
	@test -n "$${LIVENESS_CONFIG}" -a -n "$${EXECUTOR_MANIFEST}" -a -n "$${EXECUTOR_BINDING}" || { echo "usage: make protocol-liveness-disposable LIVENESS_CONFIG=… EXECUTOR_MANIFEST=… EXECUTOR_BINDING=…"; exit 1; }
	@python3 ./scripts/protocol-liveness.py \
	  --config "$${LIVENESS_CONFIG}" \
	  --executor-manifest "$${EXECUTOR_MANIFEST}" \
	  --executor-binding "$${EXECUTOR_BINDING}"

deonboard-disposable-liveness:
	@test -n "$${EXECUTOR_MANIFEST}" -a -n "$${EXECUTOR_BINDING}" \
	  -a -n "$${STAGING_POST_DESTROY_EVIDENCE}" -a -n "$${LIVENESS_SENTINEL_REGISTRY}" \
	  -a -n "$${LIVENESS_CONFIG}" -a -n "$${SOPS_FILE}" -a -n "$${DEONBOARD_EVIDENCE}" || { echo "usage: make deonboard-disposable-liveness EXECUTOR_MANIFEST=… EXECUTOR_BINDING=… STAGING_POST_DESTROY_EVIDENCE=… LIVENESS_SENTINEL_REGISTRY=… LIVENESS_CONFIG=… SOPS_FILE=… DEONBOARD_EVIDENCE=…"; exit 1; }
	@build-gate -- python3 ./scripts/disposable_liveness_executor.py deonboard \
	  --binding "$${EXECUTOR_BINDING}" \
	  --manifest "$${EXECUTOR_MANIFEST}" \
	  --absence-evidence "$${STAGING_POST_DESTROY_EVIDENCE}" \
	  --registry "$${LIVENESS_SENTINEL_REGISTRY}" \
	  --config "$${LIVENESS_CONFIG}" \
	  --sops-file "$${SOPS_FILE}" \
	  --output "$${DEONBOARD_EVIDENCE}"

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
	PROVIDER=$(PROVIDER) ENV=$(ENV) LIVENESS_CONFIG="$(LIVENESS_CONFIG)" SOPS_FILE="$(SOPS_FILE)" \
	  SOPS_AGE_KEY_FILE="$${SOPS_AGE_KEY_FILE:-}" ./scripts/install-operator-crons.sh \
	  $(if $(filter 1 yes true,$(DRY_RUN)),--dry-run)

remove-operator-crons:
	./scripts/install-operator-crons.sh --remove

# Keep operator-supplied values literal. The controller validates every path,
# exact inventory alias, component, environment and confirmation boundary.
OBSERVABILITY_INVENTORY ?= $(ANSIBLE_DIR)/inventory/generated.ini
OBSERVABILITY_ENVIRONMENT ?=
OBSERVABILITY_KNOWN_HOSTS ?= $(HOME)/.ssh/known_hosts
OBSERVABILITY_SECRETS_FILE ?= $(SECRETS_FILE)

ifneq ($(filter observability-render observability-validate observability-status observability-drill observability-deploy observability-rotate observability-rollback observability-remove observability-silence-create observability-silence-delete,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error observability operator commands require exactly one make goal)
endif
override OBSERVABILITY_INVENTORY_LITERAL := $(if $(filter file default undefined,$(origin OBSERVABILITY_INVENTORY)),$(OBSERVABILITY_INVENTORY),$(value OBSERVABILITY_INVENTORY))
override OBSERVABILITY_HOST_LITERAL := $(value OBSERVABILITY_HOST)
override OBSERVABILITY_ENVIRONMENT_LITERAL := $(if $(filter file default undefined,$(origin OBSERVABILITY_ENVIRONMENT)),$(OBSERVABILITY_ENVIRONMENT),$(value OBSERVABILITY_ENVIRONMENT))
override OBSERVABILITY_COMPONENT_LITERAL := $(value OBSERVABILITY_COMPONENT)
override OBSERVABILITY_KNOWN_HOSTS_LITERAL := $(if $(filter file default undefined,$(origin OBSERVABILITY_KNOWN_HOSTS)),$(OBSERVABILITY_KNOWN_HOSTS),$(value OBSERVABILITY_KNOWN_HOSTS))
override OBSERVABILITY_SECRETS_LITERAL := $(if $(filter file default undefined,$(origin OBSERVABILITY_SECRETS_FILE)),$(OBSERVABILITY_SECRETS_FILE),$(value OBSERVABILITY_SECRETS_FILE))
override OBSERVABILITY_VARS_LITERAL := $(value OBSERVABILITY_VARS)
override OBSERVABILITY_ROLLBACK_MANIFEST_LITERAL := $(value OBSERVABILITY_ROLLBACK_MANIFEST)
override OBSERVABILITY_SILENCE_OWNER_LITERAL := $(value OBSERVABILITY_SILENCE_OWNER)
override OBSERVABILITY_SILENCE_REQUEST_LITERAL := $(value OBSERVABILITY_SILENCE_REQUEST)
override OBSERVABILITY_SILENCE_ID_LITERAL := $(value OBSERVABILITY_SILENCE_ID)
ifeq ($(strip $(OBSERVABILITY_ENVIRONMENT_LITERAL)),)
$(error observability operator commands require OBSERVABILITY_ENVIRONMENT explicitly)
endif
export OBSERVABILITY_INVENTORY_LITERAL OBSERVABILITY_HOST_LITERAL
export OBSERVABILITY_ENVIRONMENT_LITERAL OBSERVABILITY_COMPONENT_LITERAL
export OBSERVABILITY_KNOWN_HOSTS_LITERAL OBSERVABILITY_SECRETS_LITERAL
export OBSERVABILITY_VARS_LITERAL OBSERVABILITY_ROLLBACK_MANIFEST_LITERAL OBSERVABILITY_SILENCE_OWNER_LITERAL
export OBSERVABILITY_SILENCE_REQUEST_LITERAL OBSERVABILITY_SILENCE_ID_LITERAL
unexport OBSERVABILITY_SILENCE_OWNER OBSERVABILITY_SILENCE_REQUEST OBSERVABILITY_SILENCE_ID
unexport MAKEFLAGS MFLAGS
MAKEOVERRIDES :=
endif

define observability_common
	  --inventory "$${OBSERVABILITY_INVENTORY_LITERAL}" \
	  --host "$${OBSERVABILITY_HOST_LITERAL}" \
	  --environment "$${OBSERVABILITY_ENVIRONMENT_LITERAL}" \
	  --component "$${OBSERVABILITY_COMPONENT_LITERAL}" \
	  --known-hosts "$${OBSERVABILITY_KNOWN_HOSTS_LITERAL}"
endef

observability-render:
	@python3 scripts/observability-operator.py render $(observability_common) \
	  --secrets "$${OBSERVABILITY_SECRETS_LITERAL}" --vars "$${OBSERVABILITY_VARS_LITERAL}"

observability-validate:
	@python3 scripts/observability-operator.py validate $(observability_common) \
	  --secrets "$${OBSERVABILITY_SECRETS_LITERAL}" --vars "$${OBSERVABILITY_VARS_LITERAL}"

observability-status:
	@python3 scripts/observability-operator.py status $(observability_common)

observability-drill:
	@python3 scripts/observability-operator.py drill $(observability_common) \
	  --confirm-notification --silence-owner "$${OBSERVABILITY_SILENCE_OWNER_LITERAL}"

observability-deploy:
	@python3 scripts/observability-operator.py deploy $(observability_common) \
	  --secrets "$${OBSERVABILITY_SECRETS_LITERAL}" --vars "$${OBSERVABILITY_VARS_LITERAL}" \
	  --confirm

observability-silence-create:
	@python3 scripts/observability-operator.py silence-create $(observability_common) \
	  --silence-owner "$${OBSERVABILITY_SILENCE_OWNER_LITERAL}" \
	  --request "$${OBSERVABILITY_SILENCE_REQUEST_LITERAL}" --confirm

observability-silence-delete:
	@python3 scripts/observability-operator.py silence-delete $(observability_common) \
	  --silence-owner "$${OBSERVABILITY_SILENCE_OWNER_LITERAL}" \
	  --silence-id "$${OBSERVABILITY_SILENCE_ID_LITERAL}" --confirm

observability-rotate:
	@python3 scripts/observability-operator.py rotate $(observability_common) \
	  --secrets "$${OBSERVABILITY_SECRETS_LITERAL}" --vars "$${OBSERVABILITY_VARS_LITERAL}" \
	  --confirm

observability-rollback:
	@python3 scripts/observability-operator.py rollback $(observability_common) \
	  --secrets "$${OBSERVABILITY_SECRETS_LITERAL}" --vars "$${OBSERVABILITY_VARS_LITERAL}" \
	  --rollback-manifest "$${OBSERVABILITY_ROLLBACK_MANIFEST_LITERAL}" \
	  --confirm

observability-remove:
	@python3 scripts/observability-operator.py remove $(observability_common) \
	  --vars "$${OBSERVABILITY_VARS_LITERAL}" --confirm

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
	./scripts/test-vpnd-mutants.sh

tf-policy:
	@for p in upcloud hetzner vultr scaleway; do \
	  echo "== $$p =="; \
	  terraform -chdir=terraform/providers/$$p init -backend=false >/dev/null && \
	  terraform -chdir=terraform/providers/$$p test || exit 1; \
	done
	conftest verify --rego-version v0 -p terraform/policy/
