"""One-off: produce the revised evidence-designer prompt (adds the 2026-11-18 no-code-name rule)."""
import sys

src = open(sys.argv[1], encoding="utf-8").read()
a = "已确认决定 D-001～D-015。"
b = "已确认决定 D-001～D-021（D-016～D-021 为 2026-11-18 确认的五个科目证据提取规则）。"
c = "10. 记录先后顺序不能当熟练度代理：当天后段的表现反而变差。"
d = c + """
11. **不用代称缩写，描述要完整**（用户 2026-11-18 规定，见 `proj/CLAUDE.md`）。
    - 不使用项目自造的代号，如 E1～E4、CP2、B、H、J、Q1、G2、S1-5、T-A、“方案c”。每次都写完整名称，如“减速航迹与航向证据”“减速度变化幅度”“中段杆位变化范围”“按推拉次数分档的合成方案”。
    - 决定编号 D-0xx 只能跟在完整描述之后作括注。
    - 档位写全称：期望／可接受／不可接受，不单写 D/A/U。
    - 外部缩写（FAA、EASA、ADS-33、ACS）在每份文档首次出现时写全称。
    - 程序标识符可以保留，但正文中第一次出现时说明含义。
    - 这条规则同样适用于交回负责人的汇报。"""
assert src.count(a) == 1 and src.count(c) == 1
out = src.replace(a, b).replace(c, d)
open(sys.argv[2], "w", encoding="utf-8").write(out)
print(len(out))
