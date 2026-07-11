locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user_yaml           = yamlencode(var.admin_user)
    admin_ssh_public_key_yaml = yamlencode(var.admin_ssh_public_key)
    build_id_content_yaml     = indent(4, yamlencode(format("provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=%s\n", var.build_env)))
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

resource "vultr_ssh_key" "admin" {
  name    = "${var.server_name}-${var.admin_user}"
  ssh_key = var.admin_ssh_public_key
}

resource "vultr_firewall_group" "vpn" {
  description = "${var.server_name} vpn ingress"
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
