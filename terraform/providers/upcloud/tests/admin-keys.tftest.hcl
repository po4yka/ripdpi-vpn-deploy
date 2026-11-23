# The admin key list reaches the provider login block as its first entry only, so
# adding or revoking a later key (for example the CI key) never replaces the node.

mock_provider "upcloud" {}

variables {
  server_name           = "vpn-test"
  zone                  = "fi-hel1"
  plan                  = "1xCPU-2GB"
  storage_template      = "01000000-0000-4000-8000-000020030200"
  admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness"]
  allowed_ssh_cidrs     = ["203.0.113.42/32"]
  public_listeners = [
    { name = "xray", protocol = "tcp", port = 443 },
  ]
}

run "single_key_list_registers_that_key" {
  command = plan

  assert {
    condition     = length(upcloud_server.vpn.login[0].keys) == 1
    error_message = "A single-entry list must register that key with the provider."
  }
}

run "second_key_is_not_a_provider_change" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness", "ssh-ed25519 AAAACIKEY ci@harness"]
  }

  assert {
    condition     = length(upcloud_server.vpn.login[0].keys) == 1
    error_message = "Only the first key may reach the provider login block; later keys flow through cloud-init and baseline."
  }
}

run "duplicate_keys_refused" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY a", "ssh-ed25519 AAAATESTKEY b"]
  }

  expect_failures = [var.admin_ssh_public_keys]
}

run "empty_list_refused" {
  command = plan

  variables {
    admin_ssh_public_keys = []
  }

  expect_failures = [var.admin_ssh_public_keys]
}

run "multiline_key_refused" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY a\nruncmd: [x]"]
  }

  expect_failures = [var.admin_ssh_public_keys]
}

run "key_without_comment_separator_refused" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY;junk"]
  }

  expect_failures = [var.admin_ssh_public_keys]
}

run "apostrophe_in_comment_refused" {
  command = plan

  variables {
    admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY operator's laptop"]
  }

  expect_failures = [var.admin_ssh_public_keys]
}
