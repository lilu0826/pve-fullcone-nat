#!/usr/bin/env python3
"""Destructive only inside explicitly marked disposable test VM namespaces."""
import concurrent.futures
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
RESULTS = []
PROCESSES = []
CONTROL = Path(tempfile.mkdtemp(prefix='fc-peer-'))
ENABLED = sys.argv[1] == 'enabled'


def run(*args, ns=None, stdin=None, check=True):
    command = (['ip', 'netns', 'exec', ns] if ns else []) + list(args)
    return subprocess.run(command, input=stdin, text=True, capture_output=True, check=check)


def rpc(ns, method, **args):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15)
        sock.connect(str(CONTROL / ns))
        sock.sendall(json.dumps({'method': method, **args}).encode() + b'\n')
        result = json.loads(sock.makefile('rb').readline())
    if not result['ok']:
        if result['error'] in ('TimeoutError', 'ConnectionRefusedError'):
            raise TimeoutError(result['detail'])
        raise RuntimeError(result)
    return result['value']


def blocked(ns, method, **args):
    try:
        rpc(ns, method, timeout=1, **args)
    except TimeoutError:
        return
    raise AssertionError(f'Unexpectedly allowed {ns} {method} {args}')


def link(namespace, interface, peer_ns, peer_interface, address, peer_address):
    run('ip', 'link', 'add', interface, 'type', 'veth', 'peer', 'name', peer_interface, ns=namespace)
    run('ip', 'link', 'set', peer_interface, 'netns', peer_ns, ns=namespace)
    for ns, dev, ip in [(namespace, interface, address), (peer_ns, peer_interface, peer_address)]:
        run('ip', 'addr', 'add', ip, 'dev', dev, ns=ns)
        run('ip', 'link', 'set', dev, 'up', ns=ns)


def rules(expression='masquerade', forward_drop=False):
    run('nft', 'flush', 'ruleset', ns='r')
    run('conntrack', '-F', ns='r')
    text = f'''table ip nat {{
      chain post {{ type nat hook postrouting priority srcnat; oifname "wan" {expression}; }}
    }}\n'''
    if forward_drop:
        text += '''table inet filter {
          chain forward { type filter hook forward priority filter; policy drop;
            ct state established,related accept
            iifname { "lan1", "lan2" } accept
          }
        }\n'''
    run('nft', '-f', '-', ns='r', stdin=text)


def setup():
    release = run('uname', '-r').stdout.strip()
    if not Path('/run/fullcone-test-vm').exists() or not ('fullcone-test' in release or release == '7.0.14-23-fullcone-pve'):
        raise SystemExit('Run only in the provided disposable QEMU test VM')
    for ns in ('r', 'h1', 'h2', 'a', 'b'):
        run('ip', 'netns', 'add', ns)
        run('ip', 'link', 'set', 'lo', 'up', ns=ns)
    link('r', 'lan1', 'h1', 'eth0', '10.0.1.1/24', '10.0.1.2/24')
    link('r', 'lan2', 'h2', 'eth0', '10.0.2.1/24', '10.0.2.2/24')
    # The bridge belongs to the VM, not the NAT router namespace.
    run('ip', 'link', 'add', 'outside', 'type', 'bridge')
    run('ip', 'link', 'set', 'outside', 'up')
    for ns, addr in [('r', '198.18.0.1'), ('a', '198.18.0.2'), ('b', '198.18.0.3')]:
        run('ip', 'link', 'add', ns+'-wire', 'type', 'veth', 'peer', 'name', ns+'-end')
        run('ip', 'link', 'set', ns+'-wire', 'master', 'outside')
        run('ip', 'link', 'set', ns+'-wire', 'up')
        run('ip', 'link', 'set', ns+'-end', 'netns', ns)
        run('ip', 'link', 'set', ns+'-end', 'name', 'wan', ns=ns)
        run('ip', 'addr', 'add', addr+'/24', 'dev', 'wan', ns=ns)
        run('ip', 'link', 'set', 'wan', 'up', ns=ns)
    for ns, gateway in [('h1', '10.0.1.1'), ('h2', '10.0.2.1')]:
        run('ip', 'route', 'add', 'default', 'via', gateway, ns=ns)
    run('sysctl', '-qw', 'net.ipv4.ip_forward=1', ns='r')
    for ns in ('r', 'h1', 'h2', 'a', 'b'):
        run('sysctl', '-qw', 'net.ipv4.conf.all.rp_filter=0', ns=ns)
        run('sysctl', '-qw', 'net.ipv4.conf.default.rp_filter=0', ns=ns)
    for ns, addr in [('h1', '10.0.1.2'), ('h2', '10.0.2.2'), ('a', '198.18.0.2'), ('b', '198.18.0.3'), ('r', '198.18.0.1')]:
        process = subprocess.Popen(['ip', 'netns', 'exec', ns, 'python3', str(HERE/'peer.py'), str(CONTROL/ns), addr])
        PROCESSES.append(process)
    end = time.monotonic() + 10
    while not all((CONTROL / ns).exists() for ns in ('r', 'h1', 'h2', 'a', 'b')):
        if time.monotonic() > end:
            raise TimeoutError('Peer startup timed out')
        time.sleep(.05)
    for ns in ('a', 'b'):
        for port in (9000, 9001):
            rpc(ns, 'udp_open', port=port)
            rpc(ns, 'tcp_listen', port=port)


