"""
Main entry point for the USMS package.

This module will be executed when the package is run directly.
It will delegate the execution to the CLI logic in the `cli.py` file.
"""

from usms.cli import run_cli

if __name__ == "__main__":
    run_cli()
