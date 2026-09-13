#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harvest.py — 从 agent 记忆文件打捞待办清单
=====================================================================================
扫描一组「记忆根目录」下的 <项目>/.workbuddy/memory/*.md，把散落在里面的待办事项
抽成一份结构化清单 todos.json，供本地页面渲染。

三类待办信号
  A) 待办语义章节  标题命中 待办 / TODO / 剩余待办 / 下一步 / 未完成 / 待处理 /
                   待执行 / 待确认 / 待跟进 / 待决策
                   → 章节标题作为「出处」，章节内列表项为待办
  B) 未勾选 checkbox   `- [ ] xxx` → 待办；`- [x] xxx` → 已完成
  C) 行内待办句        `**待办**：xxx` / `剩余待办：xxx`
                   → 一条待办；带 ①②③ 编号的自动拆分为多条

核心设计（每层都对应一个实测踩坑，详见 references/pitfalls.md）
  1. 口径反转：只有「待办」进清单，会话活动记录不进 —— 否则信噪比会到 1:49
  2. 项目锚定：条目归属不只看标题，按 标题/上下文/项目锚/文件主题/目录 五路打分
  3. 防误收兜底：候选制 + 独立判定档案 + 分级模糊匹配（标题被改也不丢判定）
  4. 陈旧标记：未完成超过 N 天的单独折叠，不混在当前待办里

用法
  python3 harvest.py --init                 # 生成 harvest.config.json 模板
  python3 harvest.py --dry-run              # 只统计不写盘（先看命中了什么）
  python3 harvest.py --dry-run --sample 60  # 附带抽样明细，用于人工核准确率
  python3 harvest.py                        # 正式写盘
  python3 harvest.py --config /path/cfg.json

  import harvest; harvest.find_log_files()   # 供本地服务调用（签名稳定，勿改）
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter

# ---------------------------------------------------------------- 配置
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "harvest.config.json")

DEF_EXCLUDE_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv",
                    "_archive", "dist", "build", ".next", ".next", "vendor",
                    "site-packages", ".mypy_cache", ".pytest_cache"]
DEF_EXCLUDE_FRAGS = ["/automations/"]        # 自动化流水日志目录，整目录跳过

# 「记忆目录」：agent 按天/按主题写下的流水与档案。命中其一即整目录纳入扫描。
DEF_MEMORY_DIR_NAMES = ["memory", "memories", "memory-bank", "journal", "notes"]
# 单独成名的记忆目录（名字本身足够独特，不必再靠父目录判定）
DEF_STANDALONE_MEMORY_DIRS = ["memory-bank"]
# agent 的状态目录标记：记忆目录通常位于其中之一下面，用父目录链判定可避免
# 把普通项目里叫 memory/ 的目录误当成 agent 记忆。
DEF_AGENT_STATE_DIRS = [".workbuddy", ".claude", ".codex", ".cursor", ".serena",
                        ".agents", ".agent", ".gemini", ".continue", ".trae",
                        ".aider", ".roo", ".cline", ".qoder", ".augment"]

# 「指令 / 规则文件」：人或 agent 维护的长期档案。它们里面既可能有规则正文、
# 也可能有真正的待办清单，所以统一按「长期档案」处理——只认显式待办信号
# （未勾选 checkbox 与「待办：」标记行），不把章节正文当待办。
DEF_LONGTERM = [
    "MEMORY.md",
    "AGENTS.md", "AGENTS.override.md",
    "CLAUDE.md", "CLAUDE.local.md",
    "GEMINI.md", "CONVENTIONS.md", "WARP.md", "NOTES.md", "TODO.md",
    ".cursorrules", ".windsurfrules", ".clinerules", ".roorules",
    "copilot-instructions.md",
]
# 指令文件扫描深度上限（防止把依赖目录里的 AGENTS.md 全捞进来）
DEF_INSTRUCTION_DEPTH = 3

CONFIG = {}          # 由 load_config() 填充


def load_config(path=None):
    """读取配置。缺项一律走默认值，保证「零配置也能跑」。"""
    cfg_path = path or os.environ.get("HARVEST_CONFIG") or DEFAULT_CONFIG
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            sys.stderr.write(f"[warn] 配置读取失败，改用默认值：{e}\n")
    cfg.setdefault("roots", [os.path.expanduser("~")])
    cfg.setdefault("out", os.path.join(HERE, "todos.json"))
    cfg.setdefault("state", os.path.join(HERE, "todo-state.json"))
    cfg.setdefault("schema", "memory_todo_v1")
    cfg.setdefault("projects", [])
    cfg.setdefault("exclude_dirs", DEF_EXCLUDE_DIRS)
    cfg.setdefault("exclude_path_frags", DEF_EXCLUDE_FRAGS)
    cfg.setdefault("longterm_files", DEF_LONGTERM)
    cfg.setdefault("memory_dir_names", DEF_MEMORY_DIR_NAMES)
    cfg.setdefault("standalone_memory_dirs", DEF_STANDALONE_MEMORY_DIRS)
    cfg.setdefault("agent_state_dirs", DEF_AGENT_STATE_DIRS)
    cfg.setdefault("scan_instruction_files", True)
    cfg.setdefault("instruction_depth", DEF_INSTRUCTION_DEPTH)
    cfg.setdefault("container_dirs", [])
    cfg.setdefault("dir_project_map", {})
    cfg.setdefault("stale_days", 14)
    cfg.setdefault("per_file_cap", 100)
    cfg.setdefault("render_html", True)          # 归集后自动生成 todos.html
    cfg.setdefault("html_out", "todos.html")     # 输出文件名（相对 data 所在目录）
    cfg["roots"] = [os.path.expanduser(r) for r in cfg["roots"]]
    for k in ("out", "state"):
        cfg[k] = cfg[k] if os.path.isabs(cfg[k]) else os.path.join(HERE, cfg[k])
    CONFIG.clear()
    CONFIG.update(cfg)
    return cfg


def ensure_config():
    """库调用（import harvest）时也能自动就位。"""
    if not CONFIG:
        load_config()
    return CONFIG


def _cfg(key, default=None):
    """配置取值；未初始化时自动加载（保证 import 后直接调用也不会炸）。"""
    if not CONFIG:
        load_config()
    return CONFIG.get(key, default)


def init_config(path=None):
    """生成配置模板。projects 留空时脚本会尽量从目录名兜底匹配。"""
    tpl = {
        "roots": ["~/Documents/work"],
        "out": "todos.json",
        "state": "todo-state.json",
        "schema": "memory_todo_v1",
        "stale_days": 14,
        "memory_dir_names": DEF_MEMORY_DIR_NAMES,
        "agent_state_dirs": DEF_AGENT_STATE_DIRS,
        "longterm_files": DEF_LONGTERM,
        "scan_instruction_files": True,
        "render_html": True,
        "html_out": "todos.html",
        "_note_container_dirs": "放项目的容器目录名，它们不是项目本身",
        "container_dirs": [],
        "_note_dir_map": "目录名 → 项目台账里的项目名（中文项目名必须显式映射）",
        "dir_project_map": {},
        "_note_projects": "keywords 要写全别名：产品名/简称/错误码/关键术语都算",
        "projects": [
            {"id": "p_alpha", "name": "项目 Alpha",
             "keywords": ["alpha", "阿尔法"], "stage": "", "next": "", "blocker": ""}
        ],
    }
    p = path or DEFAULT_CONFIG
    with open(p, "w", encoding="utf-8") as f:
        json.dump(tpl, f, ensure_ascii=False, indent=1)
    return p


# ---------------------------------------------------------------- 待办信号定义
# A) 待办语义章节关键词（清洗后的标题以此开头或等于）
TODO_SECTION_WORDS = (
    "待办", "todo", "剩余待办", "下一步", "未完成", "待处理",
    "待执行", "待确认", "待跟进", "待决策", "待补充", "遗留项",
)

# C) 行内待办标记：允许出现在行内任意位置（如 MEMORY.md 的
#    「- **技能数据看板** …。**待办**：`gho_` token 换 fine-grained PAT」）
RE_INLINE_TODO = re.compile(
    r"(?:^|[\s；;。，,、）)】>*-])[\u4e00-\u9fff]{0,6}\**\s*"
    r"(?:待办|待办提醒|待办事项|剩余待办|待处理|待执行|待确认|待跟进|待决策)"
    r"\**\s*[:：]\s*(\S.*)$", re.I)
RE_CIRCLED = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")

# 凭据掩码：待办文本里不得出现密码/token 明文（对齐 PLAYBOOK「只记指针不记值」）
RE_SECRET = re.compile(r"(密码|口令)\s*(?:已有|已为|为|是)?\s*[:：]\s*[^\s，。；;)）]+")

# B) checkbox
RE_CHECKBOX = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.+)$")
RE_BULLET = re.compile(r"^\s*[-*+]\s+(.+)$")
RE_HEADING = re.compile(r"^(#{2,4})\s+(.*)$")

# ---------------------------------------------------------------- 状态信号白名单
DONE_TRUE = [
    "✅", "已兑现", "已交付", "已验证", "已完成", "已修复", "已落地", "已上线", "已执行",
    "已通过", "已闭环", "已解决", "已入库", "已归档", "已发布", "已同步", "已整改",
    "已回写", "已更新", "已合并", "已打包", "全部完成", "全通", "入库成功",
    "部署完成", "打包完成", "验证成功", "发布完成", "整改完成", "迁移完成", "改造完成",
]
DONE_FALSE = [
    "未做", "未执行", "未拍板", "未修", "未完", "未完成", "未上线", "未发布", "未落地",
    "未验证", "未解决", "未采纳", "未成", "未交付", "未启动", "未动",
    "待用户拍板", "待用户", "待拍板", "待决策", "待确认", "待排查", "待复盘", "待授权",
    "待执行", "待下次", "留待", "下次", "进行中", "在跑", "调研中",
    "仅方案", "仅调研", "仅建议", "仅本机", "暂停", "待定",
    "下一步", "TODO", "待实施", "待落地", "待补", "待更新",
]
DONE_ABANDONED = ["叫停", "已放弃", "不做了", "搁置", "不采纳", "暂缓", "暂不动", "暂不"]
WEAK_TRUE = ["完成", "成功", "通过"]
NEG_PREFIX = ("未", "尚未", "还没", "没有", "待", "未能够")
NOTE_PREFIX = ("💡", "⚠️", "❌", "🔥", "📌", "❗")

# 时间前缀清洗
RE_TIME_LONG = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?:[：:-]\d{1,2}:\d{2})?\s*")
RE_TIME_RANGE = re.compile(r"^\d{1,2}:\d{2}\s*[xX]?\s*[–\-~至]\s*\d{1,2}:\d{2}\s*[xX]?\s*")
RE_TIME_ONE = re.compile(r"^\d{1,2}:\d{2}\s*[xX]?\s*")
RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
RE_HEAD_JUNK = re.compile(r"^(?:\s|【[^】]{0,20}】|《[^》]{0,40}》|[^\w\u4e00-\u9fff])+")
RE_SPACES = re.compile(r"\s{2,}")

# ---------------------------------------------------------------- 项目关联（只匹配，不新建）
PROJECT_STOPWORDS = {
    "优化", "升级", "收尾", "迭代", "整改", "交付", "基线", "自动", "化", "推进",
    "技能", "安全", "阶段", "计划", "与", "和", "的", "工作", "项目", "研究",
}


# ================================================================ 基础工具
def log(msg):
    print(msg, flush=True)


def load_wb():
    if not os.path.isfile(_cfg("out")):
        return {"schema": _cfg("schema"), "tasks": [], "projects": [], "sessions": []}
    try:
        with open(_cfg("out"), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[warn] workbench.json 读取失败：{e}")
        return {"schema": _cfg("schema"), "tasks": [], "projects": [], "sessions": []}


def save_wb(d):
    d["updated"] = int(time.time() * 1000)
    tmp = _cfg("out") + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cfg("out"))          # 原子替换：中途失败不会留半个文件


def today_str():
    return dt.date.today().isoformat()


def _age_days(date_str):
    """距今天数；无法解析返回 0（视为不陈旧）。"""
    try:
        d = dt.date.fromisoformat(str(date_str))
    except Exception:
        return 0
    return (dt.date.today() - d).days


# ================================================================ 归集口径常量
# 显式待办标记：inline = `**待办**：xxx`（含 ①②③ 拆分），checkbox = `- [ ] xxx`。
# 这两类是人**主动写下**的待办，不属于「机器从正文推断」——归集时直接转正，
# 不进「新发现 · 待确认」。候选制的价值在于拦住推断出来的条目；对显式标记
# 再要一遍人工确认属重复劳动。
EXPLICIT_SRC = {"inline", "checkbox"}


# ================================================================ 文本清洗
TITLE_MAX = 200
# 标题长度上限。取值要**容得下完整的一句话**：待办正文常带长路径、命令或说明，
# 截得太短会只剩半句（例如「…（tag 」），清单上看不出这条待办到底在讲什么。


def mask_secret(text):
    """待办文本内的凭据明文一律掩码（本地文件同样执行，防误传/误截图）。"""
    return RE_SECRET.sub(lambda m: f"{m.group(1)}：***（已掩码）", text or "")


def clean_item(raw):
    """待办条目文本清洗：去 markdown 标记 / 链接 / 首部时间戳 / 凭据明文。"""
    t = (raw or "").strip()
    t = RE_MD_LINK.sub(r"\1", t)
    t = t.replace("`", "").replace("**", "").replace("__", "")
    for _ in range(2):
        t2 = RE_TIME_LONG.sub("", t)
        t2 = RE_TIME_RANGE.sub("", t2)
        if t2 == t:
            break
        t = t2
    t = RE_TIME_ONE.sub("", t)
    t = t.strip(" ：:—-–·、,，.。;；")
    t = RE_SPACES.sub(" ", t)
    return mask_secret(t)[:TITLE_MAX]


def clean_heading(raw):
    """章节标题清洗（用于判断是否为待办章节、以及作为出处名）。"""
    t = (raw or "").strip().replace("`", "").replace("**", "")
    for _ in range(3):
        t2 = RE_HEAD_JUNK.sub("", t)
        if t2 == t:
            break
        t = t2
    for _ in range(3):
        t2 = RE_TIME_LONG.sub("", t)
        t2 = RE_TIME_RANGE.sub("", t2)
        t2 = RE_TIME_ONE.sub("", t2)
        if t2 == t:
            break
        t = t2.strip()
    return RE_SPACES.sub(" ", t).strip(" ：:—-–·、,，.。")


def is_todo_section(title):
    """是否为「待办语义」章节。

    必须严格：章节名**以「待办」开头但在讲别的事**（例如执行记录里的
    「待办上下文补全（同日 22:4x…）」）不能算作待办章节 —— 否则整节内容
    会被逐条捞成待办。2026-09-11 实测：一条执行记录误贡献 12 条垃圾待办。

    规则：去掉括号补充后的核心词，必须**等于**关键词，或只多出极短限定
    （如「待办迁移」「下一步计划」）。
    """
    t = (title or "").strip().lower()
    if not t:
        return False
    core = re.sub(r"[（(【\[].*?[）)】\]]", "", t).strip(" ：:—-·、。")
    if not core:
        return False
    for w in TODO_SECTION_WORDS:
        if core == w:
            return True
        if core.startswith(w) and len(core) <= len(w) + 2:
            return True
    return False


def detect_status(text):
    """返回 (done: bool|None, signal: str)。无信号 → (None, '')。

    优先级：终结信号（叫停/放弃→归档）> 否定 > 强真 > 弱真。
    """
    h = text or ""
    if h.lstrip().startswith(NOTE_PREFIX):
        return None, ""
    for w in DONE_ABANDONED:
        if w in h:
            return True, w
    for w in DONE_FALSE:
        if w in h:
            return False, w
    for w in DONE_TRUE:
        if w in h:
            return True, w
    for w in WEAK_TRUE:
        idx = h.find(w)
        while idx != -1:
            prefix = h[max(0, idx - 3):idx]
            if not any(prefix.endswith(p) for p in NEG_PREFIX):
                return True, w
            idx = h.find(w, idx + 1)
    return None, ""


def load_todo_state():
    """人工判定档案：{done:{...}, dismissed:{...}, assigned:{...}}。

    与归集产物解密：重新归集时判定不会丢，可单独备份；
    标题微调导致 id 漂移时靠模糊匹配兜住。

    · done       —— 已完成（页面勾选写回）
    · dismissed  —— 已忽略（不再捞回）
    · assigned   —— 人工指定的归属（页面调整分组后写回）。归集时优先于自动
                    打分；只改产物不写这里，下次归集就会被重算覆盖。
    """
    empty = {"done": {}, "dismissed": {}, "assigned": {}}
    if not os.path.isfile(_cfg("state")):
        return empty
    try:
        with open(_cfg("state"), encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("done", {})
        d.setdefault("dismissed", {})
        d.setdefault("assigned", {})
        return d
    except Exception as e:
        log(f"[warn] todo-state.json 读取失败：{e}")
        return empty


def save_todo_state(st):
    st["schema"] = "wb_todo_state_v1"
    st["updated"] = int(time.time() * 1000)
    tmp = _cfg("state") + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cfg("state"))


def norm_title(t):
    """标题规范化：去标点 / 空白 / 反引号 / 大小写差异，只留字母数字与汉字。

    用于跨版本比对「是不是同一条待办」——源文本被改写后原文不同，
    规范化后才看得出是同一件事。
    """
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(t or "").lower())


def title_grams(t):
    t = norm_title(t)
    return set(t[i:i + 2] for i in range(len(t) - 1)) if len(t) >= 2 else set()


def title_sim(a, b):
    """Jaccard 相似度：比「重叠系数」严格，避免短标题对长标题虚高。"""
    A, B = title_grams(a), title_grams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def title_overlap(a, b):
    """重叠率 = |A∩B| / min(|A|,|B|)：对「长标题被删补语」免疫。

    Jaccard 单独用有盲区：原文被删掉尾补语时，短标题的 gram 全落在长标题里，
    但分母仍是「并集」，分数会明显偏低（实测两条分别只有 0.562 / 0.395，
    双双跌破同文件阈值 0.6），于是已完成的条目会退回未完成、已忽略的会重新
    回到候选区 —— 表现就是「勾了又变回来 / 怎么点都消不掉」。

    重叠率对这种情况恒为 1.0。它只作为 Jaccard 之外的**受限补充通道**使用
    （见 resolve_state）：仅同文件、且规范化后短串足够长才启用，防止极短串乱吞。
    """
    A, B = title_grams(a), title_grams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def resolve_state(sid, title, logbase, st, same_file=0.6, cross_file=0.85,
                  containment=0.9, contain_min_len=6):
    """人工判定优先：先精确 id，再模糊标题（抗标题微调导致的 id 漂移）。

    分级阈值（实测标定）：
      · 同一记忆文件（同一 logBase）→ 宽松 0.6，冲突概率低（同文件的
        两条不同待办标题极少高度相似）
      · 跨文件 → 严格 0.85，且相似度先打 0.9 折，避免把别的待办误认成同一条

    补充通道（2026-09-13）：同文件内再加一条「包含关系」——短标题是长标题的
    子串（重叠率 ≥ 0.9）。原文被删掉尾补语时 Jaccard 会跌破 0.6，而重叠率仍是
    1.0；只认同文件、且规范化后短串 ≥ 6 字，避免极短串乱吞长标题。

    取向不变：宁可不匹配（退回未完成，人工再勾一次），也不能误匹配
    （错误关闭真实待办）。

    返回 (kind|None, matched_key)。kind ∈ {done, dismissed}
    """
    for kind in ("dismissed", "done"):
        if sid in (st.get(kind) or {}):
            return kind, sid
    nt = norm_title(title)
    best_sc, best_kind, best_key = 0.0, None, None
    for kind in ("dismissed", "done"):
        for k, v in (st.get(kind) or {}).items():
            lb = v.get("logBase") or ""
            vt = v.get("title") or ""
            same = bool(lb and logbase and lb == logbase)
            if same:
                score, need = title_sim(title, vt), same_file
            else:
                score, need = title_sim(title, vt) * 0.9, cross_file
            hit = score >= need
            if not hit and same and len(nt) >= contain_min_len:
                ov = title_overlap(title, vt)
                if ov >= containment:
                    hit, score = True, ov
            if hit and score > best_sc:
                best_sc, best_kind, best_key = score, kind, k
    if best_kind:
        return best_kind, best_key
    return None, None


def find_old_by_overlap(it, old_sessions, min_ratio=0.9, min_len=6):
    """同文件内按「包含关系」找回旧记录（供候选状态继承用）。

    与 resolve_state 的包含通道同源：源文本被改写后 id 变了，旧记录里的人工状态
    （已确认 pending=false / 已勾完成）必须跟着走，否则「已经处理过的任务」
    每次运行都会重新变成待确认候选。
    """
    nt = norm_title(it["title"])
    if len(nt) < min_len:
        return None
    best, best_ov = None, 0.0
    for s in old_sessions:
        if not s.get("id") or (s.get("logFile") or "") != it["logFile"]:
            continue
        ov = title_overlap(it["title"], s.get("title"))
        if ov >= min_ratio and ov > best_ov:
            best, best_ov = s, ov
    return best


def find_assigned_by_overlap(it, assigned, min_ratio=0.9, min_len=6):
    """同文件内按「包含关系」找回「人工指定归属」记录。

    与 find_old_by_overlap 同源。人工指定的归属要比完成 / 忽略更抗漂移 ——
    它不是「这条办完了」，而是「这条属于哪个项目」；一旦丢失，条目会退回
    自动打分的结果，表现为「调过的分组下次又变回去了」。
    记录里只有 logBase + title，所以按 logBase 判同文件。
    """
    nt = norm_title(it["title"])
    if len(nt) < min_len:
        return {}
    best, best_ov = None, 0.0
    for _sid, rec in (assigned or {}).items():
        if (rec.get("logBase") or "") != it["logBase"]:
            continue
        ov = title_overlap(it["title"], rec.get("title"))
        if ov >= min_ratio and ov > best_ov:
            best, best_ov = rec, ov
    return best or {}


def extract_context(before):
    """从「待办：」之前的前缀里提取项目/主题标识。

    存在意义：memory 的常见写法是
        `- **项目名**（状态）：说明。**待办**：具体事项`
    只抽「待办：」之后的内容会丢掉项目名，导致页面上只剩下
    「M3 实时行情 / 扩量回测」这类看不出归属的碎片（2026-09-11 用户实测反馈）。
    """
    t = before or ""
    m = re.search(r"\*\*([^*\n]{2,40})\*\*", t)      # 首个加粗片段 = 通常是项目名
    if m:
        return m.group(1).strip(" ：:—-·、。[]")
    m = re.search(r"[【《]([^】》]{2,30})[】》]", t)
    if m:
        return m.group(1).strip()
    return ""


CTX_BAD_PREFIX = ("用户问", "提问", "答疑", "说明", "备注", "背景", "原理", "什么是", "是什么")
CTX_MAX = 28

# 文档结构名：这些是「章节骨架」而非「项目/主题」，当上下文毫无信息量。
# 实测反馈：「### 未完成」下的待办上下文显示成「未完成」，等于没说。
CTX_STOPWORDS = {
    "待办", "待办事项", "待办清单", "下一步", "下一步计划", "下步", "未完成", "遗留",
    "遗留项", "待处理", "待执行", "待确认", "待跟进", "待决策", "待补充", "任务",
    "结果", "产出", "产物", "输出", "结论", "关键结论", "说明", "备注", "背景",
    "经验", "教训", "踩坑", "新踩坑", "验收", "验收结果", "复核", "复核清单",
    "备份", "归档", "最终状态", "执行方式", "关键改动", "关键发现", "硬教训补充",
    "流程教训", "一个流程教训", "收尾", "收尾同步", "编排", "时间预测", "三处改判",
}
RE_CTX_SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")   # 形如 my-skill / skill-dev-kit（首字符须是字母，挡掉纯日期）
RE_CTX_EN = re.compile(r"[A-Za-z]{3,}")


def is_ctx_stopword(c):
    """结构词判定：去括号后命中停用表，或形如「下一步（xxx）」这类。"""
    t = re.sub(r"[（(【\[].*?[）)】\]]", "", str(c or "")).strip(" ：:—-·、。")
    return (not t) or (t in CTX_STOPWORDS)


def ctx_score(c, proj_idx):
    """给候选上下文打分：命中已知项目 > 含英文 slug > 含英文 > 其他。"""
    s = 0
    if RE_CTX_SLUG.search(str(c or "").lower()):
        s += 2
    elif RE_CTX_EN.search(str(c or "")):
        s += 1
    if proj_idx and match_project(c, proj_idx)[0]:
        s += 3
    return s


def choose_context(cands, proj_idx):
    """从候选链里选最佳上下文。

    候选顺序 = [行内前缀, 当前章节, 父章节, …]（由近到远）。
    规则：先滤掉结构词，再按「含项目名/slug」打分，同分取更近的。
    """
    best, best_key = "", (-99, 0)
    for i, c in enumerate(cands):
        c = sanitize_context(c)
        if not c or is_ctx_stopword(c):
            continue
        key = (ctx_score(c, proj_idx), -i)
        if key > best_key:
            best, best_key = c, key
    return best


RE_CTX_LEADTIME = re.compile(r"^\d{1,2}:\d{2}(?:\s*[-–~至]\s*\d{1,2}:\d{2})?\s*[·:：]?\s*")
RE_CTX_PAREN = re.compile(r"[（(【\[].*?[）)】\]]")
RE_CTX_TAIL = re.compile(r"\s*(?:——|—|--|·|\|)\s*.*$")


def sanitize_context(c):
    """净化上下文标签：太长/太泛的都不适合做「这是什么项目」。

    实测踩坑（2026-09-11）：章节标题直接当上下文时会出两种噪音 ——
      · 过长被硬截断成 `my-skill 双平台发布完成（1…`
      · 问句章节标题（如「某次答疑：XX 是什么」）语义完全不搭
    """
    c = (c or "").strip(" ：:—-·、。[]")
    if not c or len(c) < 2:
        return ""
    if c.startswith(CTX_BAD_PREFIX):
        return ""
    if c.endswith(("？", "?")):
        return ""
    # 结构化剥离（实测反馈：`W3 收尾（17:45–17:59，墙钟 ≈14 min…`
    # 被硬截断成无意义的省略号尾巴）——先剥噪声，再判断长度
    c = RE_CTX_LEADTIME.sub("", c)                  # 前导时间戳 17:37-18:01 ·
    c = RE_CTX_PAREN.sub("", c)                     # 括号补充（时间/备注）
    c = RE_CTX_TAIL.sub("", c)                      # 破折号后缀 —— ✅ CP4 达成
    m = re.search(r"[「《『]([^」》』]{2,24})[」》』]", c)   # 标题里的引号内容往往更精炼
    if m:
        c = m.group(1)
    c = c.strip(" ：:—-·、。")
    if not c or len(c) < 2:
        return ""
    if len(c) > CTX_MAX:
        head = c[:CTX_MAX]
        cut = max(head.rfind(" "), head.rfind("+"), head.rfind("·"))
        if cut >= CTX_MAX * 0.6:          # 切在词边界，避免半个词 + 尾随空格
            head = head[:cut]
        c = head.rstrip(" ：:—-·、。+") + "…"
    return c


def in_backticks(line, pos):
    """pos 是否落在反引号包裹的行内代码里。

    存在意义：文档在举例说明「待办：」写法时（例如示例段落里写 `**待办**：xxx`），
    行内代码里的标记并不是真待办。不加这层排除，示例会被当成真待办捞进清单。
    """
    return line[:pos].count("`") % 2 == 1


def split_numbered(text):
    """带 ①②③ 编号的行内待办拆成多条；无编号则原样返回一条。"""
    t = (text or "").strip()
    if not RE_CIRCLED.search(t):
        return [t] if t else []
    parts = [p.strip(" ；;，,。.、") for p in RE_CIRCLED.split(t)]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else ([t] if t else [])


# ================================================================ 日志扫描
def _memory_dir_root(dp):
    """dp 若是「agent 记忆目录」，返回它所属的项目根；否则 None。

    判定 = 目录名命中 + 父目录链里出现 agent 状态目录标记。
    两个条件都要，否则普通项目里叫 memory/ 的目录会被误纳。
    """
    base = os.path.basename(dp)
    if base in _cfg("standalone_memory_dirs"):
        return os.path.dirname(dp)
    if base not in _cfg("memory_dir_names"):
        return None
    markers = set(_cfg("agent_state_dirs"))
    p = dp
    for _ in range(5):                       # 向上最多 5 层找状态目录标记
        parent = os.path.dirname(p)
        if not parent or parent == p:
            break
        if os.path.basename(parent) in markers:
            return os.path.dirname(parent)
        p = parent
    return None


def _iter_instruction_files(root):
    """在 root 下有限深度地找出「指令 / 规则文件」，返回 [(path, dir)]。"""
    names = set(_cfg("longterm_files"))
    max_depth = int(_cfg("instruction_depth") or 3)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in _cfg("exclude_dirs")]
        rel = os.path.relpath(dp, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > max_depth:
            dn[:] = []
            continue
        for f in sorted(fn):
            if f in names:
                yield os.path.join(dp, f), dp


def find_log_files():
    """返回 [(abs_path, project_root)]，按路径排序。

    覆盖两类来源：
      · 记忆目录：<项目根>/.workbuddy/memory/、~/.claude/projects/<proj>/memory/、
        memory-bank/ 等（由 memory_dir_names + agent_state_dirs 判定）
      · 指令文件：AGENTS.md / CLAUDE.md / GEMINI.md / 各编辑器规则文件等，
        按「长期档案」处理，只取显式待办信号

    供本地服务调用，签名稳定勿改。
    """
    ensure_config()
    out, seen = [], set()
    frags = _cfg("exclude_path_frags")
    for root in _cfg("roots"):
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in _cfg("exclude_dirs")]
            proj_root = _memory_dir_root(dp)
            if proj_root is None:
                continue
            for f in sorted(fn):
                if not f.endswith(".md"):
                    continue
                full = os.path.join(dp, f)
                if full in seen or any(fr in full for fr in frags):
                    continue
                seen.add(full)
                out.append((full, proj_root))

    if _cfg("scan_instruction_files"):
        for root in _cfg("roots"):
            if not os.path.isdir(root):
                continue
            for full, dirpath in _iter_instruction_files(root):
                if full in seen or any(fr in full for fr in frags):
                    continue
                seen.add(full)
                out.append((full, dirpath))

    out.sort()
    return out


def log_date_of(path):
    base = os.path.basename(path)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", base)
    if m:
        return m.group(1)
    try:
        return dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    except OSError:
        return today_str()


def parse_log_todos(path, proj_root, proj_idx=None):
    """解析单个记忆文件 → [todo dict]（未做去重与项目关联）。

    三类信号见模块 docstring。MEMORY.md（长期档案）只取行内待办标记。
    proj_idx：项目索引，用于给上下文打分（命中已知项目的候选优先）。
    """
    base = os.path.basename(path)
    date = log_date_of(path)
    longterm = base in _cfg("longterm_files")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except Exception as e:
        log(f"  [warn] 读取失败 {base}: {e}")
        return []

    items = []
    anchor_pool = []          # 本文件所有「能匹配到项目」的标题（用于推算文件主题）

    def add(text, done, signal, src, origin="", context=""):
        t = clean_item(text)
        if not t or len(t) < 2:
            return
        if t.startswith("（示例）") or "（示例）" in t:
            return
        items.append({
            "title": t,
            "done": done,
            "signal": signal,
            "src": src,                 # section / checkbox / inline
            "origin": origin,           # 出处：待办章节标题
            "context": context,         # 上下文：项目/主题标识（抗"看不出归属"）
            "date": date,
            "logFile": path,
            "logBase": base,
            "projRoot": proj_root,
            "anchor": cur_anchor_title,      # 最近的项目锚（章节标题级）
            "anchorLine": cur_anchor_line,
            "anchorDist": (lineno - cur_anchor_line) if cur_anchor_line else 99999,
            "lineNo": lineno,
            "docAnchor": "",                 # 文件主题，循环结束后回填
        })

    in_code = False
    cur_section = None       # 当前「待办语义」章节标题
    cur_level = 0
    cur_sec_done = None      # 章节标题携带的状态信号
    cur_sec_signal = ""
    cur_heading = ""         # 当前所在章节（**任意**层级）
    stack = []               # 章节树栈 [(level, title)]：上下文需要向上回溯（H1 不入栈）
    # 项目锚：最近一次「标题命中已知项目」的章节。
    # 关键：同级标题更替时**不清空**。真实记忆文件里常见
    #   ## 项目A 的需求梳理
    #   ## 17:37-18:01 · 第二轮联调
    # 后一个同级标题不含项目名；若按「同级即换段」清空，
    # 整个后续段落（可能几十条）的项目归属就全丢了。
    cur_anchor_title, cur_anchor_line = "", 0

    for lineno, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        mh = RE_HEADING.match(line)
        if mh:
            level, heading = len(mh.group(1)), mh.group(2).strip()
            title = clean_heading(heading)
            while stack and stack[-1][0] >= level:      # 维护祖先链
                stack.pop()
            if level >= 2 and title:
                stack.append((level, title))
            if title:
                cur_heading = title
            if proj_idx and title and match_project(title, proj_idx)[0]:
                cur_anchor_title, cur_anchor_line = title, lineno   # 更新项目锚
                anchor_pool.append(title)
            if not longterm and is_todo_section(title):
                cur_section, cur_level = title, level
                cur_sec_done, cur_sec_signal = detect_status(heading)
                continue
            if cur_section and level <= cur_level:
                cur_section, cur_sec_done, cur_sec_signal = None, None, ""
            continue

        if not line.strip():
            continue

        # C) 行内待办句（任意位置，含长期档案）—— 必须用 search：
        #    re.match 只从行首试一次，「…。**待办**：X」这类行中间标记会永远漏掉
        mi = RE_INLINE_TODO.search(line)
        if mi and not in_backticks(line, mi.start()):
            body = mi.group(1)
            # 状态只看待办正文，不能用整行：整行常含「已发布/已完成」等
            # 描述前文状态的词，会把待办本身误判为已完成（实测踩坑）
            d, sig = detect_status(body)
            # 候选链：行内前缀 → 当前章节 → 父章节 → …（近到远）
            cands = [extract_context(line[:mi.start()])]
            cands += [t for _lv, t in reversed(stack)]
            ctx = choose_context(cands, proj_idx)
            for p in split_numbered(body):
                add(p, d if d is not None else False, sig, "inline",
                    origin=cur_section or cur_heading or "", context=ctx)
            continue

        # B) checkbox —— 任何文件都认：`- [ ]` 是显式标记，零歧义。
        #    指令/规则文件（AGENTS.md、CLAUDE.md 等）常把待办写成清单，
        #    若沿用「长期档案只认行内标记」会把它们整批漏掉。
        mc = RE_CHECKBOX.match(line)
        if mc:
            done = mc.group(1).lower() == "x"
            d, sig = detect_status(mc.group(2))
            if d is not None and not done:
                done = d
            add(mc.group(2), done, sig or ("[x]" if done else "[ ]"), "checkbox",
                origin=cur_section or cur_heading or "",
                context=choose_context([cur_section or ""] + [t for _lv, t in reversed(stack)], proj_idx))
            continue

        if longterm:
            continue                      # 长期档案：不再把章节正文整段当待办

        # A) 待办章节内的列表项 / 段落
        if cur_section:
            mb = RE_BULLET.match(line)
            body = mb.group(1) if mb else line.strip()
            d, sig = detect_status(body)
            if d is None:                 # 条目无信号 → 继承章节信号，仍无则视为未完成
                d = cur_sec_done if cur_sec_done is not None else False
                sig = cur_sec_signal
            add(body, d, sig, "section", origin=cur_section,
                context=choose_context([cur_section or ""] + [t for _lv, t in reversed(stack)], proj_idx))

    # 文件主题：全文件出现最多的「带项目名的标题」。作为锚失效时的兜底信号。
    doc_anchor = ""
    if anchor_pool:
        doc_anchor = Counter(anchor_pool).most_common(1)[0][0]
    for it in items:
        it["docAnchor"] = doc_anchor

    if len(items) > _cfg("per_file_cap"):
        log(f"  [warn] {base} 命中 {len(items)} 条，超过上限 {_cfg("per_file_cap")}，已截断")
        items = items[:_cfg("per_file_cap")]
    return items


# ================================================================ 项目关联（只匹配，不新建）
def build_project_index(projects):
    """项目 → 关键词索引。

    关键词两处来源：
      1. 配置里显式写的 ``keywords`` —— 最可靠；**中文项目名必须靠它**
      2. 从项目名按分隔符切出的英文/长词 —— 兜底

    纯中文项目名无法按空格分词，只靠名字派生关键词时目录兜底永远匹配不上，
    条目会大批落「未分类」（实测一度 64%）。
    """
    idx = []
    for p in projects:
        kws = set(p.get("keywords") or [])
        for tok in re.split(r"[\s/、·（）()]+", p.get("name") or ""):
            tok = tok.strip()
            if not tok:
                continue
            if re.match(r"^[A-Za-z0-9._-]+$", tok):
                if len(tok) >= 3:
                    kws.add(tok)
            elif len(tok) >= 3 and tok not in PROJECT_STOPWORDS:
                kws.add(tok)
        for k in kws:
            idx.append((k, p))
    idx.sort(key=lambda x: -len(x[0]))
    return idx


# 匹配前先剥离「路径 / 点文件」片段：它们是路径，不是项目指代，却常包含项目或产品名。
# 典型误判：待办正文里写了 `.workbuddy/`、`~/.cursor/rules/xxx` 这类路径，
# 而某个项目名恰好是「WorkBuddy」或「cursor」——标题通道权重高于事由通道，
# 条目于是被从正确的项目抢进那个同名项目分组。
# 只剥离 ASCII 路径：正文里的中文必须原样保留。
RE_PATH_FRAG = re.compile(
    r"~?/[A-Za-z0-9._\-]*(?:/[A-Za-z0-9._\-]*)*"           # /abs/path、~/abs/path
    r"|\.[A-Za-z_][A-Za-z0-9._\-]*(?:/[A-Za-z0-9._\-]*)*"  # .workbuddy、.cursor/rules
)


def strip_path_frags(text):
    """剥离文本里的路径 / 点文件片段（仅供项目匹配使用）。

    注意字符类必须限定 ASCII：Python 的 \\w 默认含汉字，写成 [\\w./-] 会把
    「A / B 两条管线」这类正文整段吞掉。
    """
    return RE_PATH_FRAG.sub(" ", text or "")


def match_project(text, idx):
    t = strip_path_frags(text)
    tl = t.lower()
    for kw, p in idx:
        if kw.lower() in tl or kw in t:
            return p, kw
    return None, ""


def dir_project_name(proj_root):
    """cwd 目录名 → 已存在项目名（仅用于**匹配**，不再用于新建）。"""
    return os.path.basename((proj_root or "").rstrip("/"))


# ================================================================ 主流程
def collect(dry_run=False, sample=0):
    ensure_config()
    t0 = time.time()
    wb = load_wb()
    # 项目台账：优先用配置里的（配置即事实源）；同时保留上次运行写入的
    # archived / created 等运行期字段，避免刷新页面把「已归档」洗掉。
    cfg_projects = _cfg("projects") or []
    if cfg_projects:
        prev = {p.get("id"): p for p in wb.get("projects", [])}
        projects = []
        for p in cfg_projects:
            m = dict(p)
            for k in ("archived", "archivedAt", "created", "updated"):
                if k in (prev.get(p.get("id")) or {}):
                    m[k] = prev[p.get("id")][k]
            projects.append(m)
    else:
        projects = wb.get("projects", [])
    old_sessions = wb.get("sessions", []) or []
    old_by_id = {s.get("id"): s for s in old_sessions if s.get("id")}
    # 抗标题漂移的二级索引：源文本被改写后 id 会变，
    # 只按 id 找旧记录会让「已确认」的条目重新退回候选区。
    old_by_key = {}
    for _s in old_sessions:
        if not _s.get("id"):
            continue
        old_by_key.setdefault(
            (_s.get("logFile") or "", norm_title(_s.get("title"))), _s)
    legacy_dismissed = set(wb.get("dismissed") or [])   # 旧字段（兼容保留）
    tstate = load_todo_state()                          # 人工判定档案（兜底）
    state_hits, state_fuzzy, migrated = 0, 0, 0
    migrated_from = {}                                  # 旧 id → 新 id（供补齐逻辑避让）
    # 是否已有历史数据：候选制据此决定「首次全量」还是「增量提名」
    had_v4 = any(str(s.get("id", "")).startswith("T_") for s in old_sessions)
    # 人工指定归属档案（页面调整分组 → 导出 → --apply-checked 写入）
    assigned_map = tstate.get("assigned") or {}
    assigned_hits = 0

    pairs = find_log_files()
    log(f"[1/4] 记忆文件：{len(pairs)} 个")

    proj_idx = build_project_index(projects)      # 提前构建：上下文打分需要它
    raw = []
    for path, proj_root in pairs:
        got = parse_log_todos(path, proj_root, proj_idx)
        if got:
            log(f"      · {os.path.basename(path):18s} → {len(got):2d} 条待办")
        raw.extend(got)
    log(f"[2/4] 原始待办条目：{len(raw)}")

    # ---- 去重（同文件 + 规范化标题）
    dedup = {}
    for it in raw:
        key = (it["logFile"], re.sub(r"\s+", "", it["title"]).lower())
        if key in dedup:
            prev = dedup[key]
            if it.get("done") is False and prev.get("done") is True:
                prev["done"] = False                  # 任一来源说未完成 → 未完成
                prev["signal"] = it.get("signal") or prev.get("signal")
            continue
        dedup[key] = it
    todos = list(dedup.values())
    log(f"[3/4] 去重后：{len(todos)}（合并重复 {len(raw) - len(todos)} 条）")

    # ---- 项目关联 + 生成 session
    sessions = []
    unmatched = 0
    # 项目锚最大有效距离：超过则认为锚已失效（换到别的项目段落了）
    ANCHOR_MAX_DIST = 400

    for it in todos:
        pid, kwsrc = "", ""
        # ----------------  项目锚定：多信号打分，谁高分听谁的 ----------------
        # 为什么不能只看标题：memory 的待办正文多是「W2 薄客户端 §5.2 错误表仍写 401」
        # 这类片段，项目名在**章节标题**里，不在条目里。
        dname = dir_project_name(it["projRoot"])
        anchor_fresh = (it.get("anchorDist") or 99999) <= ANCHOR_MAX_DIST
        sig = [
            (6, match_project(it["title"], proj_idx)[0], "标题"),
            (5, match_project(it.get("context") or "", proj_idx)[0], "上下文"),
            (5 if anchor_fresh else 1,
             match_project(it.get("anchor") or "", proj_idx)[0], "项目锚"),
            (3, match_project(it.get("docAnchor") or "", proj_idx)[0], "文件主题"),
        ]
        # 目录兜底：容器目录（只是「放项目的文件夹」）不是项目，跳过
        if dname not in _cfg("container_dirs"):
            sig.append((2, match_project(_cfg("dir_project_map").get(dname, dname), proj_idx)[0], "目录"))
        best = max(sig, key=lambda x: x[0] if x[1] else -1)
        if best[1]:
            pid, kwsrc = best[1]["id"], best[2]

        sid = "T_" + hashlib.md5(f"{it['logFile']}::{it['title']}".encode("utf-8")).hexdigest()[:11]
        if sid in legacy_dismissed:
            continue                              # 人工已忽略（旧字段）
        state_kind, matched = resolve_state(sid, it["title"], it["logBase"], tstate)
        if state_kind == "dismissed":
            # 自愈：模糊命中（源文本被改写导致 id 漂移）→ 把黑名单记录迁到新 id，
            # 下次起精确命中，不再每次归集都依赖模糊通道
            if matched and matched != sid:
                rec = dict(tstate["dismissed"].pop(matched, {}))
                rec.update({"title": it["title"], "logBase": it["logBase"],
                            "at": time.strftime("%Y-%m-%d %H:%M"), "by": "migrated"})
                tstate["dismissed"][sid] = rec
                migrated_from[matched] = sid
                migrated += 1
            continue                              # 人工已忽略（状态档案）
        if state_kind == "done":
            state_hits += 1
            if matched != sid:
                state_fuzzy += 1
        # 旧记录查找：精确 id → 规范标题 → 同文件包含关系（都查不到才是真新条目）
        old = old_by_id.get(sid)
        if old is None:
            old = old_by_key.get((it["logFile"], norm_title(it["title"])))
        if old is None:
            old = find_old_by_overlap(it, old_sessions)
        old = old or {}

        # 人工指定归属：优先级高于上面全部自动打分。自动打分本质是猜（只能说
        # 「最像哪个项目」，说不出「不属于这里」），猜错时人给的答案必须在
        # **下一次归集之后依然生效** —— 所以读独立档案，而不是只改产物。
        assigned = assigned_map.get(sid) or {}
        if not assigned:
            assigned = find_assigned_by_overlap(it, assigned_map)
        if assigned:
            # projectId 为空串 = 人指定为「未分类」；有值 = 指定到该项目。
            # 只要该条在档案里出现过，就以人的指定为准，不回落到自动打分。
            pid, kwsrc = assigned.get("projectId") or "", "人工指定"
            assigned_hits += 1
        if not pid:
            unmatched += 1

        # 优先级：人工判定档案 > 产物里的人工状态 > 日志信号 > 默认
        if state_kind == "done":
            done, done_by = True, "user"
        elif old.get("doneBy") == "user":
            done, done_by = bool(old.get("done")), "user"
        elif it.get("signal"):
            done, done_by = bool(it["done"]), "auto"
        else:
            done, done_by = bool(it["done"]), "default"

        # 候选制分级：
        #   ① 归属已被人工指定过 → 转正（组都选过了，没必要再确认一遍）
        #   ② 显式标记（`**待办**：` / `- [ ]`）→ 转正。人主动写下的待办不是
        #      「机器新提名」，再要一遍确认属重复劳动；这里**不看**旧值，
        #      把此前已积压在候选区的显式条目一并释放。
        #   ③ 其余（机器从章节正文推断出来的）→ 沿用旧值；首次迁移全量信任；
        #      此后新出现的才进候选区。
        if assigned:
            pending = False
        elif it.get("src") in EXPLICIT_SRC:
            pending = False
        elif old:
            pending = bool(old.get("pending", False))
        elif not had_v4:
            pending = False
        else:
            pending = True

        # 自愈：标题微调导致 id 漂移 → 把人工判定迁移到新 id，避免下次再靠模糊匹配
        if matched and matched != sid:
            pool = tstate["done"] if state_kind == "done" else tstate["dismissed"]
            rec = dict(pool.pop(matched, {}))
            rec.update({"title": it["title"], "logBase": it["logBase"],
                        "at": time.strftime("%Y-%m-%d %H:%M"), "by": "migrated"})
            pool[sid] = rec
            migrated_from[matched] = sid
            migrated += 1

        sessions.append({
            "id": sid,
            "title": it["title"],
            "kind": "record" if done else "todo",
            "done": done,
            "doneBy": done_by,
            "doneSource": (f"log:{it['logBase']}:{it['signal']}" if it.get("signal") else ""),
            "pending": pending,
            "source": it["src"],
            "origin": it.get("origin", ""),
            "context": it.get("context", ""),
            "matchVia": kwsrc,                     # 归属判定依据：标题/上下文/项目锚/文件主题/目录
            "anchor": it.get("anchor", ""),        # 项目锚（章节标题）
            "projectId": pid,
            "projectSource": kwsrc,
            "logFile": it["logFile"],
            "logBase": it["logBase"],
            "logDate": it["date"],
            "startedAt": f"{it['date']}T00:00:00.000Z",
            "firstSeen": old.get("firstSeen") or it["date"],
            "archived": bool(done),
            # 历史遗留：未完成且已超 _cfg("stale_days")，页面折叠展示，避免淹没当前待办
            "stale": (not done) and _age_days(it["date"]) > _cfg("stale_days"),
        })

    # ---- 排序：未完成在前（新→旧），已完成在后
    sessions.sort(key=lambda s: (1 if s["done"] else 0,
                                 "" if s["done"] else _rev(s["logDate"]),
                                 _rev(s["logDate"])))
    n_pend = sum(1 for s in sessions if not s["done"] and s["pending"])
    log(f"[4/4] 生成待办 {len(sessions)} 条（未完成 "
        f"{sum(1 for s in sessions if not s['done'])} / 已完成 "
        f"{sum(1 for s in sessions if s['done'])}）｜未分类 {unmatched} 条"
        f"｜待确认候选 {n_pend} 条")
    if state_hits or migrated:
        log(f"      人工判定档案命中 {state_hits} 条"
            f"（其中模糊匹配 {state_fuzzy} 条、id 自愈迁移 {migrated} 条）")
    if assigned_hits:
        log(f"      人工指定归属 {assigned_hits} 条（页面调整过分组，优先于自动判定）")
    # 审计：两个载体的计数应互相印证（档案为空但 workbench 有大量人工标记 = 可疑）
    wb_user = sum(1 for s in old_sessions if s.get("doneBy") == "user")
    st_n = len(tstate.get("done") or {})
    if wb_user or st_n:
        log(f"      人工判定存量：workbench {wb_user} 条 / 档案 {st_n} 条"
            + ("   ⚠ 两者差异较大，建议核对" if abs(wb_user - st_n) > max(3, st_n * 0.5) else ""))

    if sample:
        print_sample(sessions, sample)

    if dry_run:
        log(f"[dry-run] 未写盘。耗时 {time.time() - t0:.2f}s")
        return sessions, wb

    # 项目按待办数降序重排（页面 chips / 分组的展示顺序随之稳定）
    pcnt = {}
    for s in sessions:
        pid = s.get("projectId")
        if pid:
            pcnt[pid] = pcnt.get(pid, 0) + 1
    projects.sort(key=lambda x: (-pcnt.get(x.get("id"), 0), x.get("name") or ""))

    # 补齐：workbench 里的人工标记若不在档案里（旧版 serve.py 勾选、历史遗留），
    # 一次性补进档案 —— 让「人工判定」真正与归集派生物解耦
    patched = 0
    revoked = 0
    for s_old in old_sessions:
        oid = s_old.get("id")
        if s_old.get("doneBy") != "user" or not oid:
            continue
        if oid in migrated_from:
            # 该条判定已随 id 迁移到新 id。这里若不跳过，会把刚迁移走的旧 id
            # 又补回档案（同一件事留两份），下次改写时判定在两条之间来回跳。
            continue
        if s_old.get("done") and oid not in tstate["done"]:
            tstate["done"][oid] = {
                "title": s_old.get("title") or "",
                "logBase": s_old.get("logBase") or "",
                "projectId": s_old.get("projectId") or "",
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "by": "sync",
            }
            patched += 1
        elif (not s_old.get("done")) and oid in tstate["done"]:
            # ⚠️ 必须同时看 done：只看 doneBy 会把「取消勾选」的动作当成标记，
            # 下一秒又把它补回档案 → 用户永远取消不掉（2026-09-11 自查发现）
            tstate["done"].pop(oid, None)
            revoked += 1
    if patched or revoked:
        log(f"      人工判定对齐档案：补齐 {patched} 条 / 撤销 {revoked} 条")

    if migrated or patched or revoked:
        save_todo_state(tstate)          # 仅在发生变化时写档案，避免无谓 IO
    wb["sessions"] = sessions
    wb["schema"] = _cfg("schema")
    wb.setdefault("tasks", [])
    wb["projects"] = projects
    save_wb(wb)
    log(f"✅ 已写入 todos.json：sessions {len(old_sessions)} → {len(sessions)} 条"
        f"｜项目 {len(projects)} 个｜耗时 {time.time() - t0:.2f}s")
    if not dry_run:
        auto_render_html()
    return sessions, wb


def _rev(d):
    """日期倒序辅助：把 YYYY-MM-DD 反转用于排序（越大越靠前）。"""
    return "".join(chr(255 - ord(c)) for c in str(d or ""))


def print_sample(sessions, n):
    print("\n" + "=" * 78)
    print(f"抽样 {min(n, len(sessions))} / {len(sessions)} 条（人工复核用）")
    print("=" * 78)
    for i, s in enumerate(sessions[:n], 1):
        flag = "✔" if s["done"] else "☐"
        pend = " [候选]" if s.get("pending") else ""
        print(f"{i:3d} {flag}{pend} {s['title'][:58]}")
        print(f"      id={s['id']}  proj={s['projectId'] or '未分类'}  src={s['source']}"
              f"  origin={s.get('origin') or '-'}  date={s['logDate']}")
        print(f"      {s['logBase']}")


def apply_checked(checked_path):
    """把 todos.html 导出的结果写回清单与判定档案。

    checked.json 形如：
        {"checked": ["T_xxx", ...], "unchecked": [...], "assign": {"T_xxx": "p_abc"}}

    · checked   → 完成 + 记入判定档案
    · unchecked → 未勾选且此前为人工完成 → 撤销（支持取消完成）
    · assign     → 调整归属：写进判定档案的 assigned 段，归集时优先于自动判定。
                   值为空串表示改回「未分类」。旧版导出的文件没有这个字段，
                   照常工作。
    """
    ensure_config()
    try:
        with open(checked_path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        log(f"❌ 读取结果文件失败：{e}")
        return 1

    on = set(payload.get("checked") or [])
    off = set(payload.get("unchecked") or [])
    assign = payload.get("assign") or {}
    if not on and not off and not assign:
        log("结果为空，无事可做")
        return 0

    wb = load_wb()
    sessions = wb.get("sessions") or []
    by_id = {s.get("id"): s for s in sessions}

    st = load_todo_state()
    done_n = undo_n = 0
    for tid in on:
        t = by_id.get(tid)
        if not t:
            continue
        if not t.get("done"):
            t["done"] = True
            t["archived"] = True
            t["pending"] = False
            t["kind"] = "record"
            t["doneBy"] = "user"
            done_n += 1
        st["done"][tid] = {
            "title": t.get("title") or "",
            "logBase": t.get("logBase") or "",
            "projectId": t.get("projectId") or "",
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "by": "page",
        }
    for tid in off:
        t = by_id.get(tid)
        if not t:
            continue
        # 只撤销「人工判定」留下的完成状态；日志信号判定的不动
        if t.get("done") and t.get("doneBy") == "user":
            t["done"] = False
            t["archived"] = False
            t["kind"] = "todo"
            t["doneBy"] = "default"
            st["done"].pop(tid, None)
            undo_n += 1

    # 归属调整：只接受配置里登记过的项目（空串 = 未分类），避免写进不存在的 id。
    # 结果落判定档案，下次归集优先采用；重复调整以最后一次为准。
    assign_n = 0
    if assign:
        known = {p.get("id") for p in (_cfg("projects") or [])}
        st.setdefault("assigned", {})
        for tid, pid in assign.items():
            t = by_id.get(tid)
            if not t:
                continue
            pid = (pid or "").strip()
            if pid and pid not in known:
                log(f"  [跳过] 未在配置里登记的项目 id：{pid}")
                continue
            t["projectId"] = pid
            t["projectSource"] = "人工指定"
            st["assigned"][tid] = {
                "projectId": pid,
                "title": t.get("title") or "",
                "logBase": t.get("logBase") or "",
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "by": "page",
            }
            assign_n += 1

    wb["sessions"] = sessions
    save_wb(wb)
    save_todo_state(st)
    log(f"✅ 已写回：标记完成 {done_n} 条 / 撤销完成 {undo_n} 条"
        + (f" / 调整归属 {assign_n} 条" if assign_n else ""))
    return 0


def auto_render_html():
    """归集后自动生成 HTML 清单（render_todos.py 与 harvest.py 同目录）。"""
    if not _cfg("render_html"):
        return None
    script = os.path.join(HERE, "render_todos.py")
    if not os.path.isfile(script):
        log("  [提示] 未找到 render_todos.py，跳过生成 HTML")
        return None
    data_path = _cfg("out")
    if not os.path.isfile(data_path):
        return None
    out = _cfg("html_out")
    out = out if os.path.isabs(out) else os.path.join(os.path.dirname(data_path), out)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("render_todos", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.render(data_path, out, _cfg("state"), "待办清单")
        return out
    except Exception as e:
        log(f"  [提示] 生成 HTML 失败：{e}")
        return None


def main():
    p = argparse.ArgumentParser(
        description="从 agent 记忆文件打捞待办清单",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例
  harvest.py --init                     生成 harvest.config.json 模板
  harvest.py --dry-run                  先看命中了什么（不写盘）
  harvest.py --dry-run --sample 60      附带抽样明细，人工核准确率
  harvest.py                            正式写盘 todos.json
""")
    p.add_argument("--config", help="配置文件路径（默认 ./harvest.config.json）")
    p.add_argument("--init", action="store_true", help="生成配置模板后退出")
    p.add_argument("--dry-run", action="store_true", help="预览不写盘")
    p.add_argument("--sample", type=int, default=0, help="抽样打印 N 条")
    p.add_argument("--force", action="store_true", help="兼容保留（恒为全量扫描）")
    p.add_argument("--apply-checked", metavar="FILE",
                   help="把 todos.html 导出的 checked.json 写回清单与判定档案")
    p.add_argument("--no-html", action="store_true", help="归集后不生成 HTML 清单")
    args = p.parse_args()

    if args.init:
        path = init_config(args.config)
        print(f"已生成配置模板：{path}")
        print("下一步：填好 roots / projects / container_dirs，然后 harvest.py --dry-run")
        return 0

    load_config(args.config)
    if args.no_html:
        CONFIG["render_html"] = False

    if args.apply_checked:
        rc = apply_checked(args.apply_checked)
        if rc == 0:
            auto_render_html()
        return rc

    try:
        collect(dry_run=args.dry_run, sample=args.sample)
    except Exception as e:
        log(f"❌ 归集失败：{e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
