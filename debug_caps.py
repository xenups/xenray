
import os
import shutil
import subprocess
import sys

# Locate getcap
getcap = shutil.which("getcap")
if not getcap:
    possible_paths = ["/usr/sbin/getcap", "/sbin/getcap"]
    for p in possible_paths:
        if os.path.exists(p):
            getcap = p
            break

print(f"Using getcap: {getcap}")

# Binaries
bin_dir = os.path.abspath("bin/linux-x86_64")
singbox = os.path.join(bin_dir, "sing-box")
xray = os.path.join(bin_dir, "xray")

for binary in [singbox, xray]:
    print(f"Checking: {binary}")
    if os.path.exists(binary):
        cmd = [getcap, binary]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            print(f"Result ({res.returncode}): {res.stdout.strip()}")
            if "cap_net_admin" in res.stdout:
                print("HAS CAP_NET_ADMIN")
            else:
                print("MISSING CAP_NET_ADMIN")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Does not exist")
