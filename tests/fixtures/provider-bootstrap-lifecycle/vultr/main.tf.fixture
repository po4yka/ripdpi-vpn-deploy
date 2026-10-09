locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user                  = var.admin_user
    admin_ssh_public_key        = var.admin_ssh_public_key
    ssh_port                    = var.ssh_port
    build_env                   = var.build_env
    bootstrap_ssh_ownership_b64 = filebase64("${path.module}/../../shared/bootstrap-sshd-ownership.py")
  })

  # Tags are intentionally minimal to limit provider-side fingerprinting.
  # "vpn" and "ansible" are omitted — they identify the workload type to
  # a cloud provider's analytics pipeline. "terraform" (managed_by) and
  # build_env are kept for cost-allocation and operational filtering.
  base_tags = distinct(concat(
    ["terraform", var.build_env],
    [for key, value in var.labels : "${key}:${value}"],
  ))
}

resource "terraform_data" "ssh_port" {
  input = var.ssh_port
}

resource "vultr_ssh_key" "admin" {
  name    = "${var.server_name}-${var.admin_user}"
  ssh_key = var.admin_ssh_public_key
}

resource "vultr_firewall_group" "vpn" {
  description = "${var.server_name} vpn ingress"

  lifecycle {
    precondition {
      condition     = length(local.effective_public_listeners) > 0
      error_message = "public_listeners resolves to an empty set; set public_listeners explicitly or opt into the historical defaults with use_legacy_public_listeners = true."
    }
  }
}

resource "vultr_instance" "vpn" {
  region = var.region
  plan   = var.plan
  os_id  = var.os_id

  label             = var.server_name
  hostname          = var.server_name
  ssh_key_ids       = [vultr_ssh_key.admin.id]
  firewall_group_id = vultr_firewall_group.vpn.id
  user_data         = local.user_data
  enable_ipv6       = var.enable_ipv6
  backups           = var.enable_backups ? "enabled" : "disabled"
  tags              = local.base_tags

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

resource "vultr_instance_ipv4" "honeypot" {
  count = var.additional_public_ip ? 1 : 0

  instance_id = vultr_instance.vpn.id
  # Vultr requires a reboot to converge the added address into the guest
  # network configuration. Inventory verifies the address before publishing it.
  reboot = true
}
