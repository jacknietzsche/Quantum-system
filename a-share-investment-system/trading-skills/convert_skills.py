#!/usr/bin/env python3
"""Convert trading skill markdown files to proper OMC skill format."""

import os

SKILL_MAP = [
    {
        "name": "livermore-advisor",
        "desc": "Jesse Livermore investment advisor skill — 利弗莫尔投资顾问. Active trend trading based on key points, pyramid building, and disciplined execution.",
        "src": "livermore-trading-skill.md",
    },
    {
        "name": "t-plus-zero",
        "desc": "T+0 day trading strategy for A-shares — 股票T+0操作策略. Intraday high-sell-low-buy spread trading with base position management.",
        "src": "T+0操作策略_决策技能.md",
    },
    {
        "name": "bukui-investment",
        "desc": "Don't Lose: professional investor survival philosophy — 不亏：职业投资人的股市生存之道. Systematic 'three-knows' (know bottom, top, time) and risk-first framework.",
        "src": "不亏_决策技能.md",
    },
    {
        "name": "chaojia-33",
        "desc": "Speculator 33 articles — 炒家33篇. Hot money style: tracking leaders, momentum trading, and sector rotation in A-shares.",
        "src": "炒家33篇_决策技能.md",
    },
    {
        "name": "dengfeng-road",
        "desc": "Path to the peak — 登峰之路. Qingmu's moving average system: trend identification, three-market-state framework, and disciplined trading.",
        "src": "登峰之路_决策技能.md",
    },
    {
        "name": "stock-master-technique",
        "desc": "Stock master trading technique — 股票大作手操盘术. Livermore's key point theory: entry at pivotal thresholds, pyramid pyramiding, and danger signal recognition.",
        "src": "股票大作手操盘术_决策技能.md",
    },
    {
        "name": "stock-master-memoir",
        "desc": "Stock master memoir — 股票大作手回忆录. Livermore's life lessons: trend following, patience for big moves, tape reading, and avoiding common pitfalls.",
        "src": "股票大作手回忆录_决策技能.md",
    },
    {
        "name": "stock-trading-patterns",
        "desc": "Stock trading patterns — 股票买卖定式. Short-term technical analysis: K-line formations, moving averages, MACD/KDJ/RSI/Bollinger, and主力 tracking.",
        "src": "股票买卖定式_决策技能.md",
    },
    {
        "name": "turtle-trading",
        "desc": "Turtle trading rules — 海龟交易法则. Complete mechanical trend-following system: Donchian channels, ATR position sizing, pyramiding, and systematic execution.",
        "src": "海龟交易法则_决策技能.md",
    },
    {
        "name": "livermore-wisdom",
        "desc": "Practicing Livermore trading wisdom — 践行利弗莫尔交易智慧. Modern application of Livermore principles: trend tracking, key point breakout, and risk management.",
        "src": "践行利弗莫尔交易智慧_决策技能.md",
    },
    {
        "name": "li-daxiao-strategy",
        "desc": "Li Daxiao investment strategy — 李大霄投资战略. Diamond bottom, baby bottom, earth top framework: value investing with surplus funds and long-term perspective.",
        "src": "李大霄投资战略_决策技能.md",
    },
    {
        "name": "candlestick-techniques",
        "desc": "Japanese candlestick chart techniques — 日本蜡烛图技术新解. Advanced candlestick patterns: hammer/doji/engulfing, divergence index, three-gap and three-line break charts.",
        "src": "日本蜡烛图技术新解_决策技能.md",
    },
    {
        "name": "random-walk-fool",
        "desc": "Random Walk Fool — 随机漫步的傻瓜. Taleb's antifragile investing: barbell strategy, black swan protection, survivorship bias detection, and asymmetric bets.",
        "src": "随机漫步的傻瓜_决策技能.md",
    },
    {
        "name": "stock-winner",
        "desc": "Stock market winner — 要做股市赢家. Yang Million-style: watch the index to trade stocks, cycle timing, bottom-fishing and top-escaping strategies.",
        "src": "要做股市赢家_决策技能.md",
    },
    {
        "name": "speculation-principles",
        "desc": "Professional speculation principles — 专业投机原理. Sperandeo's 1-2-3 trend reversal法则, 2B fakeout rule, market psychology, and macro-driven投机体系.",
        "src": "投机原理_决策技能.md",
        "src_actual": "专业投机原理_决策技能.md",
    },
]

