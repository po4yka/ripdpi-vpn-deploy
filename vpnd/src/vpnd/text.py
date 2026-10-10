"""Unicode White_Space trimming and LF-delimited text contracts."""

# Python's default strip additionally consumes U+001C..U+001F. Those control
# separators are not Unicode White_Space and must remain visible to validation.
WHITE_SPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def trim_whitespace(value):
    return value.strip(WHITE_SPACE)


def lf_lines(value):
    """Split LF/CRLF lines without treating other separators as line breaks."""
    chunks = value.split("\n")
    terminated = chunks[-1] == ""
    if terminated:
        chunks.pop()
    return [
        chunk[:-1] if chunk.endswith("\r") and (terminated or index < len(chunks) - 1) else chunk
        for index, chunk in enumerate(chunks)
    ]
