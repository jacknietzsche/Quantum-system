import os

def find_empty_folders(directory):
    """查找目录中的空文件夹"""
    empty_folders = []
    
    for root, dirs, files in os.walk(directory):
        # 跳过一些常见的目录
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv']]
        
        # 检查当前目录是否为空
        if not dirs and not files:
            empty_folders.append(root)
    
    return empty_folders

def main():
    directory = os.getcwd()
    print(f"Searching for empty folders in: {directory}")
    
    empty_folders = find_empty_folders(directory)
    
    if empty_folders:
        print(f"Found {len(empty_folders)} empty folders:")
        for folder in empty_folders:
            print(f"  - {folder}")
    else:
        print("No empty folders found.")

if __name__ == "__main__":
    main()