def udp_case(random=False):
    rules('masquerade fully-random' if random else 'masquerade')
    port = 5101 if random else 5100
    rpc('h1', 'udp_open', port=port)
    first = rpc('h1', 'udp_probe', port=port, destination=['198.18.0.2', 9000])['observed']
    second = rpc('h1', 'udp_probe', port=port, destination=['198.18.0.3', 9001])['observed']
    assert first[0] == second[0] == '198.18.0.1', (first, second)
    rpc('b', 'udp_open', port=port+1000)
    if ENABLED:
        assert first == second, (first, second)
        reply = rpc('b', 'udp_probe', port=port+1000, destination=first)
        assert reply['responder'] == first and reply['observed'] == ['198.18.0.3', port+1000], reply
    else:
        blocked('b', 'udp_probe', port=port+1000, destination=first)


def tcp_case():
    rules('masquerade fully-random')
    first = rpc('h1', 'tcp_probe', port=5200, destination=['198.18.0.2', 9000])
    second = rpc('h1', 'tcp_probe', port=5200, destination=['198.18.0.3', 9001])
    assert first['observed'][0] == '198.18.0.1'
    rpc('h1', 'tcp_listen', port=5200)
    if ENABLED:
        assert first['observed'] == second['observed'], (first, second)
        inbound = rpc('b', 'tcp_probe', port=6200, destination=first['observed'])
        assert inbound['observed'] == ['198.18.0.3', 6200], inbound
        assert inbound['bytes_each_direction'] == 32768
        state = run('conntrack', '-L', '-p', 'tcp', ns='r').stdout
        assert 'ESTABLISHED' in state and '[ASSURED]' in state, state
    else:
        blocked('b', 'tcp_probe', port=6200, destination=first['observed'])
    rpc('h1', 'tcp_close_all')
    rpc('b', 'tcp_close_all')
    end = time.monotonic() + 2
    while time.monotonic() < end:
        state = run('conntrack', '-L', '-p', 'tcp', ns='r').stdout
        if 'ESTABLISHED' not in state:
            break
        time.sleep(.05)
    assert 'ESTABLISHED' not in state, state


def firewall_case():
    rules(forward_drop=True)
    rpc('h1', 'udp_open', port=5300)
    endpoint = rpc('h1', 'udp_probe', port=5300, destination=['198.18.0.2', 9000])['observed']
    rpc('b', 'udp_open', port=6300)
    blocked('b', 'udp_probe', port=6300, destination=endpoint)
    endpoint = rpc('h1', 'tcp_probe', port=5301, destination=['198.18.0.2', 9000])['observed']
    rpc('h1', 'tcp_listen', port=5301)
    blocked('b', 'tcp_probe', port=6301, destination=endpoint)


def snat_case():
    rules('snat to 198.18.0.1')
    rpc('h2', 'udp_open', port=5400)
    endpoint = rpc('h2', 'udp_probe', port=5400, destination=['198.18.0.2', 9000])['observed']
    assert endpoint[0] == '198.18.0.1'
    rpc('b', 'udp_open', port=6400)
    blocked('b', 'udp_probe', port=6400, destination=endpoint)


