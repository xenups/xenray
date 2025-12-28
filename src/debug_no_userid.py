import ctypes
import subprocess
import sys


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def debug_no_userid():
    print(f"Is Admin: {is_admin()}")

    exe_path = r"C:\Windows\System32\cmd.exe"
    cwd = r"C:\Windows\System32"

    # EXACTLY the same structure as task_scheduler.py (no UserId)
    ps_script = f"""
    $ErrorActionPreference = 'Stop'
    try {{
        $Action = New-ScheduledTaskAction -Execute '{exe_path}' -WorkingDirectory '{cwd}'
        $Trigger = New-ScheduledTaskTrigger -AtLogon
        $Principal = New-ScheduledTaskPrincipal -LogonType Interactive -RunLevel Highest
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        Register-ScheduledTask -TaskName 'XenRay_Debug_NoUser' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
        Write-Host "Success!"
    }} catch {{
        Write-Error $_
    }}
    """

    print("Running PowerShell...")
    result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return Code:", result.returncode)

    if result.returncode == 0:
        subprocess.run(
            ["powershell", "-Command", "Unregister-ScheduledTask -TaskName 'XenRay_Debug_NoUser' -Confirm:$false"],
            capture_output=True,
        )


if __name__ == "__main__":
    debug_no_userid()
