terraform {
  required_version = "1.13.9"

  required_providers {
    upcloud = {
      source  = "UpCloudLtd/upcloud"
      version = "~> 5.48"
    }
  }
}
