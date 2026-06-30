import os
import hashlib
import json
from collections import defaultdict

def calculate_hash(file_path, block_size=65536):
    """计算文件的MD5哈希值"""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            buf = f.read(block_size)
            while buf:
                hasher.update(buf)
                buf = f.read(block_size)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

def find_duplicates(directory):
    """查找目录中的重复文件"""
    hash_to_files = defaultdict(list)
    
    for root, dirs, files in os.walk(directory):
        # 跳过一些常见的不需要检查的目录
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv']]
        
        for file in files:
            file_path = os.path.join(root, file)
            file_hash = calculate_hash(file_path)
            if file_hash:
                hash_to_files[file_hash].append(file_path)
    
    # 过滤出有多个文件的哈希值
    duplicates = {hash_val: files for hash_val, files in hash_to_files.items() if len(files) > 1}
    return duplicates

def main():
    directory = os.getcwd()
    print(f"Searching for duplicate files in: {directory}")
    
    duplicates = find_duplicates(directory)
    
    if duplicates:
        print(f"Found {len(duplicates)} sets of duplicate files:")
        
        # 保存结果到文件
        result = {
            "total_duplicate_sets": len(duplicates),
            "duplicates": {}
        }
        
        for i, (hash_val, files) in enumerate(duplicates.items(), 1):
            print(f"\nSet {i}:")
            print(f"Hash: {hash_val}")
            print(f"Files: {len(files)}")
            for file in files:
                print(f"  - {file}")
            
            result["duplicates"][hash_val] = files
        
        with open('duplicate_files.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\nResults saved to duplicate_files.json")
    else:
        print("No duplicate files found.")

if __name__ == "__main__":
    main()
