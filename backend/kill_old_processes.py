"""
停止占用8000端口的进程
"""
import subprocess
import sys

def kill_process(pid):
    try:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=True, capture_output=True)
        print(f"成功停止进程 {pid}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"停止进程 {pid} 失败: {e}")
        return False

# 查找占用8000端口的进程
result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
lines = result.stdout.split('\n')

pids = set()
for line in lines:
    if ':8000' in line and 'LISTENING' in line:
        parts = line.split()
        if len(parts) >= 5:
            pid = parts[-1]
            if pid.isdigit():
                pids.add(int(pid))

print(f"发现占用8000端口的进程: {pids}")

for pid in pids:
    kill_process(pid)

print("完成!")
