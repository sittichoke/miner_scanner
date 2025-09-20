import socket
import json
import sys

from antminer.exceptions import (
    WarningResponse, ErrorResponse, FatalResponse, UnknownError,
    raise_exception
)
from antminer.constants import (
    STATUS_INFO, STATUS_SUCCESS, DEFAULT_PORT, MINER_CGMINER,
    MINER_BMMINER
)
from antminer.utils import parse_version_number


class Core(object):
    def __init__(self, host, port=DEFAULT_PORT):
        self.host = host
        self.port = int(port)
        self.conn = None

    def connect(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((self.host, self.port))

    def close(self):
        self.conn.close()
        self.conn = None

    def send_command(self, command):
        if self.conn is None:
            self.connect()

        cmd = command.split('|')
        if len(cmd) > 2 or len(cmd) == 0:
            raise ValueError("Commands must be one or two parts")

        payload = {
            'command': cmd[0]
        }

        if len(cmd) == 2:
            payload['parameter'] = cmd[1]

        # self.conn.send(json.dumps(payload))
        self.conn.sendall(json.dumps(payload).encode('utf-8'))
        payload = self.read_response()
        try:
            response = json.loads(payload)
        except ValueError:
            response = payload# Assume downstream code knows what to do.

        self.close()
        return response

    # def read_response(self):
    #     final_result = ""
    #     done = False
    #     buf = self.conn.recv(4096)
    #     while done is False:
    #         more = self.conn.recv(4096)
    #         if not more:
    #             done = True
    #         else:
    #             buf += more
    #     return buf.replace('\x00','')
    def read_response(self):
        # Optional: prevent hangs on misbehaving firmware
        try:
            self.conn.settimeout(5.0)
        except Exception:
            pass

        chunks = []
        while True:
            try:
                chunk = self.conn.recv(4096)
            except socket.timeout:
                # Timed out waiting for more data; use what we have
                break
            if not chunk:
                break
            chunks.append(chunk)

        raw = b"".join(chunks)
        raw = raw.replace(b"\x00", b"")  # some miners NUL-terminate JSON
        return raw.decode("utf-8", errors="ignore")

    def command(self, *args):
        """
        Send a raw command to the API.

        This is a lower level method that assumes the command is the first
        argument and that the rest of the arguments are parameters that should
        be comma separated. 

        The basic format of API commands is 'command|param1,param2,etc'. The meaning
        of parameters depends greatly on the command provided. This method will return
        odd results if poorly constructed commands are passed.
        """
        return self._send('{command}|{parameters}'.format(command=args[0],
            parameters=','.join(args[1:])))

    def _raise(self, response, message=None):
        raise_exception(response, message)

    def _send(self, command):
        response = self.send_command(command)
        try:
            success = (response['STATUS'][0]['STATUS'] in [STATUS_INFO, STATUS_SUCCESS])
        except:
            raise UnknownError(response)

        if not success:
            self._raise(response)

        return response


class BaseClient(Core):

    def stats(self):
        """
        Get stats for the miner.

        Unfortunately, the API doesn't return valid JSON for this API response, which
        requires us to do some light JSON correction before we load the response.
        """
        response = self.send_command('stats')
        # return json.loads(response.replace('"}{"', '"},{"'))
        return response

    def ip(self):
        return self.host

    def version(self):
        """
        Get basic hardware and software version information for a miner.

        This returns a number of important version numbers for the miner. Each of the
        version numbers is an instance of Version from the SemVer Python package.
        """
        fields = [
            ('Type', 'model', str),
            ('API', 'api', parse_version_number),
            # ('Miner', 'version', parse_version_number),
        ]

        resp = self.command('version')

        version = {}
        for from_name, to_name, formatter in fields:
            try:
                version[to_name] = formatter(str(resp['VERSION'][0][from_name]))
            except KeyError:
                pass
            except Exception as exc:
                print("extract version error,",exc)


        version['miner'] = {}
        if MINER_CGMINER in resp['VERSION'][0]:
            version['miner']['vendor'] = MINER_CGMINER
            version['miner']['version'] = parse_version_number(resp['VERSION'][0][MINER_CGMINER])
        elif MINER_BMMINER in resp['VERSION'][0]:
            version['miner']['vendor'] = MINER_BMMINER
            version['miner']['version'] = parse_version_number(resp['VERSION'][0][MINER_BMMINER])
        else:
            version['miner']['vendor'] = MINER_UNKNWON
            version['miner']['version'] = None

        return version

     # ──────────────────────────────────────────────────────────────────
    # New: get pools via the miner API and normalize fields
    # ──────────────────────────────────────────────────────────────────
    def pools(self) -> list[dict]:
        """
        Return a normalized list of pool dicts from the miner.

        Common keys per item:
            - url
            - workername
            - status        (Alive/Dead/Disabled)
            - priority      (int, if available)
            - stratum_active (bool, if available)
            - quota, accepted, rejected (ints, if available)
        """
        try:
            resp = self.command('pools')  # {'POOLS': [ ... ]}
        except Exception as exc:
            raise UnknownError(f"pools command failed: {exc}")

        pools_raw = resp.get('POOLS', []) if isinstance(resp, dict) else []
        out: list[dict] = []

        for p in pools_raw:
            # Different firmwares use different field names; be defensive.
            url = (p.get('URL') or p.get('Stratum URL') or p.get('Stratum') or
                   p.get('StratumURL'))
            user = (p.get('User') or p.get('Worker') or p.get('UserName') or
                    p.get('Username'))
            status = p.get('Status') or p.get('Stratum Status') or p.get('StratumActive')
            prio = p.get('Priority') or p.get('PRIORITY')

            # Optional metrics
            quota = p.get('Quota')
            accepted = p.get('Accepted')
            rejected = p.get('Rejected')

            # Some firmwares expose a boolean-ish field
            stratum_active = (
                p.get('Stratum Active') if 'Stratum Active' in p
                else p.get('StratumActive') if 'StratumActive' in p
                else None
            )

            out.append({
                'url': url,
                'workername': user,
                'status': status,
                'priority': _to_int(prio),
                'stratum_active': _to_bool(stratum_active),
                'quota': _to_int(quota),
                'accepted': _to_int(accepted),
                'rejected': _to_int(rejected),
                # Keep the raw block if you need vendor-specific fields later
                'raw': p,
            })

        return out
    
def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def _to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {'1', 'true', 'yes', 'y', 'on', 'alive'}
    if isinstance(v, (int, float)):
        return v != 0
    return None

    def __getattr__(self, name, *args):
        return lambda *x: self.command(name, *x)
