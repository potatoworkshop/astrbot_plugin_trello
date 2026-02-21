# Trello 控制插件 / Trello Control Plugin

通过 AstrBot 指令控制 Trello 看板和卡片。  
Control Trello boards and cards via AstrBot commands.

## 命令列表（中文优先，英文对照）/ Commands (Chinese first, English reference)

- `/trello scope`：显示当前会话作用域（`unified_msg_origin`）。  
  Show current session scope (`unified_msg_origin`).
- `/trello help`：显示命令帮助。  
  Show command help.
- `/trello boards`：列出可访问的看板。  
  List available boards.
- `/trello board-create <name> | <description>`：创建看板。  
  Create a board.
- `/trello board-info [board_id]`：显示看板详情（未传时使用默认看板）。  
  Show board details (fallback to default board).
- `/trello board-archive [board_id]`：归档看板（未传时使用默认看板）。  
  Archive board (fallback to default board).
- `/trello use-board <board_id>`：设置当前会话默认看板（仅管理员）。  
  Set default board for current session (admin only).
- `/trello lists [board_id]`：列出看板中的列表。  
  List lists on board.
- `/trello list-create <name>`：在默认看板中创建列表。  
  Create list in default board.
- `/trello list-create <board_id> | <name>`：在指定看板中创建列表。  
  Create list in specific board.
- `/trello list-rename <list_id> | <new_name>`：重命名列表。  
  Rename list.
- `/trello list-archive [list_id]`：归档列表（未传时使用默认列表）。  
  Archive list (fallback to default list).
- `/trello use-list <list_id>`：设置当前会话默认列表（仅管理员）。  
  Set default list for current session (admin only).
- `/trello use-done <list_id>`：设置当前会话默认完成列表（仅管理员）。  
  Set default done list for current session (admin only).
- `/trello cards [list_id]`：列出列表中的卡片（未传时使用默认列表）。  
  List cards on list (fallback to default list).
- `/trello add <title> | <description>`：在默认列表中创建卡片。  
  Create card in default list.
- `/trello card <card_id>`：显示卡片详情。  
  Show card details.
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

## Token 存储 / Token Storage

- 在插件配置中填写 `trello_api_key` 和 `trello_token`。  
  Configure `trello_api_key` and `trello_token` in plugin config.
- 凭据以明文保存在 `data/config` 下的插件配置文件中。  
  Values are stored as plain text in plugin config file under `data/config`.
