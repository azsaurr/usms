# ruff: noqa: C901, T201

"""
CLI module for USMS.

This module contains the CLI logic to interact with the USMS package, including
commands and options for users to interact with the system through the command line.
"""

import argparse
import os
import sys
from importlib.metadata import PackageNotFoundError, version

from usms import USMSAccount
from usms.exceptions.errors import USMSLoginError, USMSMeterNumberError
from usms.utils.logging_config import init_console_logging, logging

# get usms_version dynamically
try:
    usms_version = version("usms")
except PackageNotFoundError:
    usms_version = "unknown"


def run_cli():
    """Run the command-line interface for USMS."""
    parser = argparse.ArgumentParser(description="USMS CLI")

    parser.add_argument(
        "-log",
        "--log-level",
        default="warning",
        help="Set log level (e.g., debug, info, warning, error)",
    )
    parser.add_argument("--version", action="version", version=f"USMS CLI v{usms_version}")

    parser.add_argument(
        "-u",
        "--username",
        default=os.getenv("USMS_USERNAME"),
        help="USMS account username",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=os.getenv("USMS_PASSWORD"),
        help="USMS account password",
    )

    # optional arguments
    parser.add_argument("-l", "--list", action="store_true", help="List all available meters")
    parser.add_argument("-m", "--meter", help="Meter number to query")

    # meter data options
    data_group = parser.add_argument_group("Meter Data Options")
    data_group.add_argument("--unit", action="store_true", help="Show remaining unit")
    data_group.add_argument(
        "--consumption", action="store_true", help="Show last recorded consumption"
    )
    data_group.add_argument("--credit", action="store_true", help="Show remaining credit balance")

    args = parser.parse_args()

    # check passed arguments
    if not getattr(logging, args.log_level.upper(), None):
        print(f"Invalid log level: {args.log_level}")
        sys.exit(1)
    init_console_logging(args.log_level.upper())

    if not args.username or not args.password:
        print("Username and password must be provided (via arguments or environment variables).")
        sys.exit(1)

    if not args.list and not args.meter:
        print("No meter option (--list, --meter) specified.")
        parser.print_help()
        sys.exit(0)

    if args.meter and not (args.unit or args.credit or args.consumption):
        print("No data option (--unit, --credit, --consumption) specified.")
        parser.print_help()
        sys.exit(0)

    # initialize account
    try:
        account = USMSAccount(args.username, args.password)
    except USMSLoginError as error:
        print(error)
        sys.exit(1)

    if args.list:
        print("Meters:")
        for meter in account.meters:
            print(f"- {meter.get_no()} ({meter.get_type()})")

    try:
        meter = account.get_meter(args.meter)

        if args.unit:
            print(f"Unit: {meter.get_remaining_unit()} {meter.get_unit()}")
        if args.credit:
            print(f"Credit: ${meter.get_remaining_credit()}")
        if args.consumption:
            print(f"Consumption: {meter.get_last_consumption()} {meter.get_unit()}")
    except USMSMeterNumberError as error:
        print(error)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    run_cli()
