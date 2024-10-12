import base64
import httpx
import logging
import lxml.html
import typing

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


_LOGGER = logging.getLogger(__name__)


class USMSAccount:
    """Represents a USMS account."""

    _session: None

    """USMS Account class attributes."""
    reg_no: str
    name: str
    contact_no: str
    email: str
    meters: list

    def __init__(self, username: str, password: str) -> None:
        self._session = USMSClient(username, password)

        self.initialize()

    def initialize(self) -> None:
        """Retrieves initial USMS Account attributes."""

        _LOGGER.debug("Initializing account")

        response = self._session.get("/AccountInfo")
        response_html = lxml.html.fromstring(response.content)

        self.reg_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblIDNumber"]"""
        ).text_content()
        self.name = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblName"]"""
        ).text_content()
        self.contact_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblContactNo"]"""
        ).text_content()
        self.email = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblEmail"]"""
        ).text_content()

        self.meters = []
        root = response_html.find(
            """.//div[@id="ASPxPanel1_ASPxTreeView1_CD"]"""
        )  # Nx_y_z
        for x, lvl1 in enumerate(root.findall("./ul/li")):
            for y, lvl2 in enumerate(lvl1.findall("./ul/li")):
                for z, lvl3 in enumerate(lvl2.findall("./ul/li")):
                    meter = USMSMeter(self, f"N{x}_{y}_{z}")
                    self.meters.append(meter)

        _LOGGER.debug(f"Initialized account {self.reg_no} {self.name}")

    def get_meter(self, meter_no: str):
        for meter in self.meters:
            if meter.id == meter_no or meter.no == meter_no:
                return meter
        raise USMSMeterNumberError(meter_no)


