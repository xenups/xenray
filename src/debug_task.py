
import subprocess
import sys
import os
import ctypes
from pathlib import Path

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def debug_task_creation():
    print(f"Is Admin: {is_admin()}")
    
    # Simulate the path of the distributed EXE
    exe_path = r"C:\Users\Xenups\Desktop\gorzer\pub\xenray\dist\XenRay.exe"
    cwd = r"C:\Users\Xenups\Desktop\gorzer\pub\xenray\dist"
    
    print(f"Target Exe: {exe_path}")
    print(f"Target CWD: {cwd}")

    # FIX: Use WindowsIdentity to get the correct DOMAIN\User format
    ps_script = f"""
    $ErrorActionPreference = 'Stop'
    try {{
        $currentId = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        $Action = New-ScheduledTaskAction -Execute '{exe_path}' -WorkingDirectory '{cwd}'
        $Trigger = New-ScheduledTaskTrigger -AtLogon
        $Principal = New-ScheduledTaskPrincipal -UserId $currentId.Name -LogonType Interactive -RunLevel Highest
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        Register-ScheduledTask -TaskName 'XenRayStartup_Debug' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
        Write-Host "Success!"
    }} catch {{
        Write-Error $_
    }}
    """
    
    print("Running PowerShell...")
    result = subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True,
        text=True
    )
    
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return Code:", result.returncode)

if __name__ == "__main__":
    debug_task_creation()
