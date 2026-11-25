"""Tests for the Gumroad release script's text and file planning (no network)."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'gumroad_release.py'
spec = importlib.util.spec_from_file_location('gumroad_release', SCRIPT)
gr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gr)

NOTES = """# Animation Tool Kit 1.1.30 — Title

## Fixed: something

Line one
continues here with **bold** and `code`.

- first item
- second [link](https://example.com)
"""


class ParseVersion(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(gr.parse_version('ATK_1.1.29'), '1.1.29')
        self.assertEqual(gr.parse_version('ATK_v1-1-3'), '1.1.3')
        with self.assertRaises(ValueError):
            gr.parse_version('latest')


class Markdown(unittest.TestCase):
    def test_converts_release_notes(self):
        out = gr.markdown_to_html(NOTES)
        self.assertNotIn('Title', out)
        self.assertIn('<h3>Fixed: something</h3>', out)
        self.assertIn('<p>Line one continues here with <strong>bold</strong> and <code>code</code>.</p>', out)
        self.assertIn('<ul><li>first item</li><li>second <a href="https://example.com">link</a></li></ul>', out)

    def test_escapes_html(self):
        self.assertIn('&lt;script&gt;', gr.markdown_to_html('a <script> tag'))


class Description(unittest.TestCase):
    def test_bumps_versions_and_adds_block_at_top(self):
        old = '<p>Version 1.1.29 of ATK. Needs Maya 2024.</p>'
        new, how = gr.update_description(old, '1.1.30', NOTES)
        self.assertEqual(how, 'top')
        self.assertIn('<p>Version 1.1.30 of ATK. Needs Maya 2024.</p>', new)
        self.assertTrue(new.startswith(gr.CHANGELOG_START))
        self.assertIn("<h2>What's new in 1.1.30</h2>", new)

    def test_replaces_between_markers_only(self):
        old = ('<p>Intro v1.1.29</p>' + gr.CHANGELOG_START + '<h2>What\'s new in 1.1.29</h2><p>old</p>'
               + gr.CHANGELOG_END + '<p>Footer</p>')
        new, how = gr.update_description(old, '1.1.30', NOTES)
        self.assertEqual(how, 'markers')
        self.assertNotIn('<p>old</p>', new)
        self.assertIn('<p>Intro v1.1.30</p>', new)
        self.assertTrue(new.endswith('<p>Footer</p>'))
        self.assertEqual(new.count(gr.CHANGELOG_START), 1)

    def test_replaces_whats_new_heading_up_to_next_h2(self):
        old = ('<p>Intro</p><h2>What&#39;s new in 1.1.29</h2><p>old</p><ul><li>x</li></ul>'
               '<h2>Requirements</h2><p>Maya</p>')
        new, how = gr.update_description(old, '1.1.30', NOTES)
        self.assertEqual(how, 'heading')
        self.assertNotIn('<p>old</p>', new)
        self.assertIn('<h2>Requirements</h2><p>Maya</p>', new)

    def test_never_downgrades(self):
        self.assertEqual(gr.bump_versions('Version 2.0.0', '1.1.30'), 'Version 2.0.0')


class Files(unittest.TestCase):
    def test_swaps_only_the_atk_zip_in_place(self):
        current = [{'id': 'a', 'name': 'Guide.pdf'}, {'id': 'b', 'name': 'AnimationToolKit_v1_1_29'},
                   {'id': 'c', 'name': 'Bonus.zip'}]
        files, removed = gr.plan_files(current, 'https://s3/x.zip', 'AnimationToolKit_v1_1_30', 'cli-upload-x')
        self.assertEqual(removed, ['b'])
        self.assertEqual([f['id'] for f in files], ['a', 'cli-upload-x', 'c'])
        self.assertEqual(files[1]['url'], 'https://s3/x.zip')

    def test_repoints_file_embeds(self):
        doc = {'type': 'doc', 'content': [{'type': 'paragraph'}, {'type': 'fileEmbed', 'attrs': {'id': 'b'}},
                                          {'type': 'fileEmbed', 'attrs': {'id': 'a'}}]}
        swapped, count = gr.swap_file_embeds(doc, {'b'}, 'new')
        self.assertEqual(count, 1)
        self.assertEqual(swapped['content'][1]['attrs']['id'], 'new')
        self.assertEqual(swapped['content'][2]['attrs']['id'], 'a')
        self.assertEqual(doc['content'][1]['attrs']['id'], 'b')


class ManualSteps(unittest.TestCase):
    def test_lists_only_missing_steps(self):
        text = gr.manual_steps('1.1.30', Path('AnimationToolKit_v1_1_30.zip'), ['boom'], True, False)
        self.assertIn('AnimationToolKit_v1_1_30.zip', text)
        self.assertNotIn('Product** tab', text)
        self.assertIn('- boom', text)


class TransportErrors(unittest.TestCase):
    def test_connection_failure_becomes_gumroad_error(self):
        import urllib.error
        from unittest import mock
        with mock.patch.object(gr.urllib.request, 'urlopen', side_effect=urllib.error.URLError('down')):
            with self.assertRaises(gr.GumroadError):
                gr.Gumroad('t').call('GET', '/products/x')

    def test_lookup_failure_writes_manual_steps(self):
        import os
        import tempfile
        import urllib.error
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            manual = Path(tmp) / 'manual.md'
            env = {'GUMROAD_ACCESS_TOKEN': 't', 'RELEASE_TAG': 'ATK_1.1.30', 'RELEASE_BODY': 'notes',
                   'MANUAL_STEPS_FILE': str(manual), 'ASSETS_DIR': tmp}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(gr.urllib.request, 'urlopen', side_effect=urllib.error.URLError('down')), \
                    mock.patch('builtins.print'):
                gr.main()
            self.assertIn('Could not read the product', manual.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
