import os
import subprocess
import sys

def kill_port(port):
    if os.name == 'nt':  # Windows
        try:
            # Find the process ID using the port
            output = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True).decode()
            for line in output.strip().split('\n'):
                if 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    print(f"Killing process {pid} on port {port}...")
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                    return True
        except subprocess.CalledProcessError:
            print(f"No process found on port {port}")
    else:
        print("This script is configured for Windows only.")
    return False

if __name__ == "__main__":
    kill_port(8080)
