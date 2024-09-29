# USMS
An unofficial Python library to interface with your [USMS](https://www.usms.com.bn/smartmeter/about.html) account and smart meters.



## Getting Started

### Prerequisites

* Python >= 3.8
* pip

### Installation

```sh
pip install usms
```

### Quickstart

```sh
python -m usms --help
```
```
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



## Usage

Providing only the login information will list all meters under the account.
```sh
python -m usms -u <ic_number> -p <password>
```



## To-Do

- [ ] Publish package to PyPI
- [ ] Improve README
- [ ] Support for water meter
- [ ] Support for commercial/corporate accounts



## License

Distributed under the MIT License. See `LICENSE` for more information.



## Acknowledgments

* []() requests
* []() BeautifulSoup
* []() USMS
