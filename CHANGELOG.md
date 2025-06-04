## v0.9.2 (2025-06-05)

### Fix

- ensure datetime string is properly parsed as datetime object, using a newly added helper function

## v0.9.1 (2025-05-29)

### Fix

- **account**: update reference to meter class attribute after removing getter method

## v0.9.0 (2025-05-28)

### Feat

- add custom exceptions for errors in USMS account and storage manager initialization
- add factory module to help construct instances with default injected dependencies

### Fix

- **cli**: fix mistake when calling initialize factory function
- **client**: ASP.net state is now injected properly when making POST requests

### Refactor

- **cli**: update CLI to support changes to the codebase and use new factory initialization method
- clean up codebase, improve type checking and setters, remove redundant getters
- **parser**: create separate parser modules using html.parser instead of lxml
- rename function for clarity, remove obsolete class, add missing type hint
- **account**: replace usms_client and storage_manager initialization with dependency injection
- **client**: focus client support on httpx only for now, while refactoring httpx.Auth to a scalable mixin instead, future-proofing for potential multi-client DI support
- **client**: separate client logic into distinct layers and introduced dependency injection for HTTP client
- **storage**: create BaseUSMSStorage abstract class

## v0.8.0 (2025-05-13)

### Feat

- **db**: offload sqlite and csv storage operations using asyncio.to_thread()
- **db**: initial synchronous implementation of csv
- **db**: initial synchronous implementation of sqlite

### Fix

- correctly rename dataframe column

### Refactor

- move conversion of consumptions to dataframe to a helper method

## v0.7.3 (2025-05-07)

### Fix

- assume tz-naive timestamp as local timezone

## v0.7.2 (2025-05-05)

### Fix

- ensure proper timezone handling for datetime operations
- handle edge case where no data is available yet when trying to find earliest consumption date

## v0.7.1 (2025-04-25)

### Fix

- set last_refresh timestamp to the current time

## v0.7.0 (2025-04-25)

### Perf

- fetch account and meter info from unified page to reduce requests

## v0.6.0 (2025-04-23)

### Fix

- initial support for new/water meter with no last update timestamp

## v0.5.10 (2025-04-18)

### Feat

- **cli**: update cli, use asynchronous operations by default and add --sync flag to support synchronous operations

## v0.5.9 (2025-04-18)

### Fix

- **meter**: return correct meter data instead of empty, ignoring certain error message parsed from the page

## v0.5.8 (2025-04-17)

### Refactor

- return JSON from fetch_info without updating class attributes, allowing update checks without having to initialize temporary meter object

## v0.5.7 (2025-04-16)

### Feat

- **meter**: add refresh_interval to allow different frequency of update checks after the update_interval threshold

## v0.5.6 (2025-04-16)

### Fix

- **meter**: offset scraped hourly consumptions data from USMS by 1 hour

## v0.5.5 (2025-04-16)

### Fix

- **logging**: changed logging config to avoid duplicate stdout logs when package is imported from external apps

## v0.5.4 (2025-04-16)

### Fix

- **meter**: return only the unit column of hourly consumptions as a Series, consistent with other functions' return

## v0.5.3 (2025-04-15)

### Feat

- **client**: add async SSL context setup for AsyncUSMSClient

## v0.5.2 (2025-04-15)

### Feat

- **exceptions**: add new exceptions for validation and lifecycle checks
- introduce classmethod-based initialization for cleaner async/sync instantiation
- introduce decorators to prevent usage of certain methods before object is initialized

### Fix

- fixed typo in module import

## v0.5.1 (2025-04-15)

### Refactor

- restructure codebase with separate sync/async services, shared base classes, models and utility functions
- **async**: offload blocking operations to async functions

## v0.5.0 (2025-04-13)

### Feat

- **async**: add initial async support

## v0.4.1 (2025-04-12)

### Feat

- **account**: add methods for logging in and check authentication status

### Refactor

- **meter**: rename functions and update docstrings for clarity
- **meter**: more efficient lookup of meter consumption data

## v0.4.0 (2025-04-10)

### Feat

- **meter**: add method to refresh meter data if due and return success status

### Fix

- replace ambiguous truth value checks to avoid FutureWarning

### Refactor

- added CLI functionality and logic into cli.py
- split monolithic codebase into structured submodules
