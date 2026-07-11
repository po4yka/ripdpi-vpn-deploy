locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user_yaml           = yamlencode(var.admin_user)
    admin_ssh_public_key_yaml = yamlencode(var.admin_ssh_public_key)
    build_id_content_yaml     = indent(4, yamlencode(format("provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=%s\n", var.build_env)))
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

resource "upcloud_server" "vpn" {
  hostname = var.server_name
  zone     = var.zone
  plan     = var.plan

  cpu = null
  mem = null

  metadata  = true
  user_data = local.user_data

  template {
    storage = var.storage_template
    size    = var.storage_size_gb
    title   = "${var.server_name}-root"

    dynamic "backup_rule" {
      for_each = var.enable_backups ? [1] : []
      content {
        interval  = "daily"
        time      = "0300"
        retention = 7
      }
    }
  }

  network_interface {
    type              = "public"
    ip_address_family = "IPv4"
  }

  dynamic "network_interface" {
    for_each = var.enable_ipv6 ? [1] : []
    content {
      type              = "public"
      ip_address_family = "IPv6"
    }
  }

  # Optional secondary public interface for honeypot / per-IP isolation.
  # Enable via `additional_public_ip = true` in the env tfvars; the
  # honeypot role binds to this address via group_vars when populated.
  dynamic "network_interface" {
    for_each = var.additional_public_ip ? [1] : []
    content {
      type              = "public"
      ip_address_family = "IPv4"
    }
  }

  network_interface {
    type = "utility"
  }

  login {
    user            = var.admin_user
    keys            = [var.admin_ssh_public_key]
    create_password = false
  }

  labels = local.base_labels

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      user_data,
      template[0].title,
    ]
  }
}
