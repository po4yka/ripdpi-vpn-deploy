terraform {
  required_version = ">= 1.15, < 2.0"

  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = "~> 2.31"
    }
  }
}
