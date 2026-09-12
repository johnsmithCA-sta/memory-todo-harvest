# 版本史

## 1.1.1

- **调整**：技能包内不再附带单独的 README —— 说明文档统一收敛到 `SKILL.md` 与
  `references/`，安装后的目录更干净（GitHub 仓库首页仍保留完整图文说明）
- **调整**：技能自述改用与生态无关的表述，不再点名具体产品；
  支持的具体来源清单在正文「支持的记忆来源」与「触发词」两节完整保留

## 1.1.0

- **新增默认产物 `todos.html`**：归集后自动生成一份**自包含**的可视化待办清单页面
  （内联 CSS / JS、零外部依赖、离线可看）；按项目分组、项目与状态筛选、
  分组折叠、事由 / 来源 / 日期徽章、勾选状态存 localStorage
- **新增勾选写回闭环**：页面「导出勾选结果」→ `harvest.py --apply-checked checked.json`
  → 更新清单与判定档案（含取消勾选的撤销），并自动重新渲染页面
- 新增 `--no-html`（只要数据不要页面）；`render_html` / `html_out` 两个配置项
- **品牌名与描述口径调整**：README 与 SKILL.md 的对比 / 边界说明改为**能力类别**表述，
  不点名任何具体产品；对比表口径改为「互补 / 相邻」而非优劣

## 1.0.1

- **触发词章节改为短短语**：由「意译长句」改为用户会真实说出口的短语
  （待办散落在各处 / 提取待办 / 统一清单 / 记忆文件 / 会话记录 / 属于哪个项目 …
  以及英文 extract todos、harvest todos、agent memory），共 32 条
- **新增触发词评估集** `evals/trigger_eval.json`：12 条中文真实说法 + 8 条相邻但不该触发的请求，
  用于校验 description 的触发精准度
- **新增** `references/Changelog.md`
- 「不触发」场景独立成节，与触发词分离

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