def dnat_case():
    rules()
    rpc('h1', 'udp_open', port=5500)
    rpc('h2', 'udp_open', port=5501)
    endpoint = rpc('h1', 'udp_probe', port=5500, destination=['198.18.0.2', 9000])['observed']
    run('nft', '-f', '-', ns='r', stdin=f'''add chain ip nat pre {{ type nat hook prerouting priority dstnat + 10; }}
add rule ip nat pre iifname "wan" udp dport {endpoint[1]} dnat to 10.0.2.2:5501
''')
    rpc('b', 'udp_open', port=6500)
    reply = rpc('b', 'udp_probe', port=6500, destination=endpoint)
    assert reply['responder'] == endpoint
    # Inspect the actual translated destination, not merely the echoed bytes.
    state = run('conntrack', '-L', '-p', 'udp', ns='r').stdout
    assert 'src=10.0.2.2 dst=198.18.0.3 sport=5501' in state, state


def local_service_case():
    rules('masquerade to :5600')
    rpc('h1', 'udp_open', port=5601)
    endpoint = rpc('h1', 'udp_probe', port=5601, destination=['198.18.0.2', 9000])['observed']
    rpc('r', 'udp_open', port=5600)
    rpc('b', 'udp_open', port=6600)
    rpc('b', 'udp_probe', port=6600, destination=endpoint)
    state = run('conntrack', '-L', '-p', 'udp', ns='r').stdout
    inbound = [line for line in state.splitlines() if 'src=198.18.0.3 dst=198.18.0.1 sport=6600' in line]
    assert inbound and 'src=198.18.0.1 dst=198.18.0.3 sport=5600' in inbound[0], state


def concurrency_case():
    rules('masquerade fully-random')
    endpoints = [(ns, port) for ns in ('h1', 'h2') for port in range(10000, 10024)]
    for ns, port in endpoints:
        rpc(ns, 'udp_open', port=port)
    jobs = [(ns, port, remote) for ns, port in endpoints for remote in ('198.18.0.2', '198.18.0.3')]
    def probe(job):
        ns, port, remote = job
        return (ns, port), rpc(ns, 'udp_probe', port=port, destination=[remote, 9000])['observed']
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        values = list(pool.map(probe, jobs))
    seen = {}
    for inside, outside in values:
        if inside in seen:
            assert seen[inside] == outside, (inside, seen[inside], outside)
        seen[inside] = outside
    assert len({tuple(value) for value in seen.values()}) == len(endpoints)


def exhaustion_case():
    rules('masquerade to :45000-45001')
    for ns, port in [('h1', 5700), ('h2', 5700), ('h1', 5701)]:
        rpc(ns, 'udp_open', port=port)
    a = rpc('h1', 'udp_probe', port=5700, destination=['198.18.0.2', 9000])['observed']
    b = rpc('h2', 'udp_probe', port=5700, destination=['198.18.0.3', 9000])['observed']
    assert a != b and {a[1], b[1]} == {45000, 45001}, (a, b)
    blocked('h1', 'udp_probe', port=5701, destination=['198.18.0.2', 9001])


def lifecycle_case():
    rules()
    rpc('h1', 'udp_open', port=5800)
    rpc('b', 'udp_open', port=6800)
    endpoint = rpc('h1', 'udp_probe', port=5800, destination=['198.18.0.2', 9000])['observed']
    rpc('b', 'udp_probe', port=6800, destination=endpoint)
    run('conntrack', '-F', ns='r')
    blocked('b', 'udp_probe', port=6800, destination=endpoint)
    # Use a different external source after creating the mapping anew.
    endpoint = rpc('h1', 'udp_probe', port=5800, destination=['198.18.0.2', 9000])['observed']
    run('ip', 'link', 'set', 'wan', 'down', ns='r')
    time.sleep(.5)
    run('ip', 'link', 'set', 'wan', 'up', ns='r')
    time.sleep(.5)
    rpc('b', 'udp_open', port=6801)
    blocked('b', 'udp_probe', port=6801, destination=endpoint)
    rpc('h1', 'udp_open', port=5801)
    old = rpc('h1', 'udp_probe', port=5801, destination=['198.18.0.2', 9000])['observed']
    run('ip', 'addr', 'del', '198.18.0.1/24', 'dev', 'wan', ns='r')
    run('ip', 'addr', 'add', '198.18.0.10/24', 'dev', 'wan', ns='r')
    time.sleep(.5)
    state = run('conntrack', '-L', '-p', 'udp', ns='r').stdout
    assert f'dst=198.18.0.1 sport=9000 dport={old[1]}' not in state, state
    new = rpc('h1', 'udp_probe', port=5801, destination=['198.18.0.2', 9000])['observed']
    assert new[0] == '198.18.0.10', new
    run('ip', 'addr', 'del', '198.18.0.10/24', 'dev', 'wan', ns='r')
    run('ip', 'addr', 'add', '198.18.0.1/24', 'dev', 'wan', ns='r')


