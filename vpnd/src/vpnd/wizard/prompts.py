"""Terminal-bound choice, input and confirmation prompts."""

import sys


def terminal_line(label):
    # dialoguer uses Term.stderr() and refuses an unattended stderr stream.
    # A piped stdin is never confirmation authority: console falls back to
    # the controlling terminal instead of consuming piped default answers.
    if not sys.stderr.isatty():
        raise OSError("not a terminal")
    if sys.stdin.isatty():
        handle = sys.stdin
        owned = False
    else:
        handle = open("/dev/tty", encoding="utf-8")
        owned = True
    try:
        print(label, end="", file=sys.stderr, flush=True)
        response = handle.readline()
        if not response:
            raise EOFError("terminal input closed")
        return response.rstrip("\r\n")
    finally:
        if owned:
            handle.close()


def choose(label, options, default=0):
    if not options:
        raise ValueError("choose() called with no options")
    selected = min(max(default, 0), len(options) - 1)
    if not sys.stderr.isatty():
        raise OSError("not a terminal")
    print(label, file=sys.stderr)
    for index, value in enumerate(options):
        print(f"  {index + 1}. {value}", file=sys.stderr)
    while True:
        response = terminal_line(f"Choice [{selected + 1}]: ").strip()
        if not response:
            return selected
        if response.isdigit() and 1 <= int(response) <= len(options):
            return int(response) - 1


def prompt(label, default=None):
    while True:
        response = terminal_line(label + (f" [{default}] " if default is not None else ": "))
        if response:
            return response
        if default is not None:
            return default


def confirm(label, default=True):
    while True:
        response = terminal_line(label + (" [Y/n] " if default else " [y/N] ")).strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
