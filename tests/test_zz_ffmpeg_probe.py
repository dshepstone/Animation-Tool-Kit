"""TEMPORARY diagnostic: delay method x AAC bitrate with the real playblast command."""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_playblast_reliability import run_bounded


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class ProbeDelayBitrate(unittest.TestCase):
    def test_print_variants(self):
        with tempfile.TemporaryDirectory(prefix='ATK test spaces ') as tmp:
            d = Path(tmp)
            for i in range(12):
                (d / ('frame.%04d.ppm' % i)).write_bytes(b'P6\n65 49\n255\n' + bytes([255, i * 10, 0]) * (65 * 49))
            wav = str(d / 'audio.wav')
            run_bounded(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                         'sine=frequency=440:duration=2', '-y', wav])
            video_in = ['-framerate', '24.0', '-start_number', '0', '-i', str(d / 'frame.%04d.ppm')]
            video_out = ['-c:v', 'libx264', '-crf:v', '20', '-preset:v', 'fast', '-profile:v', 'high',
                         '-pix_fmt', 'yuv420p']
            tail = ['-shortest', '-t', '0.500000', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart']
            delays = {
                'adelay': (['-i', wav], ['-map', '0:v:0', '-map', '1:a:0',
                                         '-af', 'adelay=250:all=1,apad=whole_dur=0.500000']),
                'itsoffset+aresample': (['-itsoffset', '0.250000', '-i', wav],
                                        ['-map', '0:v:0', '-map', '1:a:0',
                                         '-af', 'aresample=async=1:first_pts=0,apad=whole_dur=0.500000']),
                'no delay': (['-i', wav], ['-map', '0:v:0', '-map', '1:a:0', '-af', 'apad=whole_dur=0.500000']),
            }
            rates = {
                '192k': ['-b:a', '192k'],
                '128k': ['-b:a', '128k'],
                'default': [],
                '192k fast coder': ['-b:a', '192k', '-aac_coder', 'fast'],
                '192k 48k stereo': ['-b:a', '192k', '-ar', '48000', '-ac', '2'],
            }
            n = 0
            for dname, (ain, amap) in delays.items():
                for rname, ropts in rates.items():
                    n += 1
                    out = d / ('out%d.mp4' % n)
                    start = time.time()
                    try:
                        code, _, err = run_bounded(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
                                                   + video_in + ain + video_out + amap + ['-c:a', 'aac'] + ropts
                                                   + tail + [str(out)], timeout=12)
                        print('=== %s | %s: exit %s in %.1fs' % (dname, rname, code, time.time() - start))
                    except AssertionError:
                        print('=== %s | %s: HUNG' % (dname, rname))
                    sys.stdout.flush()
            for rname, ropts in rates.items():
                out = d / 'late.m4a'
                try:
                    code, _, _ = run_bounded(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                                              'sine=frequency=440:duration=1', '-af', 'adelay=250:all=1',
                                              '-c:a', 'aac'] + ropts + [str(out)], timeout=12)
                    print('=== audio-only silence-then-tone | %s: exit %s' % (rname, code))
                except AssertionError:
                    print('=== audio-only silence-then-tone | %s: HUNG' % rname)
                sys.stdout.flush()


if __name__ == '__main__':
    unittest.main()
