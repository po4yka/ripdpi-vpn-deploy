# Operator inputs for the public checkout. The public checkout's ignored .fleet.mk
# includes this file by absolute path: include /absolute/path/to/ops/fleet.mk
OPS_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

TFVARS_ROOT = $(OPS_ROOT)/config/tfvars
TF_BACKEND_ROOT = $(OPS_ROOT)/config/backend
ANSIBLE_INVENTORY = $(OPS_ROOT)/config/inventories/$(ENV).ini
SOPS_FILE = $(OPS_ROOT)/config/$(ENV).secrets.sops.yaml
