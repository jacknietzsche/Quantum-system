import os


# 日志文件路径
log_file = r"c:\Users\21471\WorkBuddy\quant system\logs\backtest_comprehensive.log"

# 检查文件是否存在
if not os.path.exists(log_file):
    print("日志文件不存在: %s", log_file)
    exit(1)

# 获取文件大小
file_size = os.path.getsize(log_file)
print("日志文件大小: %.2f MB", file_size / 1024 / 1024)
# 读取文件末尾
with open(log_file, 'rb') as f:
    # 移动到文件末尾，读取最后100000字节
    f.seek(max(0, file_size - 100000))
    content = f.read().decode('utf-8', errors='ignore')

# 打印最后100行
lines = content.split('\n')
last_100_lines = lines[-100:]
for line in last_100_lines:
    print("%s", line)