DOWNLOADS = r"C:\Users\21471\Downloads"
TARGET = r"C:\Users\21471\trading-skills"
SKILLS_DIR = os.path.expanduser(r"~\.claude\skills")

os.makedirs(TARGET, exist_ok=True)

for skill in SKILL_MAP:
    name = skill["name"]
    desc = skill["desc"]
    src_file = skill.get("src_actual", skill["src"])
    src_path = os.path.join(DOWNLOADS, src_file)

    if not os.path.exists(src_path):
        print(f"[SKIP] {src_file} not found")
        continue

    with open(src_path, encoding="utf-8") as f:
        content = f.read()

    # Build frontmatter
    frontmatter = f"""---
name: {name}
description: "{desc}"
---

"""
    skill_content = frontmatter + content

    # Write to trading-skills folder
    target_dir = os.path.join(TARGET, name)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "SKILL.md")
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(skill_content)
    print(f"[OK] Written: {target_path}")

    # Write to ~/.claude/skills/
    claude_dir = os.path.join(SKILLS_DIR, name)
    os.makedirs(claude_dir, exist_ok=True)
    claude_path = os.path.join(claude_dir, "SKILL.md")
    with open(claude_path, "w", encoding="utf-8") as f:
        f.write(skill_content)
    print(f"[OK] Installed: {claude_path}")

# Write README
readme = """# Trading Decision Skills (交易决策技能)

A collection of 15 professional trading and investment decision-making skills,
converted to OMC (oh-my-claudecode) format for AI-assisted trading analysis.

## Skills Overview

| Skill | Description | Source |
|-------|------------|--------|
| livermore-advisor | 利弗莫尔投资顾问 | Livermore's active trend trading system |
| t-plus-zero | T+0操作策略 | A-share intraday spread trading |
| bukui-investment | 不亏投资哲学 | "Three-knows" risk-first framework |
| chaojia-33 | 炒家33篇 | Hot money leader-tracking |
| dengfeng-road | 登峰之路 | Qingmu moving average system |
| stock-master-technique | 股票大作手操盘术 | Key point theory & pyramiding |
| stock-master-memoir | 股票大作手回忆录 | Livermore's life trading lessons |
| stock-trading-patterns | 股票买卖定式 | K-line & technical pattern trading |
| turtle-trading | 海龟交易法则 | Mechanical trend-following system |
| livermore-wisdom | 践行利弗莫尔智慧 | Modern Livermore application |
| li-daxiao-strategy | 李大霄投资战略 | Value investment + cycle timing |
| candlestick-techniques | 蜡烛图技术新解 | Advanced candlestick patterns |
| random-walk-fool | 随机漫步的傻瓜 | Antifragile/Taleb barbell strategy |
| stock-winner | 要做股市赢家 | Index-driven stock trading |
| speculation-principles | 专业投机原理 | 1-2-3 trend reversal + 2B rule |

## Usage

These skills are registered in `~/.claude/skills/` and can be invoked by AI
agents when analyzing stocks, formulating trading plans, or making investment decisions.

Each skill includes:
- Thinking chain examples with real case studies
- Step-by-step decision frameworks
- Stock selection criteria and entry/exit rules
- Risk control and position sizing rules
- Applicability boundaries and limitations
"""
readme_path = os.path.join(TARGET, "README.md")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(readme)
print(f"✓ README: {readme_path}")

print("\n✅ All 15 skills converted and installed successfully!")
