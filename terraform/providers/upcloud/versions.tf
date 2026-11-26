terraform {
  required_version = "1.13.10"

  required_providers {
    upcloud = {
      source  = "UpCloudLtd/upcloud"
      version = "~> 5.48"
    }
  }
}
