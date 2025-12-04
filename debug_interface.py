import psutil
import socket

print("Diagnostic: Checking Interface Selection Logic")

stats = psutil.net_if_stats()
addrs = psutil.net_if_addrs()

print(f"Found {len(stats)} interfaces")

selected_interface = None

for iface, if_stats in stats.items():
    print(f"\nInterface: {iface}")
    print(f"  Status: {'UP' if if_stats.isup else 'DOWN'}")
    
    if iface in addrs:
        for addr in addrs[iface]:
            print(f"  Address: {addr.address} ({addr.family})")
            
    if if_stats.isup and iface in addrs:
        has_ipv4 = False
        for addr in addrs[iface]:
            if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                has_ipv4 = True
                break
        
        if has_ipv4:
            print(f"  [CANDIDATE] Has IPv4 and is UP")
            if selected_interface is None:
                selected_interface = iface
                print(f"  [SELECTED] This would be chosen")
            else:
                print(f"  [SKIPPED] Already selected {selected_interface}")

print(f"\nFinal Selection: {selected_interface}")
