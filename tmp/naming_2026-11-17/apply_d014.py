"""D-014 (2026-11-17): rename the hierarchy in the discussion doc to 场景 → 科目 → 检查点.

- 科目一/科目二 (scene) -> 场景一/场景二 everywhere except §6.2 (Chinese driving-test subjects).
- item (maneuver unit) -> 科目 in §0–3 and §7–10; §4–6 keep the 2026-11-02 wording as a record.
- 项目 meaning the maneuver unit -> 科目 at the listed places; 本项目 (= this project) is untouched.
- Adds the D-014 decision, a progress note and English level names (candidates) in §10.
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
PATH = sys.argv[1]
L = open(PATH, encoding="utf-8").read().split("\n")
n0 = len(L)


def sec_of(i):  # 1-based line -> section number by the "## N." headings
    s = 0
    for j in range(i):
        m = re.match(r"## (\d+)\.", L[j])
        if m:
            s = int(m.group(1))
    return s


SEC = [sec_of(i) for i in range(1, n0 + 1)]
DRIVING = range(316, 330)  # §6.2 lines, 1-based


def rep(lineno, old, new, count=1):
    i = lineno - 1
    assert L[i].count(old) >= count, (lineno, old, L[i][:120])
    L[i] = L[i].replace(old, new)


# --- explicit wording changes (line numbers refer to the file before this script) ---------------
rep(8, "D-011：科目、项目与检查方法统一改用英文名称", "D-011：场景、科目与检查方法统一改用英文名称")
rep(10, "第7节的五类飞行考核项目", "第7节的五类飞行科目")
rep(14, "当前项目清单以D-002", "当前科目清单以D-002")
rep(16, "### 0.1 已确认的项目与范围", "### 0.1 已确认的科目与范围")
rep(18, "| 科目 | 当前item |", "| 场景 | 科目 |")
for ln in (20, 22, 23, 24):
    rep(ln, "项目已确认", "科目已确认")
rep(49, "**其他项目：**", "**其他科目：**")
rep(70, "末端调整属于同一项目的完整评估范围", "末端调整属于同一科目的完整评估范围")
rep(78, "科目、项目与检查方法统一使用英文名称", "场景、科目与检查方法统一使用英文名称")
rep(233, "本科目排除Vertical", "本场景排除Vertical")
rep(404, "## 7. 已确认的项目结构", "## 7. 已确认的科目结构")
rep(406, "五类飞行考核项目于2026-11-04确认", "五类飞行科目于2026-11-04确认")
rep(410, "采用：**训练科目／场景 → 具体考核项目（item）→ 检查点**。",
    "采用：**训练场景 → 科目 → 检查点**（层级用语按D-014）。")
rep(412, "- 科目：一次复合训练，如加速减速，或斜飞到点与上下点悬停。",
    "- 场景：一次复合训练任务，如加速减速，或斜飞到点与上下点悬停。")
rep(413, "- item：有明确动作目标、完成状态和评价依据的飞行机动。",
    "- 科目：有明确动作目标、完成状态和评价依据的飞行机动，英文用Mission Task Element。")
rep(415, "项目与phase可以一对一", "科目与phase可以一对一")
rep(416, "跨项目综合概率", "跨科目综合概率")
rep(426, "项目可沿用动作名称", "科目可沿用动作名称")
rep(433, "本版核心飞行项目建议2类", "本版核心飞行科目建议2类")
rep(444, "不额外增加定点悬停保持项目", "不额外增加定点悬停保持科目")
rep(448, "本版核心飞行项目建议3类。同一类项目可以有多次动作实例", "本版核心飞行科目建议3类。同一类科目可以有多次动作实例")
rep(473, "放入各项目的检查点", "放入各科目的检查点")
rep(483, "跨项目总分", "跨科目总分")
rep(501, "五类项目已确认", "五类科目已确认")
rep(503, "## 8. 五类项目检查方法草案", "## 8. 五类科目检查方法草案")
rep(505, "项目清单按D-002", "科目清单按D-002")
rep(692, "再汇总项目", "再汇总科目")
rep(713, "项目D/A/U", "科目D/A/U")
rep(713, "重复项目按预先确定的必做实例汇总", "重复科目按预先确定的必做实例汇总")
rep(798, "按D-011，科目、项目与检查方法统一使用英文名称", "按D-011，场景、科目与检查方法统一使用英文名称")
rep(800, "### 10.1 科目与项目", "### 10.1 场景与科目")
rep(821, "### 10.3 其他项目的检查点草案", "### 10.3 其他科目的检查点草案")
rep(823, "| 项目 | 候选英文名 |", "| 科目 | 候选英文名 |")

# --- global renames ---------------------------------------------------------------------------------
for i in range(n0):
    ln = i + 1
    if ln not in DRIVING:
        L[i] = L[i].replace("科目一", "场景一").replace("科目二", "场景二")
    if SEC[i] in (0, 1, 2, 3, 7, 8, 9, 10):
        L[i] = re.sub(r"(?<![A-Za-z_])item(?![A-Za-z_])", "科目", L[i])

# --- additions (insert from the bottom up so earlier line numbers stay valid) ----------------------
LEVELS = ("- 层级：场景 Scenario（软件编号SCN-001、SCN-002）；科目 Mission Task Element（吕老师2026-10-03建议，"
          "备选 Flight Test Element）；检查点 Checkpoint（软件现用名）。场景一以ADS-33 §3.11.11同名任务命名，"
          "该任务在ADS-33中本身是一个MTE；本项目把它作为场景名，场景内再分两个科目。")
idx = next(i for i, s in enumerate(L) if s.startswith("- 评价方面：Maneuver Completion"))
L.insert(idx, LEVELS)

D014_BLOCK = """### D-014：层级用语改为“场景 → 科目 → 检查点”

