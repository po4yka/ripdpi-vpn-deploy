locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user                  = var.admin_user
    admin_ssh_public_key        = var.admin_ssh_public_key
    ssh_port                    = var.ssh_port
    build_env                   = var.build_env
    bootstrap_ssh_ownership_b64 = filebase64("${path.module}/../../shared/bootstrap-sshd-ownership.py")
  })

  # Labels are intentionally minimal to limit provider-side fingerprinting.
  # role and provisioner are omitted — they identify the workload type to
  # a cloud provider's analytics pipeline. managed_by and env are kept for
  # cost-allocation and operational filtering.
  base_labels = merge(var.labels, {
    managed_by = "terraform"
    env        = var.build_env
  })
}

resource "terraform_data" "ssh_port" {
  input = var.ssh_port
}

resource "hcloud_ssh_key" "admin" {
  name       = "${var.server_name}-${var.admin_user}"
  public_key = var.admin_ssh_public_key
  labels     = local.base_labels
}

resource "hcloud_server" "vpn" {
  name        = var.server_name
  location    = var.location
  server_type = var.server_type
  image       = var.image

  backups   = var.enable_backups
  ssh_keys  = [hcloud_ssh_key.admin.id]
  user_data = local.user_data
  labels    = local.base_labels

  public_net {
    ipv4_enabled = true
    ipv6_enabled = var.enable_ipv6
  }

  lifecycle {
    prevent_destroy = true
    replace_triggered_by = [
      terraform_data.ssh_port,
    ]
    ignore_changes = [
      user_data,
    ]
  }
}

resource "hcloud_floating_ip" "honeypot_ipv4" {
  count = var.additional_public_ip ? 1 : 0

  type          = "ipv4"
  name          = "${var.server_name}-honeypot"
  home_location = var.location
  server_id     = hcloud_server.vpn.id
  labels        = local.base_labels
}
