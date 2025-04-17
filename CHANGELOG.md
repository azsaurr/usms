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
