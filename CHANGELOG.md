# Changelog

All notable changes to this plugin will be documented in this file.

## v0.2.0 - 2026-02-22

### Added
- Add AstrBot LLM tools for unified Trello operations:
- `trello_select` (resolve by id/name and switch session context)
- `trello_read` (unified `list/get` for board/list/card/checklist/checklist_item)
- `trello_write` (unified `create/update/delete` for board/list/card/checklist/checklist_item)
- Add checklist/list/board/card helper methods in client for tool-driven CRUD and reads.

### Changed
- Support resolving board/list/card by name in command flows (`use-board`, `use-list`, `board-info`, `lists`, `cards`, `card`).
- Viewing by name now updates current session use-state (`board_id`, `list_id`, `card_id`) automatically.
- `scope` command now shows current `board_id`, `list_id`, and `card_id`.
- Help text updated to reflect `id|name` support on key commands.
- Validate checklist list-response shape in client for safer error handling.

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
