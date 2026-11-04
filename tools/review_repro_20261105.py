"""Offline observations of the reviewed revision; never talks to a device/network."""
from contextlib import ExitStack
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ios_control_bridge import activities, calendar, ellekit_bridge, files

ID = '00000000-0000-4000-8000-000000000001'
SOURCE_A = '00000000-0000-4000-8000-000000000002'
SOURCE_B = '00000000-0000-4000-8000-000000000003'
VERSION = {'ProductVersion': '16.1.1', 'ProductBuildVersion': '20B101'}
observations = {}

def bridge_paths(stack, directory):
    for name, value in {'DIRECTORY': directory, 'COMMAND_PATH': directory / 'spring.cmd',
                        'RESULT_PATH': directory / 'spring.result',
                        'COMMAND_TMP': directory / 'spring.cmd.tmp'}.items():
        stack.enter_context(patch.object(ellekit_bridge, name, value))

with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    helper = directory / 'helper'
    helper.touch()
    probes = []
    for value in (10, 20):
        payload = {'schema': activities.NATIVE_SCHEMA, 'source': activities.NATIVE_SOURCE,
                   'status': 'verified', 'requested_activity_id': ID, 'complete_for_scope': True,
                   'target_found': True,
                   'activity': {'descriptor': {'id': ID}, 'state': {'active': {}},
                                'contentState': {'encoding': 'decoded-data', 'decoded': {'value': value}}},
                   'content': {'value': value}}
        probes.append(subprocess.CompletedProcess([], 0, json.dumps(payload), ''))
    with patch.object(activities, 'ios_version', return_value=VERSION), \
         patch.object(activities, 'helper_path', return_value=helper), \
         patch.object(activities.subprocess, 'run', side_effect=probes), \
         patch.object(activities.time, 'monotonic', side_effect=[0, 0, 2]), \
         patch.object(activities.time, 'sleep'):
        result = activities.watch_activity({'activity_id': ID, 'duration_ms': 1000,
                                            'stop_on_change': True})
    observations['live_activity_body_change'] = {
        'input_content_values': [10, 20], 'observed_changed': result['data']['changed'],
        'observed_stopped_early': result['data']['stopped_early'], 'expected_changed': True,
        'reproduced': result['data']['changed'] is False}

    with patch.object(files.os, 'scandir', side_effect=PermissionError('audit fixture')):
        result = files.search_files({'path': str(directory), 'query': 'anything'})
    observations['search_permission_error'] = {
        'status': result['status'], 'complete_for_scope': result['complete_for_scope'],
        'count': result['data']['count'], 'expected': 'unavailable_or_partial',
        'reproduced': result['status'] == 'verified' and result['complete_for_scope']}

    ipc = directory / 'ipc'
    ipc.mkdir()
    with ExitStack() as stack:
        bridge_paths(stack, ipc)
        result = ellekit_bridge.request('set_orientation_lock', 1, timeout=0)
    observations['pending_write_after_timeout'] = {
        'result': result, 'command_still_present': (ipc / 'spring.cmd').exists(),
        'reproduced': result['detail'] == 'bridge_timeout' and (ipc / 'spring.cmd').exists()}

    alias_ipc = directory / 'alias-ipc'
    alias_ipc.mkdir()
    victim = directory / 'fixture-config'
    victim.write_text('original configuration', encoding='utf8')
    alias = alias_ipc / 'spring.cmd.tmp'
    try:
        alias.symlink_to(victim)
        link_kind = 'symlink'
    except OSError:
        os.link(victim, alias)
        link_kind = 'hardlink_windows_fallback'
    with ExitStack() as stack:
        bridge_paths(stack, alias_ipc)
        ellekit_bridge.request('get_low_power', timeout=0)
    observations['command_tmp_follows_alias'] = {
        'link_kind': link_kind, 'fixture_config_overwritten': victim.read_text(encoding='utf8') != 'original configuration',
        'scope': 'owned temporary file only; no privileged file accessed',
        'reproduced': victim.read_text(encoding='utf8') != 'original configuration'}

    concurrent = directory / 'concurrent'
    concurrent.mkdir()
    real_replace = os.replace
    a_ready, b_done = threading.Event(), threading.Event()
    answers = {}
    worker_errors = []
    def interleaved_replace(source, target):
        if threading.current_thread().name == 'audit-A':
            a_ready.set()
            if not b_done.wait(2): raise RuntimeError('interleaving timed out')
            return real_replace(source, target)
        if not a_ready.wait(2): raise RuntimeError('interleaving timed out')
        real_replace(source, target)
        request_id = Path(target).read_text(encoding='utf8').splitlines()[0]
        (concurrent / 'spring.result').write_text(request_id + '\nok\n1\nfixture\n', encoding='utf8')
        b_done.set()
    def worker(label):
        try:
            answers[label] = ellekit_bridge.request('get_low_power', timeout=0.5)
        except Exception as error:
            worker_errors.append(type(error).__name__)
    with ExitStack() as stack:
        bridge_paths(stack, concurrent)
        stack.enter_context(patch.object(ellekit_bridge.os, 'replace', side_effect=interleaved_replace))
        a = threading.Thread(target=worker, args=('A',), name='audit-A')
        b = threading.Thread(target=worker, args=('B',), name='audit-B')
        a.start()
        if not a_ready.wait(2): raise RuntimeError('A did not reach replace')
        b.start()
        a.join(3)
        b.join(3)
        if a.is_alive() or b.is_alive() or worker_errors: raise RuntimeError('concurrency fixture failed')
    observations['two_client_command_race'] = {
        'results': answers, 'reproduced': answers['A'].get('detail') == 'bridge_command_write_failed'
        and answers['B'].get('status') == 'ok'}

    native = {'schema': calendar.NATIVE_SCHEMA, 'source': calendar.NATIVE_SOURCE,
              'status': 'verified', 'calendar': {'id': ID, 'title': 'Repeated title', 'source_id': SOURCE_B}}
    with patch.object(calendar, 'ios_version', return_value=VERSION), \
         patch.object(calendar, 'helper_path', return_value=helper), \
         patch.object(calendar.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(native), '')):
        result = calendar.create_calendar({'title': 'Repeated title', 'source_id': SOURCE_A})
    observations['calendar_wrong_source_boundary'] = {
        'requested_source': SOURCE_A, 'returned_source': SOURCE_B, 'status': result['status'],
        'scope': 'Python boundary; native same-title selection reviewed statically',
        'reproduced': result['status'] == 'verified'}

    native = {'schema': calendar.NATIVE_SCHEMA, 'source': calendar.NATIVE_SOURCE,
              'status': 'verified', 'event': {'id': 'fixture-event', 'title': 'Fixture',
                                            'calendar_id': ID, 'start': 0, 'end': 1}}
    with patch.object(calendar, 'ios_version', return_value=VERSION), \
         patch.object(calendar, 'helper_path', return_value=helper), \
         patch.object(calendar.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(native), '')):
        result = calendar.create_event({'calendar_id': ID, 'title': 'Fixture',
                                        'start': '2026-11-05T10:00:00Z', 'end': '2026-11-05T11:00:00Z',
                                        'notes': 'fixture notes'})
    observations['event_wrong_times_boundary'] = {
        'returned_start': 0, 'returned_end': 1, 'status': result['status'],
        'expected': 'readback_mismatch', 'reproduced': result['status'] == 'verified'}

    nested = directory / 'nested'
    nested.mkdir()
    (nested / 'fixture-match.txt').write_text('fixture', encoding='utf8')
    result = files.search_files({'path': str(directory), 'query': 'fixture-match'})
    row = result['data']['matches'][0]
    observations['recursive_match_no_location'] = {
        'returned_fields': sorted(row), 'expected': 'path_or_relative_path',
        'reproduced': 'path' not in row and 'relative_path' not in row}

record = {'reviewed_revision': 'ec2a8882c143690c162b332ac943d3f2b4d7fad1',
          'scope': 'offline mocks and temporary files; no device/network operations',
          'observations': observations,
          'reproduced': sum(item['reproduced'] for item in observations.values()),
          'cases': len(observations)}
(ROOT / 'local').mkdir(exist_ok=True)
(ROOT / 'local/review-regressions.json').write_text(json.dumps(record, indent=2), encoding='utf8')
print(json.dumps(record, indent=2))
