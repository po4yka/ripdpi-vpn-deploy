terraform {
  required_version = ">= 1.15, < 2.0"

  required_providers {
    upcloud = {
      source  = "UpCloudLtd/upcloud"
      version = "~> 5.36"
    }
  }
}
