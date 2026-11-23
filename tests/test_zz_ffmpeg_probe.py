"""TEMPORARY diagnostic: which AAC settings survive digital silence on FFmpeg 9.1."""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_playblast_reliability import run_bounded


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class ProbeAacSilence(unittest.TestCase):
    def test_print_variants(self):
        sources = {
            'silence 2s mono44k': ['-f', 'lavfi', '-t', '2', '-i', 'anullsrc=r=44100:cl=mono'],
            'silence 2s stereo48k': ['-f', 'lavfi', '-t', '2', '-i', 'anullsrc=r=48000:cl=stereo'],
            'tone then 1s pad': ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-af', 'apad=whole_dur=2'],
        }
        settings = {
            '192k': ['-b:a', '192k'],
            '160k': ['-b:a', '160k'],
            '128k': ['-b:a', '128k'],
            'default': [],
            '192k fast coder': ['-b:a', '192k', '-aac_coder', 'fast'],
            '192k twoloop': ['-b:a', '192k', '-aac_coder', 'twoloop'],
            '192k stereo out': ['-b:a', '192k', '-ac', '2'],
            '192k 48k out': ['-b:a', '192k', '-ar', '48000'],
        }
        with tempfile.TemporaryDirectory() as tmp:
            for sname, src in sources.items():
                for name, opts in settings.items():
                    out = Path(tmp) / 'o.m4a'
                    start = time.time()
                    try:
                        code, _, err = run_bounded(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
                                                   + src + ['-c:a', 'aac'] + opts + [str(out)], timeout=10)
                        print('=== %s | %s: exit %s in %.1fs %s' % (sname, name, code, time.time() - start,
                                                                     err.decode('utf-8', 'replace')[-200:].strip()))
                    except AssertionError:
                        print('=== %s | %s: HUNG' % (sname, name))
                    sys.stdout.flush()


if __name__ == '__main__':
    unittest.main()
