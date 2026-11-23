# Asserts on the Scaleway server resources and inventory-facing outputs.

mock_provider "scaleway" {}

variables {
  server_name           = "vpn-test"
  zone                  = "pl-waw-1"
  server_type           = "DEV1-S"
  image                 = "ubuntu_noble"
  admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness"]
  allowed_ssh_cidrs     = ["203.0.113.42/32"]
  build_env             = "test"
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
    condition     = terraform_data.admin_ssh_public_key.output == sha256("ssh-ed25519 AAAATESTKEY")
    error_message = "Creation must record the administrator public-key digest guard."
  }
}

run "unchanged_identity" {
  command = plan

  assert {
    condition     = scaleway_instance_server.vpn.id != ""
    error_message = "Unchanged administrator identity must retain the node."
  }
}

run "same_public_key_with_file_newline" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness\n"]
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256("ssh-ed25519 AAAATESTKEY")
    error_message = "The same key with a file newline must retain its bootstrap identity."
  }
}

# A migrated tfvars file lists the existing key alone; the plan must not touch the node.
run "single_key_list_keeps_node" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness"]
  }

  assert {
    condition     = scaleway_instance_server.vpn.id != ""
    error_message = "A single-entry key list must retain the node."
  }
}

# Adding a key (for example the CI key) after the first entry updates cloud-init and
# baseline only. The provider receives the first key, so the node stays.
run "second_key_keeps_node" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness", "ssh-ed25519 AAAACIKEY ci@harness"]
  }

  assert {
    condition     = scaleway_instance_server.vpn.id != ""
    error_message = "Adding a second key must retain the node."
  }
}

run "edited_comment_keeps_identity" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY renamed label"]
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256("ssh-ed25519 AAAATESTKEY")
    error_message = "Editing a key comment must retain the node identity."
  }
}
