# 换 agent 接着开发

此目录用于跨软件交接。通用开发约定在根目录 `AGENTS.md`；`CLAUDE.md` / `GEMINI.md` 只是指向同一份约定的入口，避免各维护一套冲突要求。

建议在其他 agent 软件中打开 **项目根目录**（本机通常为桌面的 `AIPictures`），发送：

> 请先读取 AGENTS.md、.agent/HANDOFF.md，以及存在时的 .agent/STATE.local.md。根据实际 Git 状态和日志接续未完成任务。先核对已有 ComfyUI 后台任务，不重复提交、不覆盖旧结果；先简要说明目前进度再继续。

不自动读取这些文件的软件，也可以直接粘贴上述内容。这里只交接文件中的上下文，不迁移聊天记录、账号、API 密钥、订阅或模型额度，也不会自动切换正在使用的 agent。

- `HANDOFF.md`：可提交的项目和任务进展，避免写个人路径和密钥。
- `STATE.local.md`：本机路径、在运行的任务、输出与日志，仅保留本机，由 Git 忽略。内容可能过期，读取时检查时间和日志。
- 更换电脑：按 README 安装依赖、配置自己的 ComfyUI；用户图片、模型和 `data/` 不随 Git 克隆。

更新约定只改 `AGENTS.md`，更新进度改交接记录。无需安装新的代理服务或转发订阅。

文件入口格式参考 [Claude Code 项目记忆说明](https://code.claude.com/docs/en/memory) 和 [Gemini CLI 项目上下文说明](https://geminicli.com/docs/cli/gemini-md/)。
