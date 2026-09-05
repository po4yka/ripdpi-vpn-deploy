#!/usr/bin/env bash
# Safe `make destroy`. Asks for explicit confirmation twice, removes the
# `prevent_destroy` lifecycle block in a temp override file (so the source
# stays clean), runs `terraform destroy`, removes the override, and clears
# the inventory.
#
# Required env: PROVIDER, ENV. `--non-interactive` is restricted to ci-* ENV
# values and exists only for short-lived CI nodes.
set -euo pipefail

NON_INTERACTIVE=false
STAGING_MANIFEST=""
POST_DESTROY_EVIDENCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --staging-manifest)
      [[ $# -ge 2 ]] || { echo "--staging-manifest requires a path" >&2; exit 2; }
      STAGING_MANIFEST="$2"
      shift
      ;;
    --post-destroy-evidence)
      [[ $# -ge 2 ]] || { echo "--post-destroy-evidence requires a path" >&2; exit 2; }
      POST_DESTROY_EVIDENCE="$2"
      shift
      ;;
    *) echo "usage: $0 [--non-interactive] [--staging-manifest PATH --post-destroy-evidence PATH]" >&2; exit 2 ;;
  esac
  shift
done

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$PROVIDER" in
  upcloud) DESTROY_RESOURCE="upcloud_server.vpn" ;;
  hetzner) DESTROY_RESOURCE="hcloud_server.vpn" ;;
  vultr) DESTROY_RESOURCE="vultr_instance.vpn" ;;
  scaleway) DESTROY_RESOURCE="scaleway_instance_server.vpn" ;;
  *) echo "unsupported PROVIDER for destroy: $PROVIDER" >&2; exit 2 ;;
esac

TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
INV="${REPO_ROOT}/ansible/inventory/generated.ini"
OVERRIDE="${TF_DIR}/_destroy_override.tf"
TFVARS="${TF_DIR}/environments/${ENV}.tfvars"
STAGING_GUARD="${REPO_ROOT}/scripts/staging-cleanup-guard.py"
STAGING_GUARDED=false

