# memory-todo-harvest · 记忆待办归集

> 技能本体位于 `skills/memory-todo-harvest/`；本文件为仓库首页说明。

> **Turn your agent's memory files and rule files into a real, checkable todo list — with noise control, project attribution and loss-proof manual verdicts.**
> **把 agent 的记忆文件与规则文件，变成一份真正能用、能勾、能分组的待办清单——带噪音控制、项目归属与不丢判定。**

`归集 / Harvest` · `待办 / Todo` · `本地优先 / Local-first` | MIT License | Python 3.8+ (stdlib only)

---

## ✨ Why memory-todo-harvest? / 为什么选它？

Agent 每天写下大量记忆流水与规则文件。待办**确实写在里面**，但两份现实让"直接扫出来当清单"行不通：

1. **流水账里绝大多数是已完成的记录**——不做口径设计，真实待办会被淹没（活动记录与待办的数量级差可达 50 倍）；
2. **做完了通常不会回头改原条目**——所以"自动判断哪条已完成"这件事，旁证召回只有个位数百分比，而猜错就**错误关闭真实待办**。

主流方案解决的是"**把任务管起来**"；这个技能解决的是"**从已经写下的东西里，把待办稳妥地捡出来**"。

| 维度 | 现役主流方案 | memory-todo-harvest |
|---|---|---|
| **数据源** | 新建任务库（SQLite / 自建 TODO 暂存区） | **已有的 agent 记忆文件与规则文件**，不要求改变记录习惯 |
| **取数方式** | 人工录入 / 命令添加 | **从记忆流水与规则清单里按口径抽取** |
| **噪音控制** | 不涉及（数据源本身就是任务） | **三类待办信号 + 长期档案只取显式标记** |
| **归属** | 靠用户手动打标签 | **项目锚定五路打分，自动判项目与事由** |
| **判定安全** | 状态即事实 | **候选确认 + 独立判定档案 + 分级模糊匹配，误收可撤回、标题改了也不丢** |
| **运行依赖** | 常需数据库 / 框架 | **纯标准库单脚本，离线可跑** |

---

## 🆚 Comparison / 与主流方案对比

> 下表只描述**能力类别**，不点名任何具体产品——选型对比看的是定位差异，不是谁更好。

| 类别 | 典型形态 | 定位 | 与本品的关系 |
|---|---|---|---|
| **Agent 侧待办引擎** | 技能 / 跨会话暂存区 | 任务、提醒、跟进的执行与暂存 | **互补**。它们管理「新建的任务」，本技能负责「从既有记忆里取出来」——取出来的清单正好可以喂给它们继续管 |
| **工作区待办库** | 本地 SQLite / 文件数据库 | 待办的增删改查与分组 | **互补**。数据源是独立任务库；本技能的数据源是记忆文件与规则文件，两者场景不同 |
| **笔记库任务抽取 CLI** | 命令行工具（部分带 MCP） | 从笔记仓库里抽 checkbox 任务 | **相邻**。面向结构化的笔记仓库；本技能面向 agent 自己写下的记忆流水与规则文件，并处理「活动记录 vs 待办」的口径问题 |
| **笔记软件任务插件** | 编辑器插件 | 笔记内的任务视图 | **相邻**。体验成熟但绑定单一笔记产品；本技能面向多 agent、多目录混装的场景 |
| **笔记任务抽取连接器** | MCP 连接器 | 把笔记任务喂给 LLM | **相邻**。做「取出来」，不做归属判定、误收兜底与判定持久化 |

**One-liner / 一句话定位**：*Others help you manage the tasks you create; this one harvests the todos you already wrote — and tries hard not to get them wrong.*
—— 别人帮你管你**新建**的任务，这个技能把你**已经写下**的待办捡出来，并且尽量不出错。

---

## 🎯 What it does / 它做什么

四层设计，每层解决一类具体失败：

| 层 | 解决的问题 | 做法 |
|---|---|---|
| **归集口径** | 抽出来全是噪音 | 只认三类显式信号；长期档案只取显式标记 |
| **防误收兜底** | 抽错了怎么办 | 候选制（新条目先确认）+ 独立判定档案 + 分级模糊匹配 |
| **归属补全** | 看不出是哪条线的 | 五路信号加权打分；**项目锚**回溯抗标题更替 |
| **呈现** | 用起来是否顺手 | 项目分组、折叠稳定键、勾选不重排、批量可逆 |

---

## 📂 Supported sources / 支持的记忆来源

### 记忆目录（按天 / 按主题的流水与档案）

| 生态 | 典型路径 |
|---|---|
| 通用 agent 工作区 | `<项目>/.workbuddy/memory/*.md` |
| Claude Code 自动记忆 | `~/.claude/projects/<项目>/memory/*.md` |
| 记忆库模式 | `<项目>/memory-bank/*.md` |
| 其他 agent 状态目录 | `.codex/` `.cursor/` `.serena/memories/` `.agents/` 等 |

