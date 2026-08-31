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

resource "upcloud_server" "vpn" {
  hostname = var.server_name
  zone     = var.zone
  plan     = var.plan

  # UpCloud's Public & Utility firewall is stateless. Keep it disabled on a
  # fresh node until cloud-init and Ansible have installed and verified the
  # guest stateful firewall; promotion is then an explicit in-place update.
  firewall = var.enable_provider_firewall

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
    replace_triggered_by = [
      terraform_data.ssh_port,
    ]
    ignore_changes = [
      user_data,
      template[0].title,
    ]
  }
}
