"""Explicit restricted-account admission must have both transport contexts."""

import copy
import pytest
from scripts.sshd_contexts import ContextError, validate_restricted_user_contexts


def contexts():
    return [
        {
            "user": user,
            "host": "node-fixture",
            "addr": "198.51.100.20",
            "laddr": address,
            "lport": 22,
        }
        for user in ("deploy", "ripdpi-awg-evidence")
        for address in ("192.0.2.10", "100.64.0.10")
    ]


def test_explicit_extra_account_requires_both_transport_proofs():
    value = contexts()
    assert (
        validate_restricted_user_contexts(value, ["ripdpi-awg-evidence"], "deploy")
        == value
    )
    with pytest.raises(ContextError, match="missing-restricted-user-contexts"):
        validate_restricted_user_contexts(value[:-1], ["ripdpi-awg-evidence"], "deploy")
    # A context is evidence, never implicit authorization.
    assert validate_restricted_user_contexts(value, [], "deploy") == value


@pytest.mark.parametrize(
    "users",
    [
        ["root"],
        ["deploy"],
        ["ripdpi-awg-evidence"] * 2,
        [["nested"]],
        {"nested": "user"},
        ["user\nMatch all"],
    ],
)
def test_invalid_restricted_accounts_fail_categorically(users):
    with pytest.raises(ContextError):
        validate_restricted_user_contexts(contexts(), copy.deepcopy(users), "deploy")