确认日期：2026-11-17。适用范围：本文件、后续设计文档与汇报材料；软件、配置与输入模板在按新方案修改时同步。

**用户确认：** 吕老师所说的“科目”对应原item，即具体飞行机动，如“受控减速与定点停止”。原“科目一／科目二”改称“场景一／场景二”，与汇报PPT第3页的“场景一／场景二”一致。

| 层级 | 新用语 | 原用语 | 示例 |
|---|---|---|---|
| 场景 | 场景一、场景二 | 科目一、科目二；软件编号SCN-001、SCN-002 | 场景一：加速减速；场景二：悬停 |
| 科目 | 科目 | item、考核项目、飞行考核项目 | 直线飞行与速度变换；受控减速与定点停止；低速移位与到点悬停；定点悬停；垂直升降与悬停建立 |
| 检查点 | 检查点 | 检查点 | 最终停点精度；减速平顺性 |

#### 2.11 规则

1. 本文件第0～3节、第7～10节按新用语改写。第4～6节是2026-11-02的早期讨论与调研记录，保留当时的item用语，其中“科目一／科目二”已改为“场景一／场景二”；6.2节驾照的“科目二、科目三、科目四”为驾考原名，不改。
2. “本项目”指本研究项目，不受本决定影响。
3. 软件、配置与JSON中的 `item`、`item_id`、`items` 等程序标识暂不改动；软件按新方案修改时统一界面与报告文字。
4. 英文层级名称见第10.4节，随D-011一并确认。

依据：吕老师2026-10-03反馈（录音02:38–03:21）：“不要用Item……中文用科目……英文是Mission Task Element或者Flight Test Element”。汇报要求整理见[导师汇报要求](../../../../SUPERVISOR_REPORTING_REQUIREMENTS_CN.md)。
"""
idx = next(i for i, s in enumerate(L) if s.startswith("## 3. 后续待讨论内容"))
L[idx:idx] = D014_BLOCK.split("\n")

D014_LIST = ("- **D-014（2026-11-17）**　层级用语改为“场景 → 科目 → 检查点”。原“科目一／科目二”改称“场景一／场景二”，"
             "原item（具体飞行机动，如“受控减速与定点停止”）改称“科目”，英文用Mission Task Element。详见下方D-014小节。")
idx = next(i for i, s in enumerate(L) if s.startswith("- **D-013（2026-11-13）**"))
L.insert(idx + 1, D014_LIST)

PROGRESS = ("**2026-11-17 进度。D-014：层级用语改为“场景 → 科目 → 检查点”。原“科目一／科目二”改称“场景一／场景二”，"
            "原item改称“科目”（如“受控减速与定点停止”），依据吕老师2026-10-03反馈并与汇报PPT一致；"
            "第4～6节为早期讨论记录，保留当时的item用语。**")
L[7:7] = [PROGRESS, ""]  # before the 2026-11-13 progress paragraph (old line 8)

open(PATH, "w", encoding="utf-8", newline="\n").write("\n".join(L))
print("lines", n0, "->", len(L))
