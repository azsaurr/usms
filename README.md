# USMS

An unofficial Python library to interface with your [USMS](https://www.usms.com.bn/smartmeter/about.html) account and smart meters.

## Getting Started

### Pre-requisites

* Python >= 3.8
* pip

### Dependencies

* [httpx](https://www.python-httpx.org/)
* [lxml](https://lxml.de/)

### Installation

```sh
python -m pip install usms
```

### Quickstart

```sh
python -m usms --help
```

```sh
usage: __main__.py [-h] [-l LOG] -u USERNAME -p PASSWORD [-m METER] [--unit] [--consumption] [--credit]

options:
  -h, --help            show this help message and exit
  -l LOG, --log LOG
  -u USERNAME, --username USERNAME
  -p PASSWORD, --password PASSWORD
  -m METER, --meter METER
  --unit
  --consumption
  --credit
```

> [!NOTE]
> The `username` parameter is the login ID that you use to log-in on the USMS website/app, i.e. your IC Number.

As an example, you can use the following command to get the current remaining unit:

```sh
python -m usms -u <ic_number> -p <password> -m <meter> --unit
```

## Usage

```py
from usms import USMSAccount
from datetime import datetime

username = "01001234" # your ic number
password = "hunter1"

# initialize the account
account = USMSAccount(username, password)

# print out the account information
print(account.reg_no)
print(account.name)
print(account.contact_no)
print(account.email)

# print out info on all meters under the account
for meter in account.meters:
    print(meter.no)
    print(meter.type)
    print(meter.address)
    print(meter.remaining_unit)
    print(meter.remaining_credit)

# to get info from a specific meter
meter = account.get_meter(12345678) # example meter number

# getting hourly breakdown of today's consumptions
date = datetime.now()
hourly_consumptions = meter.get_hourly_consumptions(date)
print(hourly_consumptions)
# getting daily breakdown of this month's comsumptions
daily_consumptions = meter.get_daily_consumptions(date)
print(daily_consumptions)

# get yesterday's total consumption
date = date.replace(day=date.day-1)
print(meter.get_total_day_consumption(date))

# get last month's total cost based un total consumption
date = date.replace(month=date.month-1)
print(meter.get_total_month_cost(date))
```

## To-Do

* [X] Publish package to PyPI
* [X] Improve README
* [ ] Support for water meter
* [ ] Support for commercial/corporate accounts

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Acknowledgments

* [USMS](https://www.usms.com.bn/smartmeter/about.html)
* [httpx](https://www.python-httpx.org/), used to make HTTP requests
* [lxml](https://lxml.de/), used to parse HTML responses)
