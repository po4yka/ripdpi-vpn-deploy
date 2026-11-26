terraform {
  required_version = "1.13.10"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.88"
    }
  }
}
