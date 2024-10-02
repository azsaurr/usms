import argparse
import logging

from .usms import USMSAccount

_LOGGER = logging.getLogger(__name__)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("-l", "--log", default="warning")

    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-p", "--password", required=True)

    parser.add_argument("-m", "--meter", required=False)

    parser.add_argument("--unit", action="store_true")
    parser.add_argument("--consumption", action="store_true")
    parser.add_argument("--credit", action="store_true")

    args = parser.parse_args()

    numeric_level = getattr(logging, args.log.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level: %s" % args.log)
    logging.basicConfig(level=numeric_level)

    account = USMSAccount(args.username, args.password)

    if not args.meter:
        for meter in account.get_meters():
            print("Meters:")
            print(f"- {meter.get_no()} ({meter.get_type()})")
    else:
        meter = account.get_meter(args.meter)

        if args.unit:
            print(f"Unit: {meter.get_remaining_unit()} {meter.get_unit()}")
        if args.credit:
            print(f"Credit: ${meter.get_remaining_credit()}")
        if args.consumption:
            print(f"Consumption: {meter.get_last_consumption()} {meter.get_unit()}")
