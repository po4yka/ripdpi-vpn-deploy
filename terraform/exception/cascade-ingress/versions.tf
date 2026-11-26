terraform {
  required_version = "1.13.10"

  required_providers {
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3"
    }
  }

  backend "local" {
    path = "state/cascade-ingress.tfstate"
  }
}
