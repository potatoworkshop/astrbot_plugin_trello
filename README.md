# Trello 控制插件 / Trello Control Plugin

通过 AstrBot 指令和 AstrBot Tools 控制 Trello 看板、列表、卡片与检查清单。  
Control Trello boards, lists, cards, and checklists via AstrBot commands and AstrBot tools.

## 新特性（v0.2.0）/ What's New (v0.2.0)

- 支持在部分查看/切换命令中使用名称代替 ID（看板、列表、卡片）。
  Support using names instead of IDs in selected view/switch commands (board, list, card).
- 在查看成功后自动更新当前会话上下文（`board_id` / `list_id` / `card_id`）。
  Viewing resources now updates session context automatically.
- 新增 3 个 AstrBot LLM tools：`trello_select`、`trello_read`、`trello_write`。
  Added 3 AstrBot LLM tools: `trello_select`, `trello_read`, `trello_write`.

## 命令列表（中文优先，英文对照）/ Commands (Chinese first, English reference)

- `/trello scope`：显示当前会话作用域（`unified_msg_origin`）。  
  Show current session scope (`unified_msg_origin`).
- `/trello help`：显示命令帮助。  
  Show command help.
- `/trello boards`：列出可访问的看板。  
  List available boards.
- `/trello board-create <name> | <description>`：创建看板。  
  Create a board.
- `/trello board-info [board_id|name]`：显示看板详情（未传时使用默认看板；成功后会更新当前看板上下文）。  
  Show board details (fallback to default board).
- `/trello board-archive [board_id]`：归档看板（未传时使用默认看板）。  
  Archive board (fallback to default board).
- `/trello use-board <board_id|name>`：设置当前会话默认看板（仅管理员）。  
  Set default board for current session (admin only).
- `/trello lists [board_id|name]`：列出看板中的列表（成功后会更新当前看板上下文）。  
  List lists on board (and update current board context on success).
- `/trello list-create <name>`：在默认看板中创建列表。  
  Create list in default board.
- `/trello list-create <board_id> | <name>`：在指定看板中创建列表。  
  Create list in specific board.
- `/trello list-rename <list_id> | <new_name>`：重命名列表。  
  Rename list.
- `/trello list-archive [list_id]`：归档列表（未传时使用默认列表）。  
  Archive list (fallback to default list).
- `/trello use-list <list_id|name>`：设置当前会话默认列表（仅管理员；按名称时需要先选中看板）。  
  Set default list for current session (admin only).
- `/trello use-done <list_id>`：设置当前会话默认完成列表（仅管理员）。  
  Set default done list for current session (admin only).
- `/trello cards [list_id|name]`：列出列表中的卡片（未传时使用默认列表；成功后会更新当前列表上下文）。  
  List cards on list (fallback to default list, and update current list context on success).
- `/trello add <title> | <description>`：在默认列表中创建卡片。  
  Create card in default list.
- `/trello card <card_id|name>`：显示卡片详情（按名称查找时优先当前列表，其次当前看板；成功后会更新当前上下文）。  
  Show card details (name lookup prefers current list, then current board; updates current context on success).
- `/trello edit <card_id> <name|desc|due|list> <value>`：编辑卡片字段。  
  Edit card fields.
- `/trello move <card_id> <list_id>`：移动卡片到目标列表。  
  Move card to list.
- `/trello archive <card_id>`：归档卡片。  
  Archive card.
- `/trello delete <card_id>`：删除卡片。  
  Delete card.
- `/trello comment <card_id> | <text>`：给卡片添加评论。  
  Add card comment.
- `/trello done <card_id>`：将卡片移动到默认完成列表。  
  Move card to default done list.
- `/trello find <keyword>`：在默认看板中搜索卡片。  
  Search cards in default board.
- `/trello checklists <card_id>`：查看卡片上的检查清单及条目。  
  List checklists and items on card.
- `/trello checklist-create <card_id> | <name>`：创建检查清单。  
  Create checklist.
- `/trello checklist-add <checklist_id> | <item_name>`：添加检查项。  
  Add checklist item.
- `/trello checklist-check <card_id> <check_item_id>`：标记检查项为完成。  
  Mark item complete.
- `/trello checklist-uncheck <card_id> <check_item_id>`：标记检查项为未完成。  
  Mark item incomplete.
- `/trello checklist-delete <checklist_id>`：删除检查清单。  
  Delete checklist.

## 权限与作用域 / Permissions and Scope

- 管理员命令使用 AstrBot 管理员权限检查。  
  Admin commands use AstrBot admin permission checks.
- 群聊与私聊按 `event.unified_msg_origin` 隔离。  
  Group and private chats are isolated by `event.unified_msg_origin`.
- 默认看板/列表设置按会话保存。  
  Default board/list settings are saved per session.
- 当前卡片上下文（`card_id`）也按会话保存。  
  Current card context (`card_id`) is also saved per session.

## AstrBot LLM Tools / AstrBot 工具函数

- `trello_select`
  Resolve `board/list/card/checklist` by `id_or_name` and switch current session context.
- `trello_read`
  Unified read tool for `board/list/card/checklist/checklist_item` with `mode=list|get`.
- `trello_write`
  Unified write tool for `board/list/card/checklist/checklist_item` with `action=create|update|delete`.

### Tool usage notes

- `trello_read` / `trello_write` support `parent_resource` + `parent_id_or_name` for scoped name lookup.
- `trello_write` delete actions require `confirm=true`.
- For `checklist_item` name lookup, pass checklist scope (`parent_resource="checklist"`).

## Token 存储 / Token Storage

- 在插件配置中填写 `trello_api_key` 和 `trello_token`。  
  Configure `trello_api_key` and `trello_token` in plugin config.
- 凭据以明文保存在 `data/config` 下的插件配置文件中。  
  Values are stored as plain text in plugin config file under `data/config`.
