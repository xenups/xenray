
import ctypes
import subprocess
import sys
import os

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def diagnose():
    admin = is_admin()
    print(f"Is Admin: {admin}")
    
    print("Getting User Info via PowerShell...")
    subprocess.run(["powershell", "-Command", "whoami; [System.Security.Principal.WindowsIdentity]::GetCurrent().Name"], check=False)

    if not admin:
        print("WARNING: Script not running as Admin. Task creation WILL fail.")
        return

    print("\nAttempt 1: Register Task WITHOUT explicit UserId...")
    ps_simple = """
    $Action = New-ScheduledTaskAction -Execute 'cmd.exe'
    $Principal = New-ScheduledTaskPrincipal -RunLevel Highest
    Register-ScheduledTask -TaskName 'Test_Simple_Admin' -Action $Action -Principal $Principal -Force
    """
    res1 = subprocess.run(["powershell", "-Command", ps_simple], capture_output=True, text=True)
    print("Return Code:", res1.returncode)
    print("STDERR:", res1.stderr)

    print("\nAttempt 2: Register Task WITH WindowsIdentity UserId...")
    ps_id = """
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Action = New-ScheduledTaskAction -Execute 'cmd.exe'
    $Principal = New-ScheduledTaskPrincipal -UserId $id -RunLevel Highest
    Register-ScheduledTask -TaskName 'Test_Explicit_Admin' -Action $Action -Principal $Principal -Force
    """
    res2 = subprocess.run(["powershell", "-Command", ps_id], capture_output=True, text=True)
    print("Return Code:", res2.returncode)
    print("STDERR:", res2.stderr)

    # Cleanup
    subprocess.run(["powershell", "-Command", "Unregister-ScheduledTask -TaskName 'Test_Simple_Admin' -Confirm:$false"], capture_output=True)
    subprocess.run(["powershell", "-Command", "Unregister-ScheduledTask -TaskName 'Test_Explicit_Admin' -Confirm:$false"], capture_output=True)

if __name__ == "__main__":
    diagnose()
