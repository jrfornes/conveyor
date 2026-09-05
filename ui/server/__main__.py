#!/usr/bin/env python3
"""Run the Conveyor UI API server.

Usage:
  PYTHONPATH=. python3 -m ui.server --root /path/to/repo [--port 8765]
  PYTHONPATH=. python3 -m ui.server --demo [--port 8765]
"""
import argparse
import atexit
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from ui.server import demo, state  # noqa: E402
from ui.server.httpd import DIST, serve  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Conveyor UI localhost server")
    p.add_argument("--root", help="Target repo root (default: CONVEYOR_UI_ROOT or git root)")
    p.add_argument("--demo", action="store_true",
                   help="Throwaway fixture repo (queued task, parked task, inbox item); deleted on exit")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    if args.demo and args.root:
        print("conveyor-ui: --demo and --root cannot be combined", file=sys.stderr)
        sys.exit(2)
    fixture = None
    if args.demo:
        try:
            fixture = demo.make_demo()
        except Exception as e:
            print(f"conveyor-ui: {e}", file=sys.stderr)
            sys.exit(1)
        atexit.register(fixture.cleanup)
        print(f"conveyor-ui: demo fixture at {fixture.root}  (removed on exit)")
        if not os.path.isfile(os.path.join(DIST, "index.html")):
            print("UI not built. In another terminal: cd ui && npm start → http://localhost:4200")
        root = fixture.root
    else:
        try:
            root = state.resolve_root(args.root)
        except ValueError as e:
            print(f"conveyor-ui: {e}", file=sys.stderr)
            sys.exit(1)
    serve(root, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
