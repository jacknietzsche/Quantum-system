#!/usr/bin/env python3
"""
批量转换logger f-string为%s占位符格式
用法: python convert_logger_fstring.py [--dry-run] [--path <path>]

保守策略：
- 只处理简单变量引用 {var}
- 不处理复杂表达式、字典访问、方法调用
- 保留原f-string如果无法安全转换
"""

import os
import re
import argparse

import logging
logger = logging.getLogger(__name__)


def extract_variables(content):
    """
    从f-string内容中提取变量列表
    返回 (新内容, 变量列表)
    """
    result_parts = []
    variables = []
    pos = 0

    for match in re.finditer(r'\{([^}]+)\}', content):
        # 原始文本
        result_parts.append(content[pos:match.start()])

        expr = match.group(1).strip()

        # 只处理简单变量名 (字母、数字、下划线)
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', expr):
            result_parts.append('%s')
            variables.append(expr)
        else:
            # 复杂表达式，保持原样
            result_parts.append(match.group(0))

        pos = match.end()

    result_parts.append(content[pos:])
    return ''.join(result_parts), variables


def convert_fstring_to_percent(line):
    """
    将 logger.info(f"...") 转换为 logger.info("...", var1, var2, ...)
    """
    # 匹配 logger.<level>(f"...") 或 logger.<level>(f'...')
    pattern = r'(logger\.\w+)\(f(["\'])(.*?)\2\)'

    def replacer(m):
        logger_call = m.group(1)
        quote = m.group(2)
        content = m.group(3)

        new_content, variables = extract_variables(content)

        if not variables:
            # 没有变量，保持f-string原样
            return f'{logger_call}(f"{content}")'

        # 构建新的调用
        var_str = ', '.join(variables)
        return f'{logger_call}("{new_content}", {var_str})'

    return re.sub(pattern, replacer, line)


def process_file(filepath, dry_run=True):
    """处理单个文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        logger.info("  Error reading %s: %s", filepath, e)
        return 0

    modified_lines = []
    changes = 0

    for i, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith('#'):
            modified_lines.append(line)
            continue

        # 检查是否有logger f-string
        if 'logger.' in line and ('f"' in line or "f'" in line):
            new_line = convert_fstring_to_percent(line)
            if new_line != line:
                changes += 1
                logger.info("  %s:%s", filepath, i)
                logger.info("    原: %s", line.rstrip())
                logger.info("    新: %s", new_line.rstrip())
                line = new_line

        modified_lines.append(line)

    if not dry_run and changes > 0:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)
        except Exception as e:
            logger.info("  Error writing %s: %s", filepath, e)
            return 0

    return changes


def main():
    parser = argparse.ArgumentParser(description='Convert logger f-strings to % placeholder')
    parser.add_argument('--path', default='core', help='Path to process')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no changes)')
    args = parser.parse_args()

    dry_run = args.dry_run
    path = args.path

    if dry_run:
        logger.info("=== DRY RUN MODE ===")
        logger.info("使用 --dry-run 不会实际修改文件")
        logger.info("%s", )

    total_changes = 0
    files_changed = 0

    for root, dirs, files in os.walk(path):
        # 跳过特定目录
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.workbuddy', 'venv', 'env']]

        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                try:
                    changes = process_file(filepath, dry_run=dry_run)
                    if changes > 0:
                        total_changes += changes
                        files_changed += 1
                except Exception as e:
                    logger.info("Error processing %s: %s", filepath, e)

    logger.info("%s", )
    if dry_run:
        logger.info("=== DRY RUN: Would make %s changes in %s files ===", total_changes, files_changed)
    else:
        logger.info("=== Made %s changes in %s files ===", total_changes, files_changed)


if __name__ == '__main__':
    main()
