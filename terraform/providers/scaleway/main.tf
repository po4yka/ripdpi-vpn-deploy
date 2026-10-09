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

resource "terraform_data" "admin_user" {
  input = var.admin_user
}

resource "terraform_data" "admin_ssh_public_key" {
  input = sha256(trimspace(var.admin_ssh_public_key))
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
      terraform_data.admin_user,
      terraform_data.admin_ssh_public_key,
    ]
    ignore_changes = [
      user_data,
    ]
    # Existing nodes predate the digest guards. Check their retained bootstrap
    # identity before recording new guard inputs, without comparing helper data.
    postcondition {
      condition = try(
        yamldecode(self.user_data["cloud-init"]).users[1].name == var.admin_user
        && [for key in tolist(yamldecode(self.user_data["cloud-init"]).users[1].ssh_authorized_keys) : trimspace(key)] == [trimspace(var.admin_ssh_public_key)],
        false,
      )
      error_message = "Bootstrap administrator identity differs from the requested username or key; provision a replacement node instead of adopting divergent identity."
    }
  }
}
