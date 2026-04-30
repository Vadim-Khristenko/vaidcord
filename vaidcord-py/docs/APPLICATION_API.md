# Application API resources

VaidCord includes convenience models and methods for Discord application resources.

## Current application

- `await bot.get_current_application()`
- `await bot.edit_current_application(...)`

## Role connection metadata

- `await bot.get_application_role_connection_metadata(application_id)`
- `await bot.update_application_role_connection_metadata(application_id, records)`

`records` supports up to 5 metadata entries (Discord limit).
