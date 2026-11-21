# Builtin Commands Extension

这是 AstrBot 的内置指令扩展插件，同时兼容 AstrBot `v4.23+` 和 `v4.30.0-beta.1+`。

从 AstrBot `builtin_commands` 中迁出的非核心指令会放在这里维护。核心内置指令仍保留在 AstrBot 主程序中，包括：

- `/help`
- `/sid`
- `/name`
- `/reset`
- `/stop`
- `/new`
- `/stats`
- `/provider`
- `/dashboard_update`
- `/set`
- `/unset`

## 提供的指令

本插件提供以下扩展指令：

- `/llm`：开启或关闭 LLM 聊天功能（在 AstrBot `v4.30+` 下为当前会话写入覆盖，支持 `/llm --inherit` 恢复继承）
- `/plugin`：插件管理（`ls` / `on` / `off` / `get` / `help`）
- `/op`：授权管理员
- `/deop`：取消管理员授权
- `/model`：查看或切换模型
- `/history`：查看对话记录
- `/ls`：查看对话列表
- `/groupnew`：创建群聊对话
- `/switch`：切换对话
- `/rename`：重命名当前对话
- `/del`：删除当前对话
- `/persona`：查看或切换 Persona（在 AstrBot `v4.30+` 下支持 `/persona --inherit` 恢复继承）

## 说明

该插件复用 AstrBot 原有内置指令实现，目录结构与原 `astrbot/builtin_stars/builtin_commands` 保持一致：

```text
builtin_commands_extension/
├── main.py
├── metadata.yaml
└── commands/
```

如需禁用这些扩展指令，可以在 WebUI 的插件管理中停用 `builtin_commands_extension`。
