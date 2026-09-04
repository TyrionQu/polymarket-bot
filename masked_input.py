"""Reads one line of input, echoing '*' per character instead of the real characters."""

import sys


def masked_input(prompt: str) -> str:
    print(prompt, end="", flush=True)

    if not sys.stdin.isatty():
        # No real terminal to mask against (e.g. piped input during scripting/testing).
        return input()

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":  # Ctrl-C
                raise KeyboardInterrupt
            if ch in ("\x7f", "\x08"):  # backspace/delete
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            chars.append(ch)
            sys.stdout.write("*")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()
    return "".join(chars)
