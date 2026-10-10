import sys
from .. import version


def warn_on_skew(name, host):
    if host.deployed_with is not None and host.deployed_with != version():
        print(
            f"warn: host '{name}' deployed with vpnd {host.deployed_with}, current CLI is {version()} — review runbook before mutation",
            file=sys.stderr,
        )