if [[ "$ENV" =~ ^ci-staging-[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
  STAGING_GUARDED=true
  if [[ "$PROVIDER" != "upcloud" && "$PROVIDER" != "vultr" ]]; then
    echo "UUID-bound staging cleanup supports only upcloud or vultr" >&2
    exit 2
  fi
  if [[ "$PROVIDER" == "vultr" ]]; then
    STAGING_GUARD="${REPO_ROOT}/scripts/vultr-staging-cleanup-guard.py"
  fi
  if [[ -z "$STAGING_MANIFEST" || -z "$POST_DESTROY_EVIDENCE" ]]; then
    echo "ci-staging cleanup requires --staging-manifest and --post-destroy-evidence" >&2
    exit 2
  fi
elif [[ -n "$STAGING_MANIFEST" || -n "$POST_DESTROY_EVIDENCE" ]]; then
  echo "staging cleanup arguments require a ci-staging-* environment" >&2
  exit 2
fi

if [[ -e "$OVERRIDE" ]]; then
  echo "error: ${OVERRIDE} already exists." >&2
  echo "A previous destroy crashed before its cleanup ran, so prevent_destroy" >&2
  echo "is currently disabled for this root. Inspect the file, confirm no" >&2
  echo "terraform run is in progress, and remove it manually before retrying:" >&2
  echo "  rm ${OVERRIDE}" >&2
  exit 1
fi

if [[ ! -d "$TF_DIR" ]]; then
  echo "no terraform root: $TF_DIR" >&2
  exit 1
fi

if [[ ! -f "$TFVARS" ]]; then
  echo "no tfvars: $TFVARS" >&2
  exit 1
fi

if [[ "$NON_INTERACTIVE" == "true" && ! "$ENV" =~ ^ci-[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
  echo "--non-interactive is restricted to validated ci-* environments" >&2
  exit 2
fi

PRIVATE_PLAN_DIR=""
PLAN_PATH="${ENV}.destroy.tfplan"
PLAN_INPUT="$PLAN_PATH"
PLAN_FD=""
STAGING_EVIDENCE_RESERVED=false
APPLY_STARTED=false
cleanup() {
  rm -f "$OVERRIDE"
  if [[ -n "$PRIVATE_PLAN_DIR" ]]; then
    rm -rf "$PRIVATE_PLAN_DIR"
  fi
  if [[ "$STAGING_EVIDENCE_RESERVED" == "true" && "$APPLY_STARTED" != "true" ]]; then
    "$STAGING_GUARD" release-evidence \
      --manifest "$STAGING_MANIFEST" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV" \
      || echo "warning: staging evidence reservation requires manual inspection" >&2
  fi
}
trap cleanup EXIT

cat <<EOF

DANGER: this will destroy the VPS and firewall managed by:
  ${TF_DIR}
  ENV=${ENV}

Existing clients on this node will lose connectivity. The Terraform state
file will record the destruction; back it up first if you want to keep an
audit trail.

EOF

expected="$(grep -E '^server_name' "$TFVARS" | head -1 | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')"
if [[ "$NON_INTERACTIVE" == "true" ]]; then
  echo "CI destroy authorization accepted for ${ENV} (${expected})"
else
  read -r -p "Type the server hostname to confirm (Ctrl-C to abort): " typed
  if [[ "$typed" != "$expected" ]]; then
    echo "hostname mismatch (expected: $expected) — aborting" >&2
    exit 1
  fi

  read -r -p "Type DESTROY to proceed: " word
  if [[ "$word" != "DESTROY" ]]; then
    echo "aborted"
    exit 1
  fi
fi

if [[ "$STAGING_GUARDED" == "true" ]]; then
  if [[ "$PROVIDER" == "vultr" ]]; then
    RECOVERY_RESULT="$("$STAGING_GUARD" recover-evidence \
      --manifest "$STAGING_MANIFEST" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV")"
    if [[ "$RECOVERY_RESULT" == "staging provider absence verified" ]]; then
      env ENV="$ENV" PROVIDER="$PROVIDER" \
        "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
          --action staging-destroy \
          --env "$ENV" \
          --provider "$PROVIDER" \
          --note exact-owned-resources-absent
      echo "previous staging destroy absence verified"
      exit 0
    fi
  fi
  "$STAGING_GUARD" authorize-reserve-evidence \
    --manifest "$STAGING_MANIFEST" \
    --evidence-output "$POST_DESTROY_EVIDENCE" \
    --expected-provider "$PROVIDER" \
    --expected-environment "$ENV"
  STAGING_EVIDENCE_RESERVED=true
  PRIVATE_PLAN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/vpn-staging-cleanup.XXXXXX")"
  PRIVATE_PLAN_DIR="$(CDPATH='' cd -- "$PRIVATE_PLAN_DIR" && pwd -P)"
  chmod 0700 "$PRIVATE_PLAN_DIR"
  umask 077
  PLAN_PATH="${PRIVATE_PLAN_DIR}/destroy.tfplan"
fi

# Drop a temporary override that disables prevent_destroy. Terraform merges
# *_override.tf into the working configuration; this lets us destroy without
# editing the canonical main.tf (which would dirty the working tree).
cat > "$OVERRIDE" <<EOF
# Generated by scripts/destroy.sh — removed automatically when destroy completes.
# Disables prevent_destroy on the VPS so terraform destroy can proceed.
resource "${DESTROY_RESOURCE%%.*}" "${DESTROY_RESOURCE#*.}" {
  lifecycle {
    prevent_destroy = false
  }
}
EOF

# Plan destroy first so the operator sees the diff
env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" plan -destroy \
  -var-file="environments/${ENV}.tfvars" \
  -out="$PLAN_PATH"

if [[ "$STAGING_GUARDED" == "true" ]]; then
  if [[ ! -f "$PLAN_PATH" || -L "$PLAN_PATH" ]]; then
    echo "staging destroy plan is not a private regular file" >&2
    exit 1
  fi
  chmod 0600 "$PLAN_PATH"
  exec {PLAN_FD}<"$PLAN_PATH"
  rm -f "$PLAN_PATH"
  PLAN_INPUT="/dev/fd/${PLAN_FD}"
  if [[ "$PROVIDER" == "vultr" ]]; then
    "$STAGING_GUARD" validate-plan \
      --manifest "$STAGING_MANIFEST" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --fd-number "$PLAN_FD" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV"
  else
    PLAN_VIEW="${PRIVATE_PLAN_DIR}/destroy-plan.json"
    env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" show -json "$PLAN_INPUT" > "$PLAN_VIEW"
    chmod 0600 "$PLAN_VIEW"
    "$STAGING_GUARD" validate-plan \
      --manifest "$STAGING_MANIFEST" \
      --plan-view "$PLAN_VIEW" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV"
  fi
  "$STAGING_GUARD" rewind-plan-fd --fd-number "$PLAN_FD"
else
  if ! env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" show -json "$PLAN_INPUT" \
    | jq -e --arg resource "$DESTROY_RESOURCE" '
        any(.resource_changes[]?; .address == $resource and (.change.actions | index("delete")))
      ' >/dev/null; then
    echo "destroy plan does not delete expected resource ${DESTROY_RESOURCE}; refusing apply" >&2
    exit 1
  fi
fi

if [[ "$NON_INTERACTIVE" != "true" ]]; then
  read -r -p "Apply this destroy plan? [yes/NO]: " final
  if [[ "$final" != "yes" ]]; then
    echo "aborted"
    exit 1
  fi
fi

if [[ "$STAGING_GUARDED" == "true" ]]; then
  if [[ "$PROVIDER" == "vultr" ]]; then
    "$STAGING_GUARD" mark-apply-started \
      --manifest "$STAGING_MANIFEST" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --fd-number "$PLAN_FD" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV"
  else
    "$STAGING_GUARD" mark-apply-started \
      --manifest "$STAGING_MANIFEST" \
      --evidence-output "$POST_DESTROY_EVIDENCE" \
      --expected-provider "$PROVIDER" \
      --expected-environment "$ENV"
  fi
fi
APPLY_STARTED=true
env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" apply "$PLAN_INPUT"
if [[ -n "$PLAN_FD" ]]; then
  exec {PLAN_FD}<&-
fi

if [[ "$STAGING_GUARDED" == "true" ]]; then
  if [[ "$PROVIDER" == "upcloud" ]]; then
    STAGING_VERIFY="verify-upcloud-absence"
  else
    STAGING_VERIFY="verify-vultr-absence"
  fi
  "$STAGING_GUARD" "$STAGING_VERIFY" \
    --manifest "$STAGING_MANIFEST" \
    --evidence-output "$POST_DESTROY_EVIDENCE" \
    --expected-provider "$PROVIDER" \
    --expected-environment "$ENV"
  env ENV="$ENV" PROVIDER="$PROVIDER" \
    "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
      --action staging-destroy \
      --env "$ENV" \
      --provider "$PROVIDER" \
      --note exact-owned-resources-absent
fi

if [[ "$STAGING_GUARDED" != "true" ]]; then
  rm -f "${TF_DIR}/${PLAN_PATH}"
fi

# Clean inventory and ask if they want a state backup
if [[ "$STAGING_GUARDED" != "true" && -f "$INV" ]]; then
  rm -f "$INV"
  echo "removed $INV"
fi

cat <<'EOF'

Destroyed. The Terraform state still records the destruction; on the next
plan it will be empty. Ensure you've kept an encrypted backup of the
pre-destroy state if you might want to forensically inspect what existed:

    PROVIDER=… ENV=… ./scripts/backup-tf-state.sh

(The backup script reads the current state file. After destroy, the state
shows nothing useful; back up *before* destroy if you need a record.)
EOF
