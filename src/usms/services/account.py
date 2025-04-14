"""
USMS Account Module.

This module defines the USMSAccount class,
which represents a user account in the USMS system.
It provides methods to retrieve account details,
manage associated meters and handle user sessions.
"""

import httpx
import lxml.html

from usms.core.auth import USMSAuth
from usms.models.account import USMSAccount as USMSAccountModel


class BaseUSMSAccount(USMSAccountModel):
    """
    Represents a USMS account.

    Represents a USMS account, allowing access to account details
    and associated meters.
    """

    username: str
    auth: USMSAuth

    def __init__(self, username: str, password: str) -> None:
        """Initialize a USMSAccount instance."""
        self.username = username
        self.auth = USMSAuth(username, password)

    def parse_info(self, response: httpx.Response | bytes) -> dict:
        """Parse data from account info page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        reg_no = response_html.find(""".//span[@id="ASPxFormLayout1_lblIDNumber"]""").text_content()
        name = response_html.find(""".//span[@id="ASPxFormLayout1_lblName"]""").text_content()
        contact_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblContactNo"]"""
        ).text_content()
        email = response_html.find(""".//span[@id="ASPxFormLayout1_lblEmail"]""").text_content()

        # Get all meters associated with this account
        meters = []
        root = response_html.find(""".//div[@id="ASPxPanel1_ASPxTreeView1_CD"]""")  # Nx_y_z
        for x, lvl1 in enumerate(root.findall("./ul/li")):
            for y, lvl2 in enumerate(lvl1.findall("./ul/li")):
                for z, _ in enumerate(lvl2.findall("./ul/li")):
                    meter_node_no = f"N{x}_{y}_{z}"
                    meters.append(meter_node_no)

        return {
            "reg_no": reg_no,
            "name": name,
            "contact_no": contact_no,
            "email": email,
            "meters": meters,
        }
