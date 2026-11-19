# Third-party data in the subscription-host role

## IPtoASN ip2asn-combined

- Project: <https://iptoasn.com/>, maintained by Frank Denis
- File: `ip2asn-combined.tsv.gz` (IPv4 and IPv6 ranges with AS number, AS registration country and AS description)
- License: [Public Domain Dedication and License (PDDL) 1.0](https://opendatacommons.org/licenses/pddl/1.0/), as stated on the project page
- Use: the optional network hint (`subscription_field_report.network_hint`) answers a client with the AS number and country of its request address. The role copies the pinned file to the host; the ingest reads only the first four columns and never fetches the dataset itself.
- Pin: `dataset_version` (the Last-Modified instant of the download) and `dataset_sha256` in `defaults/main.yml`. `scripts/refresh-ip-asn-dataset.sh` downloads a new copy into the ignored `.cache/ip-asn/` directory and prints the new pin. The file is not committed to this repository.

The PDDL places the data in the public domain and asks for no attribution; this notice records the source and license for review. It is compatible with the repository's BSD 3-Clause license because no license condition applies to the data.
