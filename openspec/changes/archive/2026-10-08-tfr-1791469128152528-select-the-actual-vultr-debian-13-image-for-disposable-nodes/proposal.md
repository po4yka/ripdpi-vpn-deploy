# Change: Select the actual Vultr Debian 13 image

Task ID: `TFR-1791469128152528`

## Why

The Vultr examples identify OS 2284 as Debian 13, but the provider creates
Ubuntu 24.04 with that ID. The current provider catalog identifies Debian 13
x64 as 2625, which the Terraform allowlist rejects before creation. This
blocks disposable nodes from using the intended supported base image.

## What Changes

- Allow the verified Debian 13 image and select it in the two examples.
- Correct the misleading approved-image labels and cover accepted and rejected IDs.
- BREAKING: reject OS 1869 (Rocky Linux 9), previously mislabeled Ubuntu 24.04;
  runtime provisioning supports Debian and Ubuntu.
- Existing nodes are never changed by updating an example or the allowlist.

## Capabilities

### New Capabilities

- `vultr-base-image-selection`: select the intended approved base image by its provider ID.

### Modified Capabilities

- None.

## Impact

- Terraform Vultr validation, examples, mock-provider tests and provider notes.
- No provider version, runtime firewall, secret or CLI changes.
- Example deployments select Debian 13 instead of the previously mislabeled Ubuntu image.
