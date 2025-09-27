import socket
from antminer.constants import DEFAULT_PORT
from antminer.base import BaseClient
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from netutils import resolve_mac
class LocalMiners(object):
    TIMEOUT = 0.05
    MAX_PROBES = 256   # threads per discover() call

    def __init__(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        self.ip_address = sock.getsockname()[0]
        sock.close()
        self.network = '{}.'.format('.'.join(self.ip_address.split('.')[:3]))
        self._miner_index = 0
        self._miners = None

    def _is_up(self, addr):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.TIMEOUT)
        if not sock.connect_ex((addr, DEFAULT_PORT)):
            is_up = True
        else:
            is_up = False

        sock.close()
        return is_up
    
    def _probe(self, ip: str) -> BaseClient | None:
        try:
            with socket.create_connection((ip, DEFAULT_PORT), self.TIMEOUT):
                cli = BaseClient(ip)
                # Best-effort MAC lookup (same L2 only)
                try:
                    cli.mac_addr = resolve_mac(ip)  # dynamic attribute; or extend BaseClient
                except Exception:
                    cli.mac_addr = None
                return cli
        except OSError:
            return None
        
    def ori_discover(self):
        found = []
        for ip in range(1, 256):
            addr = '{network}{ip}'.format(network=self.network, ip=str(ip))
            if self._is_up(addr):
                print(f'scanning: {addr} - found')
                found.append(BaseClient(addr))

        return found
    
    def discover(self, subnet: str = "192.168.0.0/24") -> List[BaseClient]:
        """
        Scan the given CIDR (or x.x.x.* pattern) for miners that respond on
        TCP port 4028 (the cgminer/bmminer JSON‑RPC port).

        `subnet` may be:
            • CIDR –  '192.168.2.0/24'
            • Wildcard – '192.168.2.*'  (converted to /24 automatically)
        """
        if subnet.endswith(".*"):
            subnet = subnet.replace(".*", ".0/24")

        net = ipaddress.IPv4Network(subnet, strict=False)

        miners: list[BaseClient] = []
        with ThreadPoolExecutor(max_workers=self.MAX_PROBES) as pool:
            fut = {pool.submit(self._probe, str(ip)): ip for ip in net.hosts()}
            for f in as_completed(fut):
                if cli := f.result():
                    miners.append(cli)
        return miners

    def __iter__(self):
        return self

    def next(self):
        if self._miners is None:
            self._miners = self.discover()

        if self._miner_index >= len(self._miners):
            raise StopIteration
        else:
            self._miner_index += 1
            return self._miners[(self._miner_index - 1)]

    def seek(self, offset):
        self._miner_index = offset

    def flush(self):
        self._miner_index = 0
        self._miners = None
