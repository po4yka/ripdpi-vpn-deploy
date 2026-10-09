# Asserts on the Vultr server resources and inventory-facing outputs.

mock_provider "vultr" {}

variables {
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
  public_listeners = [
    { name = "xray", protocol = "tcp", port = 443 },
    { name = "xray-fallback", protocol = "tcp", port = 2053 },
    { name = "nginx-xhttp", protocol = "tcp", port = 8443 },
    { name = "hysteria", protocol = "udp", port = 443 },
    { name = "amneziawg", protocol = "udp", port = 51820 },
  ]
}

# Shared test state exercises an actual mock apply followed by a plan.
run "create_node" {
  command = apply

  assert {
    condition     = terraform_data.admin_user.output == var.admin_user
    error_message = "Creation must record the administrator username guard."
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256(trimspace(var.admin_ssh_public_key))
    error_message = "Creation must record the administrator public-key digest guard."
  }
}

run "unchanged_identity" {
  command = plan

  assert {
    condition     = vultr_instance.vpn.id != ""
    error_message = "Unchanged administrator identity must retain the node."
  }
}

run "same_public_key_with_file_newline" {
  command = plan

  variables {
    admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness\n"
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256(trimspace(var.admin_ssh_public_key))
    error_message = "The same key with a file newline must retain its bootstrap identity."
  }
}

run "fresh_public_key_with_file_newline" {
  command   = apply
  state_key = "newline-key"

  variables {
    admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness\n"
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256(trimspace(var.admin_ssh_public_key))
    error_message = "A fresh node must accept a newline-terminated public key."
  }
}