class USMSMeter:
    """Represents a USMS meter under an account."""

    TARIFFS = {
        "Electricity": [
            [1, 600, 0.01],
            [601, 2000, 0.08],
            [2001, 4000, 0.10],
            [4001, float("inf"), 0.12],
        ],
        "Water": [
            [1, 54.54, 0.11],
            [54.54, float("inf"), 0.44],
        ],
    }
    TIMEZONE = ZoneInfo("Asia/Brunei")
    UNITS = {
        "Electricity": "kWh",
        "Water": "meter cube",  # TODO
    }

    """USMS Meter class attributes."""
    _account: None
    node_no: str

    address: str
    kampong: str
    mukim: str
    district: str
    postcode: str

    no: str
    id: str  # base64 encoded meter no

    type: str
    customer_type: str
    remaining_unit: float
    remaining_credit: float

    last_update: datetime

    status: str

    def __init__(self, account, node_no) -> None:
        self._account = account
        self._node_no = node_no

        self.initialize()

    def initialize(self, retry=True) -> None:
        """Retrieves initial USMS Meter attributes."""

        # build payload
        payload = {}
        payload["ASPxTreeView1"] = (
            "{&quot;nodesState&quot;:[{&quot;N0_0&quot;:&quot;T&quot;,&quot;N0&quot;:&quot;T&quot;},&quot;"
            + self._node_no
            + "&quot;,{}]}"
        )
        payload["__EVENTARGUMENT"] = f"NCLK|{self._node_no}"
        payload["__EVENTTARGET"] = "ASPxPanel1$ASPxTreeView1"

        while True:
            self._account._session.get("/AccountInfo")
            response = self._account._session.post("/AccountInfo", data=payload)
            response_html = lxml.html.fromstring(response.content)

            address = response_html.find(
                """.//span[@id="ASPxFormLayout1_lblAddress"]"""
            )

            # checks for error in retrieving page
            if address is None and not retry:
                raise USMSPageResponseError()
            else:
                break

        self.address = address.text_content().strip()
        self.kampong = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblKampong"]""")
            .text_content()
            .strip()
        )
        self.mukim = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMukim"]""")
            .text_content()
            .strip()
        )
        self.district = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblDistrict"]""")
            .text_content()
            .strip()
        )
        self.postcode = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblPostcode"]""")
            .text_content()
            .strip()
        )

        self.no = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterNo"]""")
            .text_content()
            .strip()
        )
        self.id = base64.b64encode(self.no.encode()).decode()

        self.type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterType"]""")
            .text_content()
            .strip()
        )
        self.customer_type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCustomerType"]""")
            .text_content()
            .strip()
        )

        self.remaining_unit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblRemainingUnit"]""")
            .text_content()
            .strip()
        )
        self.remaining_unit = float(self.remaining_unit.split()[0].replace(",", ""))

        self.remaining_credit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCurrentBalance"]""")
            .text_content()
            .strip()
        )
        self.remaining_credit = float(
            self.remaining_credit.split("$")[-1].replace(",", "")
        )

        self.last_update = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblLastUpdated"]""")
            .text_content()
            .strip()
        )
        date = self.last_update.split()[0].split("/")
        time = self.last_update.split()[1].split(":")
        self.last_update = datetime(
            int(date[2]),
            int(date[1]),
            int(date[0]),
            hour=int(time[0]),
            minute=int(time[1]),
            second=int(time[2]),
            tzinfo=self.TIMEZONE,
        )

        self.status = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblStatus"]""")
            .text_content()
            .strip()
        )

        _LOGGER.debug(f"Initialized {self.type} meter {self.no}")

    def update(self, force=False) -> bool:
        """
        Retrieves updated values for the following attributes:
            - remaining unit
            - remaining credit
            - last update
        Returns a boolean indicating there was an update.
        """

        """
        Tries to limit unnecessary calls to the site by
        checking if at least an hour has passed since last meter update
        i.e. no new meter update available yet
        """
        if not force:
            now = datetime.now(tz=self.TIMEZONE)
            if (now - self.last_update).total_seconds() <= 3600:
                _LOGGER.warning(
                    f"Not enough time has passed since last update: {now - self.last_update}"
                )
                return False

        # build payload
        payload = {}
        payload["ASPxTreeView1"] = (
            "{&quot;nodesState&quot;:[{&quot;N0_0&quot;:&quot;T&quot;,&quot;N0&quot;:&quot;T&quot;},&quot;"
            + self._node_no
            + "&quot;,{}]}"
        )
        payload["__EVENTARGUMENT"] = f"NCLK|{self._node_no}"
        payload["__EVENTTARGET"] = "ASPxPanel1$ASPxTreeView1"

        self._account._session.get("/AccountInfo")
        response = self._account._session.post("/AccountInfo", data=payload)
        response_html = lxml.html.fromstring(response.content)

        # checks for error in retrieving page
        if response_html.find(""".//span[@id="ASPxFormLayout1_lblAddress"]""") is None:
            _LOGGER.error(f"Error retrieving updates for {self.type} meter {self.no}")
            return False

        remaining_unit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblRemainingUnit"]""")
            .text_content()
            .strip()
            .split()[0]
            .replace(",", "")
        )
        if "-" in remaining_unit:
            _LOGGER.error(f"Updates for {self.type} meter {self.no} not available.")
            return False
        self.remaining_unit = float(remaining_unit)

        self.remaining_credit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCurrentBalance"]""")
            .text_content()
            .strip()
        )
        self.remaining_credit = float(
            self.remaining_credit.split("$")[-1].replace(",", "")
        )

        self.last_update = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblLastUpdated"]""")
            .text_content()
            .strip()
        )
        date = self.last_update.split()[0].split("/")
        time = self.last_update.split()[1].split(":")
        self.last_update = datetime(
            int(date[2]),
            int(date[1]),
            int(date[0]),
            hour=int(time[0]),
            minute=int(time[1]),
            second=int(time[2]),
            tzinfo=self.TIMEZONE,
        )

        _LOGGER.debug(f"Retrieved updates for {self.type} meter {self.no}")
        return True

    def get_hourly_consumptions(self, date: datetime) -> dict:
        """Returns the hourly unit consumptions for a given day."""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        now = datetime.now(tz=self.TIMEZONE)

        # make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch = date.strftime("%s") + "000"

        # build payload
        payload = {}
        payload["cboType_VI"] = "3"
        payload["cboType"] = "Hourly (Max 1 day)"

        self._account._session.get(f"/Report/UsageHistory?p={self.id}")
        self._account._session.post(f"/Report/UsageHistory?p={self.id}", data=payload)

        payload = {"btnRefresh": ["Search", ""]}
        payload["cboDateFrom"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = (
            "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        )
        payload["cboDateTo$State"] = (
            "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        )
        response = self._account._session.post(
            f"/Report/UsageHistory?p={self.id}",
            data=payload,
        )
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(
            """.//span[@id="pcErr_lblErrMsg"]"""
        ).text_content()
        if error_message == "consumption history not found.":
            raise USMSConsumptionHistoryNotFoundError()
        elif error_message:
            raise Exception(error_message)

        table = response_html.find(
            """.//table[@id="ASPxPageControl1_grid_DXMainTable"]"""
        )

        hourly_consumptions = {}
        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            row = row.findall(".//td")

            hour = int(row[0].text_content())

            if hour < 24:
                hour = datetime(
                    date.year,
                    date.month,
                    date.day,
                    hour,
                    0,
                    0,
                    tzinfo=self.TIMEZONE,
                )
            else:
                hour = datetime(
                    date.year,
                    date.month,
                    date.day,
                    23,
                    0,
                    0,
                    tzinfo=self.TIMEZONE,
                )
                hour = hour + timedelta(hours=1)

            consumption = float(row[1].text_content())

            hourly_consumptions[hour] = consumption

        _LOGGER.debug(f"Retrieved consumption info for day of: {date}")
        return hourly_consumptions

    def get_daily_consumptions(self, date: datetime) -> dict:
        """Returns the daily unit consumptions for a given month."""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        now = datetime.now(tz=self.TIMEZONE)

        # make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

        date_from = datetime(
            date.year,
            date.month,
            1,
            8,
            0,
            0,
            tzinfo=self.TIMEZONE,
        )
        epoch_from = date_from.strftime("%s") + "000"

        # check if given month is still ongoing
        if date.year == now.year and date.month == now.month:
            # then get consumption up until yesterday only
            date = date - timedelta(days=1)
        else:
            # otherwise get until the last day of the month
            next_month = date.replace(day=28) + timedelta(days=4)
            date.replace(day=next_month - timedelta(days=next_month.day))

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch_to = date.strftime("%s") + "000"

        # build payload
        payload = {}
        payload["cboType_VI"] = "1"
        payload["cboType"] = "Daily (Max 1 month)"
        payload["btnRefresh"] = "Search"
        payload["cboDateFrom"] = f"01/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = (
            "{" + f"&quot;rawValue&quot;:&quot;{epoch_from}&quot;" + "}"
        )
        payload["cboDateTo$State"] = (
            "{" + f"&quot;rawValue&quot;:&quot;{epoch_to}&quot;" + "}"
        )

        self._account._session.get(f"/Report/UsageHistory?p={self.id}")
        self._account._session.post(f"/Report/UsageHistory?p={self.id}")
        self._account._session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = self._account._session.post(
            f"/Report/UsageHistory?p={self.id}", data=payload
        )
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(
            """.//span[@id="pcErr_lblErrMsg"]"""
        ).text_content()
        if error_message == "consumption history not found.":
            raise USMSConsumptionHistoryNotFoundError()
        elif error_message:
            raise Exception(error_message)

        table = response_html.find(
            """.//table[@id="ASPxPageControl1_grid_DXMainTable"]"""
        )

        daily_consumptions = {}
        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            row = row.findall(".//td")

            day = int(row[0].text_content().split("/")[0])
            day = datetime(
                date.year,
                date.month,
                day,
                0,
                0,
                0,
                tzinfo=self.TIMEZONE,
            )

            consumption = float(row[1].text_content())

            daily_consumptions[day] = consumption

        _LOGGER.debug(f"Retrieved consumption info for month of: {date}")
        return daily_consumptions

    def get_total_day_consumption(self, date: datetime) -> float:
        """Returns the total unit consumption for a given day"""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        hourly_consumptions = self.get_hourly_consumptions(date)

        total_consumption = 0
        for hour, consumption in hourly_consumptions.items():
            total_consumption += consumption

        return round(total_consumption, 3)

    def get_total_month_consumption(self, date: datetime) -> float:
        """Returns the total unit consumption for a given month."""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        daily_consumptions = self.get_daily_consumptions(date)

        total_consumption = 0
        for day, consumption in daily_consumptions.items():
            total_consumption += consumption

        return round(total_consumption, 3)

    def get_hourly_consumption(self, date: datetime) -> float | None:
        """Returns the unit consumption for a given hour."""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        date = datetime(
            date.year,
            date.month,
            date.day,
            date.hour,
            0,
            0,
            tzinfo=self.TIMEZONE,
        )

        hourly_consumptions = self.get_hourly_consumptions(date)
        consumption = hourly_consumptions.get(date, None)

        if consumption is None:
            _LOGGER.warning(f"No consumption recorded yet for {date}")
            return

        return consumption

    def get_last_consumption(self) -> float | None:
        """Returns the unit consumption for the last hour."""

        date = datetime.now(tz=self.TIMEZONE)
        consumption = self.get_hourly_consumption(date)

        return consumption

    def get_total_month_cost(self, date: datetime) -> float:
        """Returns the total cost for a given month."""

        # make sure given date has timezone info
        if not date.tzinfo:
            _LOGGER.warning(f"Given date has no timezone, assuming {self.TIMEZONE}")
            date = date.replace(tzinfo=self.TIMEZONE)

        total_consumption = self.get_total_month_consumption(date)
        total_cost = self.calculate_cost(total_consumption, self.type)

        return round(total_cost, 2)

    def calculate_cost(self, consumption: float, meter_type: str = "") -> float:
        """Calculates and returns the cost for given unit consumption, according to the tariff"""

        if meter_type == "":
            meter_type = self.type

        cost = 0.0
        for tier in self.TARIFFS.get(meter_type):
            lower_bound = tier[0]
            upper_bound = tier[1]
            cost_per_unit = tier[2]

            bound_range = upper_bound - lower_bound + 1

            if consumption <= bound_range:
                cost += consumption * cost_per_unit
                break
            else:
                consumption -= bound_range
                cost += bound_range * cost_per_unit

        return round(cost, 2)

    def calculate_unit(self, cost: float, meter_type: str = "") -> float:
        """Calculates and returns the unit received for the cost paid, according to the tariff"""

        if meter_type == "":
            meter_type = self.type

        unit = 0.0
        for tier in self.TARIFFS.get(meter_type):
            lower_bound = tier[0]
            upper_bound = tier[1]
            cost_per_unit = tier[2]

            bound_range = upper_bound - lower_bound + 1
            bound_cost = bound_range * cost_per_unit

            if cost <= bound_cost:
                unit += cost / cost_per_unit
            else:
                cost -= bound_cost
                unit += bound_range

        return round(unit, 2)

    def get_remaining_unit(self) -> float:
        """Returns the last recorded unit for the meter."""

        return self.remaining_unit

    def get_remaining_credit(self) -> float:
        """Returns the last recorded credit for the meter."""

        return self.remaining_credit

    def get_last_updated(self) -> datetime:
        """Returns the last update time for the meter."""

        return self.last_update

    def is_active(self) -> bool:
        """Returns True if the meter status is active."""

        return self.status == "ACTIVE"

    def get_unit(self) -> str:
        """Returns the unit for this meter type"""

        return self.UNITS[self.type]

    def get_no(self) -> str:
        """Returns this meter's meter no"""

        return self.no

    def get_type(self) -> str:
        """Returns this meter's type (Electricity or Water)"""

        return self.type


class USMSClient(httpx.Client):
    def __init__(self, username: str, password: str) -> None:
        super().__init__()

        self.auth = USMSAuth(username, password)
        self.base_url = "https://www.usms.com.bn/SmartMeter/"
        self.event_hooks["response"] = [self._get_asp_state]
        self.http2 = True
        self.timeout = 30.0

        self._asp_state = {}

    def post(self, url: str, data: dict = {}) -> httpx.Response:
        """
        Send a `POST` request.

        **Parameters**: See `httpx.request`.
        """

        if self._asp_state and data:
            for asp_key, asp_value in self._asp_state.items():
                if not data.get(asp_key):
                    data[asp_key] = asp_value

        return super().post(url=url, data=data)

    def _get_asp_state(self, response: httpx.Response):
        response_html = lxml.html.fromstring(response.read())

        for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
            if hidden_input.value:
                self._asp_state[hidden_input.name] = hidden_input.value


class USMSAuth(httpx.Auth):
    requires_response_body = True

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> typing.Generator[httpx.Request, httpx.Response, None]:
        response = yield request

        if self.is_expired(response):
            response = yield httpx.Request(
                method="POST",
                url="https://www.usms.com.bn/SmartMeter/ResLogin",
            )
            response_html = lxml.html.fromstring(response.content)

            asp_state = {}
            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                asp_state[hidden_input.name] = hidden_input.value
            asp_state["ASPxRoundPanel1$btnLogin"] = "Login"
            asp_state["ASPxRoundPanel1$txtUsername"] = self._username
            asp_state["ASPxRoundPanel1$txtPassword"] = self._password

            response = yield httpx.Request(
                method="POST",
                url="https://www.usms.com.bn/SmartMeter/ResLogin",
                data=asp_state,
            )

            response_html = lxml.html.fromstring(response.content)
            error_message = response_html.find(""".//*[@id="pcErr_lblErrMsg"]""")
            if error_message:
                _LOGGER.error(error_message.text_content())
                raise USMSLoginError(error_message.text_content())

            request.cookies = response.cookies
            session_id = request.cookies["ASP.NET_SessionId"]
            request.headers["cookie"] = f"ASP.NET_SessionId={session_id}"

            sig = response.headers["location"].split("Sig=")[-1].split("&")[-1]
            response = yield httpx.Request(
                method="GET",
                url=f"https://www.usms.com.bn/SmartMeter/LoginSession.aspx?pLoginName={self._username}&Sig={sig}",
                cookies=request.cookies,
            )

            response = yield response.next_request
            response = yield response.next_request
            _LOGGER.debug("Logged in")

            yield request

    def is_expired(self, response: httpx.Response) -> bool:
        """Checks response and returns True if the session has expired"""

        expired = False

        if response.status_code == 302:
            if "SessionExpire" in response.text:
                expired = True
        elif response.status_code == 200:
            if "Your Session Has Expired, Please Login Again." in response.text:
                expired = True

        if expired:
            _LOGGER.debug("Session has expired")
            return True

        return False


class USMSMeterNumberError(Exception):
    """Exception raised for when invalid meter number is given."""

    def __init__(self, meter_no="is"):
        self.message = f"Meter {meter_no} not found."
        super().__init__(self.message)


class USMSLoginError(Exception):
    """Exception raised for when unable to login."""

    def __init__(self, message="Invalid login."):
        self.message = message
        super().__init__(self.message)


class USMSPageResponseError(Exception):
    """Exception raised for when error during page retrieval."""

    def __init__(self, page_url="USMS page"):
        self.message = f"Response from {page_url} was not expected."
        super().__init__(self.message)


class USMSFutureDateError(Exception):
    """Exception raised for when future date is given."""

    def __init__(self, given_date="Given date"):
        self.message = f"{given_date} is in the future."
        super().__init__(self.message)


class USMSConsumptionHistoryNotFoundError(Exception):
    """Exception raised for when no consumption history can be retrieved."""

    def __init__(self, message="Consumption history not found."):
        self.message = message
        super().__init__(self.message)
