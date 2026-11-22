terraform {
  required_version = "1.13.9"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.88"
    }
  }
}
