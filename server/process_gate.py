"""Windows launch gate: start descendants only after assignment to a Job Object."""
import json
import subprocess
import sys


if __name__ == "__main__":
    command = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
    sys.exit(subprocess.call(command, stdin=subprocess.DEVNULL))
