import subprocess

def get_default_interface():
    try:
        cmd = [
            "powershell", 
            "-Command", 
            "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty InterfaceAlias"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"Interface: '{result.stdout.strip()}'")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_default_interface()