判定 = **目录名命中** 且 **父目录链出现 agent 状态目录标记**——两个条件都要，
避免把普通项目里叫 `memory/` 的目录误纳。

### 指令 / 规则文件（长期档案）

`AGENTS.md` · `AGENTS.override.md` · `CLAUDE.md` · `CLAUDE.local.md` · `GEMINI.md` ·
`.cursorrules` · `.cursor/rules/*.mdc` · `.github/copilot-instructions.md` ·
`.windsurfrules` · `.clinerules` · `.roorules` · `CONVENTIONS.md` · `WARP.md` · `TODO.md`

这些文件同时装着规则正文与真正的待办清单，因此按「长期档案」处理：
**只认未勾选 checkbox 与「待办：」标记行**，不把章节正文整段当待办。

> 同一套配置可以同时收多个生态的内容，混在一张清单里。

---

## 🚀 Quick start

```bash
# 1. 生成配置模板
python3 skills/memory-todo-harvest/scripts/harvest.py --init

# 2. 填 roots / projects(keywords) / container_dirs，然后先看不写盘
python3 skills/memory-todo-harvest/scripts/harvest.py --dry-run

# 3. 抽样核准（准确率 ≥ 90% 再继续）
python3 skills/memory-todo-harvest/scripts/harvest.py --dry-run --sample 60

# 4. 写盘（再跑一遍确认幂等）
python3 skills/memory-todo-harvest/scripts/harvest.py
```

**产出**（默认三件套，落盘在 `todos.json` 同目录）：

| 文件 | 是什么 | 能不能删 |
|---|---|---|
| `todos.json` | 结构化待办清单（归集产物，每次全量重建） | 删了重跑就有 |
| `todo-state.json` | **人工判定档案**（勾选/忽略记录，与清单解耦） | **别删**——你的判定都在这里 |
| `todos.html` | **可视化清单页面，默认产物**（自包含、离线可看） | 删了重跑就有 |

### 看清单 + 勾完成的闭环

```bash
# 归集后会自动生成 todos.html，双击即可打开
python3 skills/memory-todo-harvest/scripts/harvest.py

# 在页面里勾选 → 点「导出勾选结果」得到 checked.json
# 再把勾选写回清单与判定档案：
python3 skills/memory-todo-harvest/scripts/harvest.py --apply-checked ./checked.json

# 只想要数据、不要页面：
python3 skills/memory-todo-harvest/scripts/harvest.py --no-html
# 或单独渲染：
python3 skills/memory-todo-harvest/scripts/render_todos.py --data ./todos.json --out ./todos.html
```

页面**不直接改磁盘文件**（浏览器做不到），所以写回走「导出 + 一行命令」两步。
这样清单数据和人工判定始终在你自己的磁盘上，页面只是视图。

---

## ⚙️ Config / 配置

| 键 | 作用 | 建议 |
|---|---|---|
| `roots` | 扫描根目录 | 工作区容器根 + agent 家目录 |
| `projects` | 项目台账：`id` / `name` / `keywords` | **中文项目名必须写 keywords**，别名写全 |
| `container_dirs` | 容器目录名（不是项目本身） | 登记放项目的上层目录 |
| `dir_project_map` | 目录名 → 项目名 | 目录名与项目名不一致时补 |
| `memory_dir_names` / `agent_state_dirs` | 记忆目录判定 | 默认覆盖主流 agent |
| `longterm_files` | 按长期档案处理的文件名 | 默认含各家指令文件 |
| `stale_days` | 未完成超过几天算「历史遗留」 | 默认 14 |

---

## ✅ Verification / 验收

- [ ] `--dry-run` 命中量落在几十条量级（上千条 = 口径配错）
- [ ] 抽样 60 条，人工准确率 ≥ 90%
- [ ] 连跑两遍输出一致（幂等）
- [ ] 未分类接近 0；不为 0 时先查项目台账是否缺项
- [ ] 手动勾一条 → 清空产物重跑 → 判定仍在
- [ ] 清单里不含密码 / token 明文

---

## 📖 Docs

| 文件 | 内容 |
|---|---|
| `skills/memory-todo-harvest/SKILL.md` | 完整工作流、机制、配置、触发词 |
| `skills/memory-todo-harvest/references/配置与排障.md` | 按现象查处置 |
| `skills/memory-todo-harvest/references/口径说明.md` | 归类行为说明与边界 |
| `skills/memory-todo-harvest/scripts/render_todos.py` | 清单 → 本地 HTML 页面 |
| `skills/memory-todo-harvest/references/Changelog.md` | 版本史 |

---

## License

MIT © 2026 johnsmithCA-sta
