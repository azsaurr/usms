# USMS

An unofficial Python library to interface with your [USMS](https://www.usms.com.bn/smartmeter/about.html) account and smart meters.

## Getting Started

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

You can also use environment variables for the login information:

```sh
export USMS_USERNAME="<ic_number>"
export USMS_PASSWORD="<password>"
python -m usms -m <meter> --unit
```

Or:

```sh
USMS_USERNAME="<ic_number>" USMS_PASSWORD="<password>" python -m usms -m <meter> --unit
```

## Usage

```py
from usms import USMSAccount
from datetime import datetime

username = "01001234" # your ic number
password = "hunter1"

# initialize the account
account = USMSAccount.create(username, password)

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

# get the number of the first meter
meter_no = account.meters[0].no

# to get info from a specific meter
meter = account.get_meter(meter_no)

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

* [ ] Add more test coverage
* [ ] Support for water meter
* [ ] Support for commercial/corporate accounts

## Contributing

### Prerequisites

1. [Generate an SSH key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent#generating-a-new-ssh-key) and [add the SSH key to your GitHub account](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).
1. Configure SSH to automatically load your SSH keys:

    ```sh
    cat << EOF >> ~/.ssh/config
    
    Host *
      AddKeysToAgent yes
      IgnoreUnknown UseKeychain
      UseKeychain yes
      ForwardAgent yes
    EOF
    ```

1. [Install Docker Desktop](https://www.docker.com/get-started).
1. [Install VS Code](https://code.visualstudio.com/) and [VS Code's Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers). Alternatively, install [PyCharm](https://www.jetbrains.com/pycharm/download/).
1. _Optional:_ install a [Nerd Font](https://www.nerdfonts.com/font-downloads) such as [FiraCode Nerd Font](https://github.com/ryanoasis/nerd-fonts/tree/master/patched-fonts/FiraCode) and [configure VS Code](https://github.com/tonsky/FiraCode/wiki/VS-Code-Instructions) or [PyCharm](https://github.com/tonsky/FiraCode/wiki/Intellij-products-instructions) to use it.

### Development Environments

The following development environments are supported:

1. ⭐️ _GitHub Codespaces_: click on [Open in GitHub Codespaces](https://github.com/codespaces/new/user/user) to start developing in your browser.
1. ⭐️ _VS Code Dev Container (with container volume)_: click on [Open in Dev Containers](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/user/user) to clone this repository in a container volume and create a Dev Container with VS Code.
1. ⭐️ _uv_: clone this repository and run the following from root of the repository:

    ```sh
    # Create and install a virtual environment
    uv sync --python 3.10 --all-extras

    # Activate the virtual environment
    source .venv/bin/activate

    # Install the pre-commit hooks
    pre-commit install --install-hooks
    ```

1. _VS Code Dev Container_: clone this repository, open it with VS Code, and run <kbd>Ctrl/⌘</kbd> + <kbd>⇧</kbd> + <kbd>P</kbd> → _Dev Containers: Reopen in Container_.
1. _PyCharm Dev Container_: clone this repository, open it with PyCharm, [create a Dev Container with Mount Sources](https://www.jetbrains.com/help/pycharm/start-dev-container-inside-ide.html), and [configure an existing Python interpreter](https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html#widget) at `/opt/venv/bin/python`.

### Developing

* This project follows the [Conventional Commits](https://www.conventionalcommits.org/) standard to automate [Semantic Versioning](https://semver.org/) and [Keep A Changelog](https://keepachangelog.com/) with [Commitizen](https://github.com/commitizen-tools/commitizen).
* Run `poe` from within the development environment to print a list of [Poe the Poet](https://github.com/nat-n/poethepoet) tasks available to run on this project.
* Run `uv add {package}` from within the development environment to install a run time dependency and add it to `pyproject.toml` and `uv.lock`. Add `--dev` to install a development dependency.
* Run `uv sync --upgrade` from within the development environment to upgrade all dependencies to the latest versions allowed by `pyproject.toml`. Add `--only-dev` to upgrade the development dependencies only.
* Run `cz bump` to bump the package's version, update the `CHANGELOG.md`, and create a git tag. Then push the changes and the git tag with `git push origin main --tags`.

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Acknowledgments

* [USMS](https://www.usms.com.bn/smartmeter/about.html)

### Project Template

This project was built using the [superlinear-ai/substrate](https://github.com/superlinear-ai/substrate) template.