def ipv6_case():
    rules()
    for ns, dev, addr in [('r','lan1','fd00:1::1/64'),('h1','eth0','fd00:1::2/64'),('r','wan','2001:db8:1::1/64'),('a','wan','2001:db8:1::2/64'),('b','wan','2001:db8:1::3/64')]:
        run('ip','-6','addr','add',addr,'dev',dev,'nodad',ns=ns)
    run('sysctl','-qw','net.ipv6.conf.all.forwarding=1',ns='r')
    run('ip','-6','route','add','default','via','fd00:1::1',ns='h1')
    run('nft','-f','-',ns='r',stdin='table ip6 nat { chain post { type nat hook postrouting priority srcnat; oifname "wan" masquerade; } }\n')
    rpc('h1','udp_open',port=5900,address='fd00:1::2')
    rpc('a','udp_open',port=9900,address='2001:db8:1::2')
    rpc('b','udp_open',port=6900,address='2001:db8:1::3')
    endpoint=rpc('h1','udp_probe',port=5900,destination=['2001:db8:1::2',9900])['observed']
    assert endpoint[0]=='2001:db8:1::1',endpoint
    blocked('b','udp_probe',port=6900,destination=endpoint)


def low_port_case():
    rules()
    rpc('h1', 'udp_open', port=500)
    endpoint = rpc('h1', 'udp_probe', port=500, destination=['198.18.0.2', 9000])['observed']
    if ENABLED:
        assert 1024 <= endpoint[1] <= 65535, endpoint
    else:
        assert endpoint[1] == 500, endpoint


def zone_case():
    rules()
    run('nft', '-f', '-', ns='r', stdin='''table ip raw {
      chain pre { type filter hook prerouting priority raw;
        iifname "lan1" ct zone set 42
        iifname "wan" udp sport 9000 ct zone set 42
      }
    }\n''')
    rpc('h1', 'udp_open', port=5950)
    endpoint = rpc('h1', 'udp_probe', port=5950, destination=['198.18.0.2', 9000])['observed']
    rpc('b', 'udp_open', port=6950)
    blocked('b', 'udp_probe', port=6950, destination=endpoint)
    run('nft', 'add', 'rule', 'ip', 'raw', 'pre', 'iifname', 'wan', 'udp', 'sport', '6951', 'ct', 'zone', 'set', '42', ns='r')
    rpc('b', 'udp_open', port=6951)
    # The return packet must select the same zone as the inbound new flow.
    reply = rpc('b', 'udp_probe', port=6951, destination=endpoint)
    assert reply['responder'] == endpoint, reply


def main():
    try:
        setup()
        cases = [('udp', udp_case), ('udp-fully-random', lambda: udp_case(True)), ('tcp-handshake-and-data', tcp_case), ('forward-drop', firewall_case), ('explicit-snat-isolation', snat_case), ('explicit-dnat-precedence', dnat_case), ('low-source-port', low_port_case), ('local-service-precedence', local_service_case), ('ipv6-unchanged', ipv6_case)]
        if ENABLED:
            cases += [('concurrent-eim-and-uniqueness', concurrency_case), ('port-exhaustion', exhaustion_case), ('flush-and-wan-down', lifecycle_case), ('conntrack-zone-isolation', zone_case)]
        for name, case in cases:
            try:
                case()
            except Exception as exc:
                RESULTS.append({'test': name, 'status': 'FAIL', 'detail': repr(exc)})
                raise
            RESULTS.append({'test': name, 'status': 'PASS'})
            print(f'PASS: {name}', flush=True)
    finally:
        print('TEST_RESULTS=' + json.dumps({'mode': sys.argv[1], 'tests': RESULTS}), flush=True)
        for process in PROCESSES:
            process.terminate()
        for process in PROCESSES:
            process.wait(timeout=5)
        for ns in ('r', 'h1', 'h2', 'a', 'b'):
            run('ip', 'netns', 'delete', ns, check=False)


if __name__ == '__main__':
    main()
