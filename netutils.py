# netutils.py
import platform, re, subprocess
from typing import Optional
from getmac import get_mac_address

def mac_via_arp_table(ip: str) -> Optional[str]:
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["arp", "-a", ip], text=True, stderr=subprocess.DEVNULL)
        else:
            out = subprocess.check_output(["arp", "-n", ip], text=True, stderr=subprocess.DEVNULL)
        m = re.search(r"((?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})", out)
        return m.group(1).lower() if m else None
    except Exception:
        return None

def mac_via_scapy(ip: str, timeout: float = 1.0) -> Optional[str]:
    try:
        # Requires: pip install scapy ; and root/admin or CAP_NET_RAW on Linux
        from scapy.all import ARP, Ether, srp  # type: ignore
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff")/ARP(pdst=ip)
        ans, _ = srp(pkt, timeout=timeout, verbose=False)
        for _, r in ans:
            return r[Ether].src.lower()
    except Exception:
        pass
    return None
def mac_via_getmac(ip: str) -> Optional[str]:
    try:
        mac = get_mac_address(ip=ip)
        return mac.lower() if mac else None
    except Exception:
        return None
    
def resolve_mac(ip: str) -> Optional[str]:
    # Prefer active ARP probe; fallback to ARP table
    return mac_via_getmac(ip) or mac_via_scapy(ip) or mac_via_arp_table(ip)
