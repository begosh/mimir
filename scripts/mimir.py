"""Compatibility entrypoint; CLI and MCP share scripts.engine."""
from engine import run_mimir, MimirConsole
from cli import main

if __name__ == "__main__":
    main()
