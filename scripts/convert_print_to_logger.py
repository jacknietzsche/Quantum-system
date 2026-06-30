#!/usr/bin/env python3
"""
print → logger 批量转换工具

将 print 语句转换为 logging 模块的 logger 调用。
自动检测并添加 logger 初始化代码。

用法:
    python convert_print_to_logger.py <file_or_directory>
"""

import re
import os
import sys
from pathlib import Path


def add_logger_import(content):
    """添加 logger 初始化代码（如果不存在）"""
    if 'import logging' in content and 'logger = logging.getLogger' in content:
        return content, False  # 已存在

    # 查找 import 区段
    lines = content.split('\n')
    insert_idx = 0

    # 找到最后一个 import 行
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            insert_idx = i + 1

    # 插入 logger 初始化
    logger_code = [
        '',
        'import logging',
        'logger = logging.getLogger(__name__)'
    ]

    lines = lines[:insert_idx] + logger_code + lines[insert_idx:]
    return '\n'.join(lines), True


def convert_print_statement(line):
    """
    转换单行 print 语句

    支持:
    - print("literal")
    - print(variable)
    - print(f"f-string {var}")
    - print("format" % (vars))
    - print("a", "b", "c")
    """
    # 匹配 print( 到匹配的括号
    print_match = re.match(r'^(\s*)print\((.*)\)\s*$', line)
    if not print_match:
        return None

    indent = print_match.group(1)
    args_str = print_match.group(2)

    # 处理 print("...") 或 print('...')
    if (args_str.startswith('"') and args_str.endswith('"')) or \
       (args_str.startswith("'") and args_str.endswith("'")):
        # 去掉引号
        content = args_str[1:-1]

        # 检查是否有 % 格式化
        if '%' in content and '%' not in content.replace('%%', ''):
            # % 格式化: print("value: %d" % x)
            match = re.match(r'^([^%]*%[^%]*)\s*%\s*\((.*)\)$', content)
            if match:
                fmt = match.group(1)
                vars_part = match.group(2)
                # 简化处理
                return f'{indent}logger.info("{fmt}", {vars_part})'
            match = re.match(r'^([^%]*%[^%]*)\s*%\s*(.+)$', content)
            if match:
                fmt = match.group(1)
                var = match.group(2)
                return f'{indent}logger.info("{fmt}", {var})'
        else:
            # 简单字符串（可能包含 \n 或 = 装饰）
            if content.strip() in ['=' * 60, '-' * 60, '_' * 60]:
                return None  # 装饰线，跳过
            if content.strip().startswith('=') or content.strip().startswith('-'):
                # 可能是标题装饰
                clean = content.strip()
                return f'{indent}logger.info("{clean}")'
            if '\\n' in content:
                content = content.replace('\\n', '')
            if content.strip():
                return f'{indent}logger.info("{content.strip()}")'
            return None

    # 处理 print(f"...")
    if args_str.startswith('f"') or args_str.startswith("f'"):
        # 提取 f-string 内容
        if args_str.startswith('f"'):
            fstring_content = args_str[2:-1]  # 去掉 f" 和 "
        else:
            fstring_content = args_str[2:-1]  # 去掉 f' 和 '

        # 提取变量名和表达式
        # 简化：找所有 {xxx} 模式
        parts = re.split(r'(\{[^}]+\})', fstring_content)
        format_parts = []
        var_names = []

        for part in parts:
            if part.startswith('{') and part.endswith('}'):
                # 去掉 { 和 }
                expr = part[1:-1]
                format_parts.append('%s')
                var_names.append(expr)
            else:
                if part:
                    format_parts.append(part.replace('{', '{{').replace('}', '}}'))

        format_str = ''.join(format_parts)

        # 处理 %% 转义
        format_str = format_str.replace('%%', '%')

        if var_names:
            var_list = ', '.join(var_names)
            return f'{indent}logger.info("{format_str}", {var_list})'
        else:
            return f'{indent}logger.info("{fstring_content}")'

    # 处理 print(variable)
    if ',' not in args_str:
        return f'{indent}logger.info("%s", {args_str})'

    # 处理 print("a", "b", variable) 或 print(a, b, c)
    return f'{indent}logger.info("%s", {args_str})'


def convert_file(filepath, dry_run=False):
    """转换单个文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    changes = 0

    for line in lines:
        converted = convert_print_statement(line)
        if converted:
            new_lines.append(converted)
            changes += 1
        else:
            new_lines.append(line)

    new_content = '\n'.join(new_lines)

    # 添加 logger 导入（如果需要）
    if changes > 0:
        new_content, added = add_logger_import(new_content)
        if added:
            changes += 1

    if dry_run:
        return changes, new_content

    if changes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return changes, None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='print → logger 转换工具')
    parser.add_argument('path', help='文件或目录路径')
    parser.add_argument('--dry-run', '-n', action='store_true', help='仅显示不写入')
    parser.add_argument('--exclude', '-e', default='__pycache__,.git', help='排除的目录')
    args = parser.parse_args()

    path = Path(args.path)
    exclude_patterns = args.exclude.split(',')

    total_changes = 0

    if path.is_file() and path.suffix == '.py':
        changes, _ = convert_file(path, dry_run=args.dry_run)
        logger.info("%s: %s 处转换", path, changes)
        total_changes += changes
    elif path.is_dir():
        for py_file in path.rglob('*.py'):
            # 跳过排除的目录
            if any(excl in str(py_file) for excl in exclude_patterns):
                continue
            changes, _ = convert_file(py_file, dry_run=args.dry_run)
            if changes > 0:
                logger.info("%s: %s 处转换", py_file, changes)
                total_changes += changes

    logger.info("\n总计: %s 处转换", total_changes)


if __name__ == '__main__':
    main()
