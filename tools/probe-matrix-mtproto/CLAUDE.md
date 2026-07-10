# probe-matrix-mtproto — no-login MTProxy connectivity helper

## Design decisions

This helper uses gotd's MTProxy resolver and Telegram test application identity to perform an MTProto key exchange plus `help.getNearestDC` without creating or reading a user session. Its only interface is one request JSON on stdin and one redacted result JSON on stdout.

## What's done well

- The MTProxy secret never appears in argv, environment variables, logs, or output.
- Connection logic is injected in tests, so unit tests never contact Telegram.

## Pitfalls

- Keep `github.com/gotd/td` pinned and commit `go.sum` changes with the source.
- Never add user login, bot tokens, messages, contacts, or persistent sessions to this measurement helper.
