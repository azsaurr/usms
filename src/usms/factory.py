"""
USMS Account Initialization Factory.

This module provides a factory method to create and initialize
USMSAccount or AsyncUSMSAccount instances with flexible configuration options.
"""

from typing import TYPE_CHECKING

from usms.core.client import USMSClient
from usms.core.protocols import HTTPXClientProtocol
from usms.exceptions.errors import USMSIncompatibleAsyncModeError, USMSMissingCredentialsError
from usms.services.async_.account import AsyncUSMSAccount
from usms.services.sync.account import USMSAccount
from usms.storage.base_storage import BaseUSMSStorage
from usms.utils.helpers import get_storage_manager

if TYPE_CHECKING:
    from usms.services.account import BaseUSMSAccount


def initialize_usms_account(  # noqa: PLR0913
    username: str | None = None,
    password: str | None = None,
    client: "HTTPXClientProtocol" = None,
    usms_client: "USMSClient" = None,
    storage_type: str | None = None,
    storage_path: str | None = None,
    storage_manager: "BaseUSMSStorage" = None,
    async_mode: bool | None = None,
) -> "BaseUSMSAccount":
    """
    Initialize and return a USMSAccount or AsyncUSMSAccount instance.

    This factory method provides a flexible way to create USMS accounts,
    supporting both synchronous and asynchronous modes. It allows for
    custom authentication, HTTP clients, and storage management.

    Parameters
    ----------
    username : str | None
        Username for USMS authentication. Required if `usms_client` is not provided.
    password : str | None
        Password for USMS authentication. Required if `usms_client` is not provided.
    client : HTTPXClientProtocol | None
        A HTTPX client (sync or async) to use for USMS requests.
    usms_client : BaseUSMSClient | None
        Initialized USMSClient or AsyncUSMSClient instance.
    storage_type : str | None
        Type of storage for data persistence (e.g., 'csv', 'json').
    storage_path : str | None
        File path for the storage file (if applicable).
    storage_manager : BaseUSMSStorage | None
        A pre-initialized storage manager instance.
    async_mode : bool | None
        Whether to use asynchronous mode. If True, has to be awaited.

    Returns
    -------
    USMSAccount | AsyncUSMSAccount
        A fully initialized USMS account object.

    Raises
    ------
    USMSMissingCredentialsError
        If neither `auth` nor both `username` and `password` are provided.
    USMSIncompatibleAsyncModeError
        If async_mode is incompatible with the provided client or client mode.

    Examples
    --------
    # Synchronous usage with automatic configuration:
    account = initialize_usms_account(username="username", password="password")

    # Asynchronous usage:
    account = await initialize_usms_account(
        username="username",
        password="password",
        async_mode=True,
    )

    # Custom client and storage:
    import httpx
    from usms.utils.helpers import get_storage_manager
    storage_manager = get_storage_manager(storage_type="csv")
    account = initialize_usms_account(
        username="username",
        password="password",
        client=httpx.Client(),
        storage_manager=storage_manager,
    )
    """
    if not isinstance(usms_client, USMSClient):
        if username is None and password is None:
            raise USMSMissingCredentialsError

        if not isinstance(client, HTTPXClientProtocol):
            import httpx

            client = httpx.AsyncClient(http2=True) if async_mode else httpx.Client(http2=True)

        usms_client = USMSClient(client=client, username=username, password=password)

    if async_mode is not None:
        if async_mode != usms_client.async_mode:
            raise USMSIncompatibleAsyncModeError
    else:
        async_mode = usms_client.async_mode

    if not isinstance(storage_manager, BaseUSMSStorage) and storage_type is not None:
        storage_manager = get_storage_manager(storage_type=storage_type, storage_path=storage_path)

    if async_mode:
        return AsyncUSMSAccount.create(session=usms_client, storage_manager=storage_manager)
    return USMSAccount.create(session=usms_client, storage_manager=storage_manager)
