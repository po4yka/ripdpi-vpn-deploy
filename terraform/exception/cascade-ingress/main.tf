locals {
  attestation_file = var.attestation_file != "" ? abspath(var.attestation_file) : abspath("${path.module}/../../../attestations/cascade-asn-attestation.json")
}

data "external" "attestation" {
  program = [
    "python3",
    "${path.module}/../../../scripts/check-cascade-attestation.py",
    "--attestation",
    local.attestation_file,
  ]
}

resource "terraform_data" "inert_contract" {
  input = {
    activation_mode          = var.activation_mode
    attestation_recheck_date = data.external.attestation.result.next_recheck_date
    server_name              = var.server_name
  }

  lifecycle {
    precondition {
      condition     = var.activation_mode == "INERT_UNATTESTED"
      error_message = "The cascade exception root is not authorized for live activation."
    }

    precondition {
      condition     = data.external.attestation.result.status == "verified"
      error_message = "A fresh measured cascade ASN attestation is required."
    }
  }
}
