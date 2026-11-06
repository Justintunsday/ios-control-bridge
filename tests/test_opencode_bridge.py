import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import opencode as bridge
from ios_control_bridge.opencode_jsonc import Document


class JsoncTests(unittest.TestCase):
    def test_preserves_unrelated_comments_urls_and_trailing_commas(self):
        source = '''// top
{"provider": {"url": "https://example.com/a/*b*/,}",}, /* keep */
 "mcp": {"servers": {"other": {"type":"remote","url":"https://example.com"},}},
 "instructions": ["custom.md", /* retain this */],
} // end
'''
        text = Document(source).set(['mcp', 'servers', 'iosremote'], {'type': 'local', 'command': ['space name', "quote's"]})
        text = Document(text).append('instructions', '/absolute/guide.md')
        actual = Document(text).root.value
        self.assertEqual(actual['provider'], Document(source).root.value['provider'])
        for comment in ('// top', '/* keep */', '/* retain this */', '// end'):
            self.assertIn(comment, text)
        self.assertEqual(actual['instructions'], ['custom.md', '/absolute/guide.md'])
        self.assertEqual(Document(text).append('instructions', '/absolute/guide.md'), text)

    def test_nested_creation_and_replacement(self):
        for source in ('{}', '{/* comment */}', '{"mcp":{},}', '{"mcp":{"servers":{}}}'):
            text = Document(source).set(['mcp', 'servers', 'iosremote'], {'command': ['one']})
            self.assertEqual(Document(text).root.value['mcp']['servers']['iosremote'], {'command': ['one']})
            text = Document(text).set(['mcp', 'servers', 'iosremote'], {'command': ['two']})
            self.assertEqual(Document(text).root.value['mcp']['servers']['iosremote'], {'command': ['two']})

    def test_ambiguous_or_invalid_documents_are_rejected(self):
        for source in ('{"mcp":{},"mcp":{}}', '{"x":', '[]', '{} {}', '{/* unclosed', '{"x":NaN}', '{"x":1e999}', '{"x":,}', '{1:2}'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                Document(source)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="桥 space & quote's-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.backend = self.root / 'backend checkout'
        automation = self.backend / 'automation'
        automation.mkdir(parents=True)
        for name in ('__init__.py', 'client.py', 'protocol.py', 'mcp_tools.py', 'mcp_stdio.py'):
            (automation / name).write_text('# fixture\n', encoding='utf-8')
        self.pairing = self.root / 'private pairing.json'
        self.pairing.write_text('PAIRING_SECRET_MUST_NOT_BE_READ', encoding='utf-8')
        self.config = self.root / 'opencode.jsonc'
        self.original = b'// preserve provider and formatting\n{"provider":{"key":"PROVIDER_SECRET"},"instructions":["mine.md", /* keep */],}\n'
        self.config.write_bytes(self.original)
        self.args = argparse.Namespace(bridge_root=self.backend, config=self.pairing,
            python=Path(sys.executable), opencode_config=self.config, server_name='iosremote',
            control=False, apply=False)

    def test_preview_apply_backup_idempotence_and_no_secret_disclosure(self):
        bridge.validate_paths(self.args)
        preview = bridge.setup(self.args)
        self.assertEqual(preview['action'], 'preview')
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse(self.config.with_name('ios-bridges.md').exists())
        self.assertNotIn('SECRET', json.dumps(preview))
        self.args.apply = True
        applied = bridge.setup(self.args)
        value = Document(self.config.read_text(encoding='utf-8')).root.value
        self.assertEqual(value['provider']['key'], 'PROVIDER_SECRET')
        self.assertIn('/* keep */', self.config.read_text(encoding='utf-8'))
        self.assertEqual(value['instructions'][0], 'mine.md')
        self.assertIn('--stdlib', value['mcp']['servers']['iosremote']['command'])
        self.assertNotIn('--control', value['mcp']['servers']['iosremote']['command'])
        self.assertEqual(Path(applied['backups'][0]).read_bytes(), self.original)
        again = bridge.setup(self.args)
        self.assertFalse(again['changed'])
        self.assertEqual(again['backups'], [])

    def test_existing_legacy_servers_and_private_environment_are_preserved(self):
        legacy = {'mcp': {'other': {'enabled': False}, 'iosremote': {
            'type': 'local', 'command': ['python', '/old/run_iosremote_mcp.py'],
            'enabled': False, 'environment': {'SECRET': 'DO_NOT_PRINT'}, 'timeout': 90000}}}
        self.config.write_text(json.dumps(legacy), encoding='utf-8')
        self.args.control, self.args.apply = True, True
        output = bridge.setup(self.args)
        value = Document(self.config.read_text(encoding='utf-8')).root.value
        self.assertEqual(value['mcp']['other'], legacy['mcp']['other'])
        self.assertNotIn('servers', value['mcp'])
        self.assertIn('--control', value['mcp']['iosremote']['command'])
        self.assertFalse(value['mcp']['iosremote']['enabled'])
        self.assertEqual(value['mcp']['iosremote']['timeout'], 90000)
        self.assertNotIn('DO_NOT_PRINT', json.dumps(output))

    def test_foreign_server_conflicts_are_preserved(self):
        original = b'{"mcp":{"servers":{"iosremote":{"type":"local","command":["foreign"]}}}}'
        self.config.write_bytes(original)
        self.args.apply = True
        with self.assertRaisesRegex(ValueError, 'another MCP'):
            bridge.setup(self.args)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(self.config.with_name('ios-bridges.md').exists())

    def test_partial_old_backend_is_rejected_before_configuration(self):
        (self.backend / 'automation/mcp_stdio.py').unlink()
        with self.assertRaisesRegex(ValueError, 'native stdlib'):
            bridge.validate_paths(self.args)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_missing_and_concurrently_changed_files_are_not_overwritten(self):
        file = self.root / 'concurrent.json'
        file.write_bytes(b'new data')
        with self.assertRaisesRegex(ValueError, 'changed'):
            bridge.replace_file(file, b'planned data', None)
        with self.assertRaisesRegex(ValueError, 'changed'):
            bridge.replace_file(file, b'planned data', b'old data')
        self.assertEqual(file.read_bytes(), b'new data')

    def test_new_config_and_unmanaged_instruction_file(self):
        self.config.unlink()
        self.args.apply = True
        output = bridge.setup(self.args)
        self.assertTrue(self.config.is_file())
        self.assertEqual(output['backups'], [])
        guide = self.config.with_name('ios-bridges.md')
        guide.write_text('owned content', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            bridge.setup(self.args)
        self.assertEqual(guide.read_text(encoding='utf-8'), 'owned content')


@unittest.skipUnless(os.environ.get('IOSREMOTE_BRIDGE_TEST_ROOT'), 'set IOSREMOTE_BRIDGE_TEST_ROOT for cross-repository integration')
class CrossRepositoryTests(unittest.TestCase):
    def test_actual_configured_process_from_an_unrelated_working_directory(self):
        root = Path(os.environ['IOSREMOTE_BRIDGE_TEST_ROOT']).resolve()
        with tempfile.TemporaryDirectory(prefix="MCP space & quote's-") as temporary:
            directory = Path(temporary)
            pairing = directory / 'unread-private.json'
            pairing.write_text('PAIRING_SECRET_NOT_JSON', encoding='utf-8')
            config = directory / 'opencode.jsonc'
            script = Path(__file__).resolve().parents[1] / 'tools/opencode_bridge.py'
            shared = ['--bridge-root', str(root), '--config', str(pairing), '--opencode-config', str(config)]
            def run(action, *extra):
                return subprocess.run([sys.executable, '-S', str(script), action, *shared, *extra],
                    cwd=directory, capture_output=True, text=True, encoding='utf-8', timeout=30)
            setup = run('setup', '--control', '--apply')
            self.assertEqual(setup.returncode, 0, setup.stderr)
            doctor = run('doctor')
            self.assertEqual(doctor.returncode, 0, doctor.stderr + doctor.stdout)
            output = json.loads(doctor.stdout)
            self.assertTrue(output['ready'])
            self.assertEqual(output['mcp_stdio']['tool_count'], 14)
            self.assertFalse(output['device_connection_tested'])
            self.assertNotIn('PAIRING_SECRET', setup.stdout + doctor.stdout)


if __name__ == '__main__':
    unittest.main()
