"""Shared bounded timing contract for the local SSH transaction controllers."""

RPC_TIMEOUT_SECONDS = 45
SFTP_TIMEOUT_SECONDS = 30
# The evaluator owns a 600-second child deadline; the wrapper gets bounded
# cleanup/serialization headroom before the remote transaction can expire.
PROMOTION_PROOF_TIMEOUT_SECONDS = 615
POST_PREPARE_RPC_COUNT = 5
POST_PREPARE_SFTP_COUNT = 2
TRANSACTION_HEADROOM_SECONDS = 60
TRANSACTION_TIMEOUT_SECONDS = (
    PROMOTION_PROOF_TIMEOUT_SECONDS
    + POST_PREPARE_RPC_COUNT * RPC_TIMEOUT_SECONDS
    + POST_PREPARE_SFTP_COUNT * SFTP_TIMEOUT_SECONDS
    + TRANSACTION_HEADROOM_SECONDS
)
