"""Configure and diagnose OpenCode + iosctl + iOSRemoteBridge, without dependencies."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid

from .opencode_jsonc import Document

ROOT = Path(__file__).resolve().parents[2]
MARKER = '<!-- managed by iosctl opencode -->'
REQUIRED_TOOLS = {'get_device_info', 'get_screen_frame', 'get_orientation',
                  'get_connection_status', 'get_performance_stats', 'tap',
                  'double_tap', 'long_press', 'swipe', 'insert_text', 'type_text',
                  'press_home', 'launch_app', 'disconnect'}
MISSING = object()


def absolute(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('all configured paths must be absolute')
    return path.resolve()


def validate_paths(args):
    args.bridge_root = absolute(args.bridge_root)
    args.config = absolute(args.config)
    args.python = absolute(args.python)
    if args.opencode_config:
        args.opencode_config = absolute(args.opencode_config)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.server_name):
        raise ValueError('server name must contain 1..64 letters, digits, underscores or hyphens')
    for name in ('__init__.py', 'client.py', 'protocol.py', 'mcp_tools.py', 'mcp_stdio.py'):
        if not (args.bridge_root / 'automation' / name).is_file():
            raise ValueError('update --bridge-root to an iOSRemoteBridge checkout with native stdlib MCP')
    if not args.config.is_file():
        raise ValueError('--config must reference an existing private pairing file')
    if not args.python.is_file():
        raise ValueError('--python must reference a Python 3.9+ executable')


def command(args, control=False):
    result = [str(args.python), '-B', str(ROOT / 'bin/iosctl'), 'iosremote',
              '--bridge-root', str(args.bridge_root), '--config', str(args.config), '--stdlib']
    if control:
        result.append('--control')
    return result


def read_config(path):
    raw = path.read_bytes() if path.exists() else b'{}\n'
    if len(raw) > 1024 * 1024:
        raise ValueError('OpenCode config exceeds 1 MiB')
    return raw, Document(raw.decode('utf-8'))


def managed_command(argv):
    if any(Path(part).name == 'run_iosremote_mcp.py' for part in argv if isinstance(part, str)):
        return True
    return ('iosremote' in argv and
            any(Path(part).name == 'iosctl' for part in argv if isinstance(part, str)))


def server_path(document, name):
    mcp = document.root.value.get('mcp', {})
    if not isinstance(mcp, dict):
        raise ValueError('mcp must be an object')
    if 'servers' in mcp:
        if not isinstance(mcp['servers'], dict):
            raise ValueError('mcp.servers must be an object')
        if set(mcp) - {'servers', 'timeout'}:
            raise ValueError('mixed legacy and v2 MCP layouts; normalize the config first')
        return ['mcp', 'servers', name], mcp['servers'].get(name), True
    # Retain an existing legacy layout; new configurations use OpenCode v2.
    if set(mcp) - {'timeout'}:
        return ['mcp', name], mcp.get(name), False
    return ['mcp', 'servers', name], None, True


def instructions(args):
    cli = shlex.join([str(args.python), '-B', str(ROOT / 'bin/iosctl')])
    return f'''{MARKER}
# iOS bridges

System services run on the host executing OpenCode. Use the fixed iosctl adapter
for settings, alarms, calendars, reminders, Siri language and Live Activities.
First run `{cli} capabilities`, then `{cli} call OPERATION --params JSON`.
Pass JSON as one strictly quoted argument; never build a shell command from task data.
Only call an implemented operation whose runtime is ready. Read back writes;
retain verified/partial/unavailable/error, source, timestamps and scope limits.
On a desktop, not_ios describes this host, not the paired phone. Use an existing
authorized device terminal for system services; the visual pairing is not SSH.

Read the service guide at {ROOT / 'skills/ios-control-bridge/SKILL.md'} and the
visual guide at {ROOT / 'skills/ios-computer-use/SKILL.md'} when relevant.
The {args.server_name} MCP server supplies screen and input tools. Observe a fresh
image, act once, then observe again. Coordinates are normalized natural portrait.
Use insert_text for literal Unicode after checking literal_text_ready and focus;
it does not submit. Never replay an ambiguous input or substitute ASCII keys.
One paired UI session is available at a time. Disconnect when finished. A connected
MCP catalog does not prove phone connectivity, unlock state or image delivery.
Keep pairing contents and personal device records out of logs and repositories.
'''


def replace_file(path, content, original=MISSING):
    """Back up before an atomic replacement; keep existing private file modes."""
    current = path.read_bytes() if path.exists() else None
    if original is not MISSING and current != original:
        raise ValueError('file changed during configuration; rerun setup')
    if current == content:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if current is not None else 0o600
    backup = None
    if current is not None:
        backup = path.with_name(path.name + '.bak-' + uuid.uuid4().hex)
        fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(current)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(backup) if backup else None


def setup(args):
    existed = args.opencode_config.exists()
    raw, document = read_config(args.opencode_config)
    path, existing, native = server_path(document, args.server_name)
    argv = command(args, args.control)
    if existing is not None:
        if (not isinstance(existing, dict) or existing.get('type') != 'local'
                or not isinstance(existing.get('command'), list)
                or not managed_command(existing['command'])):
            raise ValueError('server name is already used by another MCP; choose --server-name')
    server = dict(existing or {})
    server.update(type='local', command=argv)
    if native:
        server.setdefault('disabled', False)
        server.setdefault('timeout', {'startup': 10000, 'catalog': 10000, 'execution': 80000})
    else:
        server.setdefault('enabled', True)
        server.setdefault('timeout', 80000)
    text = document.text if existing == server else document.set(path, server)
    guide = args.opencode_config.with_name('ios-bridges.md')
    text = Document(text).append('instructions', str(guide))
    guide_bytes = instructions(args).encode('utf-8')
    old_guide = guide.read_bytes() if guide.exists() else None
    if old_guide is not None and not old_guide.startswith(MARKER.encode()):
        raise ValueError('ios-bridges.md already contains unmanaged content')
    updated = text.encode('utf-8')
    changed = updated != raw or old_guide != guide_bytes or not args.opencode_config.exists()
    backups = []
    if args.apply and changed:
        backup = replace_file(guide, guide_bytes, old_guide)
        if backup:
            backups.append(backup)
        backup = replace_file(args.opencode_config, updated,
                              raw if existed else None)
        if backup:
            backups.append(backup)
    return {'action': 'applied' if args.apply else 'preview', 'changed': changed,
            'opencode_config': str(args.opencode_config), 'instructions': str(guide),
            'server': args.server_name,
            'mcp': {'type': 'local', 'command': argv, 'input_requested': args.control}, 'backups': backups,
            'next': 'Reload the OpenCode server, reopen its client, then run doctor and opencode mcp list.',
            'device_connection_tested': False}


def doctor(args):
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
         'params': {'name': 'get_connection_status', 'arguments': {}}},
    ]
    response = subprocess.run(command(args), input=('\n'.join(json.dumps(m) for m in messages) + '\n').encode(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12, cwd=str(ROOT))
    try:
        rows = {row['id']: row for row in map(json.loads, response.stdout.splitlines())}
        names = {tool['name'] for tool in rows[2]['result']['tools']}
        session = rows[3]['result']
        state = json.loads(session['content'][0]['text'])
        stdio_ok = (response.returncode == 0 and not session.get('isError')
                    and state['connected'] is False and REQUIRED_TOOLS <= names
                    and rows[1]['result']['serverInfo']['name'] == 'iOSRemoteBridge')
    except (ValueError, KeyError, TypeError):
        stdio_ok, names = False, set()
    report = {'mcp_stdio': {'ready': stdio_ok, 'tool_count': len(names),
                            'missing_tools': sorted(REQUIRED_TOOLS - names)},
              'device_connection_tested': False}
    if args.opencode_config:
        _, document = read_config(args.opencode_config)
        _, server, native = server_path(document, args.server_name)
        if not isinstance(server, dict) or not isinstance(server.get('command'), list):
            raise ValueError('configured MCP server is missing or invalid')
        expected = command(args, '--control' in server['command'])
        guide = args.opencode_config.with_name('ios-bridges.md')
        wired = (isinstance(server, dict) and server.get('type') == 'local'
                 and server.get('command') == expected
                 and (not server.get('disabled', False) if native else server.get('enabled', True))
                 and str(guide) in document.root.value.get('instructions', [])
                 and guide.is_file() and guide.read_text(encoding='utf-8') == instructions(args))
        report['opencode_config'] = {'ready': wired}
        stdio_ok = stdio_ok and wired
    service = subprocess.run([str(args.python), '-B', str(ROOT / 'bin/iosctl'), 'capabilities'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12, cwd=str(ROOT))
    catalog = json.loads(service.stdout)
    entries = catalog['data']['operations']
    report['system_services'] = {'status': catalog['status'],
                                 'ready_operations': sum(bool(op['runtime']['ready_to_query']) for op in entries),
                                 'unavailable_reasons': sorted({op['runtime']['reason'] for op in entries
                                                              if op['runtime']['reason']})}
    report['ready'] = stdio_ok and service.returncode == 0
    return report


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('setup', 'doctor'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--bridge-root', required=True)
        cmd.add_argument('--config', required=True, help='existing private pairing JSON; contents are never copied')
        cmd.add_argument('--opencode-config', required=name == 'setup', help='actual config from opencode debug paths/config')
        cmd.add_argument('--python', default=sys.executable, help='absolute Python 3.9+ executable')
        cmd.add_argument('--server-name', default='iosremote')
        if name == 'setup':
            cmd.add_argument('--control', action='store_true')
            cmd.add_argument('--apply', action='store_true', help='apply the preview, retaining a backup')
    args = parser.parse_args(argv)
    try:
        validate_paths(args)
        output = setup(args) if args.action == 'setup' else doctor(args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        # Do not echo command output, provider configuration or pairing data.
        print(json.dumps({'ready': False, 'error': str(exc) if isinstance(exc, ValueError)
                          else 'integration check failed: ' + type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output.get('ready', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
