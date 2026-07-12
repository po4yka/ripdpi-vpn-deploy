package terraform.policy.no_secrets_in_user_data

# cloud_init_user_data_contains_no_secrets
#
# Deny if any server resource's user_data (cloud-init) contains a plaintext
# secret-like pattern: a line-start key/value pair matching
#   (password|token|api_key|secret)\s*[:=]\s*[^\s]{6,}
#
# "key" is intentionally excluded from the keyword list — it is too generic
# and produces false-positives on valid cloud-init ssh_authorized_keys blocks
# (e.g. "ssh_authorized_keys: ssh-ed25519 AAAA..."). Use api_key to catch
# real API key leaks.
#
# Placeholder substitutions (e.g. "{{ admin_user }}") produced by Terraform's
# templatefile() are acceptable; only literal non-whitespace values of 6+
# characters trigger the rule.
#
# Applies to: upcloud_server, hcloud_server, vultr_instance, scaleway_instance_server

server_resource_types := {
  "upcloud_server",
  "hcloud_server",
  "vultr_instance",
  "scaleway_instance_server",
}

# Regex matches literal secret assignments in plaintext.
# Matches: password/token/api_key/secret followed by : or = and 6+ non-space chars,
# where the keyword appears at the start of the line (optional leading whitespace).
# This avoids false-positives on SSH public-key lines such as:
#   ssh_authorized_keys:
#     - ssh-ed25519 AAAA...
# because those lines begin with "ssh_authorized_keys" or "- ssh-", not a secret keyword.
# The bare word "key" is intentionally excluded — it is too generic and matches
# ssh_authorized_keys / ssh-ed25519 key material. Use api_key instead.
secret_pattern := `(?im)^\s*(password|token|api_key|secret)\s*[:=]\s*[^\s]{6,}`

deny[msg] {
  rc := input.resource_changes[_]
  server_resource_types[rc.type]
  user_data := rc.change.after.user_data
  is_string(user_data)

  # user_data present and non-null
  user_data != null
  user_data != ""

  regex.match(secret_pattern, user_data)

  msg := sprintf(
    "resource %q (%s): user_data appears to contain a plaintext secret (matched pattern %q); use templatefile() placeholders or SOPS-encrypted values passed via Ansible",
    [rc.address, rc.type, secret_pattern],
  )
}

deny[msg] {
  rc := input.resource_changes[_]
  server_resource_types[rc.type]
  user_data_map := rc.change.after.user_data
  is_object(user_data_map)
  some key
  user_data := user_data_map[key]
  is_string(user_data)
  regex.match(secret_pattern, user_data)

  msg := sprintf(
    "resource %q (%s): user_data[%q] appears to contain a plaintext secret (matched pattern %q); use templatefile() placeholders or SOPS-encrypted values passed via Ansible",
    [rc.address, rc.type, key, secret_pattern],
  )
}
