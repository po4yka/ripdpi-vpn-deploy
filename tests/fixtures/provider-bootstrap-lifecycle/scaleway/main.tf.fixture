locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user                  = var.admin_user
    admin_ssh_public_key        = var.admin_ssh_public_key
    ssh_port                    = var.ssh_port
    build_env                   = var.build_env
    bootstrap_ssh_ownership_b64 = filebase64("${path.module}/../../shared/bootstrap-sshd-ownership.py")
  })

  base_tags = distinct(concat(
    ["terraform", var.build_env],
    [for key, value in var.labels : "${key}:${value}"],
  ))
}

resource "terraform_data" "ssh_port" {
  input = var.ssh_port
}

resource "scaleway_instance_ip" "ipv4" {
  count = 1

  type = "routed_ipv4"
  zone = var.zone
  tags = local.base_tags
}

resource "scaleway_instance_ip" "ipv6" {
  count = var.enable_ipv6 ? 1 : 0

  type = "routed_ipv6"
  zone = var.zone
  tags = local.base_tags
}

resource "scaleway_instance_ip" "honeypot_ipv4" {
  count = var.additional_public_ip ? 1 : 0

  type = "routed_ipv4"
  zone = var.zone
  tags = concat(local.base_tags, ["secondary"])
}

resource "scaleway_instance_server" "vpn" {
  name  = var.server_name
  zone  = var.zone
  type  = var.server_type
  image = var.image
  ip_ids = concat(
    [scaleway_instance_ip.ipv4[0].id],
    scaleway_instance_ip.ipv6[*].id,
    scaleway_instance_ip.honeypot_ipv4[*].id,
  )
  security_group_id = scaleway_instance_security_group.vpn.id
  tags              = local.base_tags
  user_data = {
    cloud-init = local.user_data
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
