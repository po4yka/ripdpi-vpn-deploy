# A fresh node accepts a newline-terminated public key. Each test file starts
# from empty state, so this case lives apart from the shared lifecycle state.

mock_provider "scaleway" {}

variables {
  server_name          = "vpn-test"
  zone                 = "pl-waw-1"
  server_type          = "DEV1-S"
  image                = "ubuntu_noble"
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

run "fresh_public_key_with_file_newline" {
  command = apply

  variables {
    admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness\n"
  }

  assert {
    condition     = terraform_data.admin_ssh_public_key.output == sha256(trimspace(var.admin_ssh_public_key))
    error_message = "A fresh node must accept a newline-terminated public key."
  }
}
