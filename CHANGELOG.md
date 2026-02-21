# Changelog

All notable changes to this plugin will be documented in this file.

## v0.1.1 - 2026-02-21

### Added
- Add board features:
- `board-create`
- `board-info`
- `board-archive`
- Add list features:
- `list-create`
- `list-rename`
- `list-archive`
- `cards` (list cards under a list)
- Add card features:
- `card` (show card details)
- `edit` (edit `name|desc|due|list`)
- `archive` (archive card)
- `delete` (delete card)
- `comment` (add card comment)
- Add checklist features:
- `checklists` (list checklists and items)
- `checklist-create`
- `checklist-add`
- `checklist-check`
- `checklist-uncheck`
- `checklist-delete`
- Add `help` command to show command usage.

### Changed
- Reuse `aiohttp.ClientSession` in client and close it in plugin `terminate()`.
- Improve client response validation and network error handling.
- Unify command parsing for `|` style commands via shared helper.
- Remove hard-coded slash prefix dependency in command tail parsing.

