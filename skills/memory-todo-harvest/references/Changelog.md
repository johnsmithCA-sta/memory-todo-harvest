# 版本史

## 1.0.0

首个版本。

- **归集口径**：只认三类显式待办信号（待办语义章节 / 未勾选 checkbox / 行内待办句）；
  指令与规则文件按「长期档案」处理，只取显式标记，不把章节正文整段当待办
- **多生态来源**：覆盖 `AGENTS.md`、`CLAUDE.md`、`CLAUDE.local.md`、`GEMINI.md`、
  `.cursorrules`、`.windsurfrules`、`.clinerules`、`.roorules`、`copilot-instructions.md`、
  `CONVENTIONS.md`、`WARP.md`、`TODO.md`，以及 `.workbuddy/memory`、
  `.claude/projects/*/memory`、`memory-bank` 等记忆目录
- **防误收兜底**：候选制（仅对增量生效）+ 独立判定档案（与归集产物解耦）+
  分级模糊匹配（同文件 0.6 / 跨文件 0.85，Jaccard 相似度）
- **归属补全**：五路信号加权打分（标题 / 上下文 / 项目锚 / 文件主题 / 目录）；
  项目锚支持同级标题更替后的回溯，容器目录不参与项目判定
- **事由标签净化**：剥前导时间戳、括号补充、破折号后缀；结构词黑名单
- **配置驱动**：`roots` / `projects(keywords)` / `container_dirs` / `dir_project_map` /
  `memory_dir_names` / `agent_state_dirs` / `longterm_files` / `stale_days`
- 纯标准库单脚本，支持 `--init` / `--dry-run` / `--sample`
