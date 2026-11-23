"""TEMPORARY diagnostic: which delayed-audio command finishes on this FFmpeg."""
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_playblast_reliability import run_bounded


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class ProbeDelayedAudio(unittest.TestCase):
    def test_print_variants(self):
        print('\n=== ' + subprocess.run(['ffmpeg', '-version'], capture_output=True,
                                       stdin=subprocess.DEVNULL, timeout=30).stdout.decode().splitlines()[0])
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for i in range(12):
                (d / ('f.%04d.ppm' % i)).write_bytes(b'P6\n65 49\n255\n' + bytes([255, i * 10, 0]) * (65 * 49))
            wav = d / 'a.wav'
            run_bounded(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                         'sine=frequency=440:duration=2', '-y', str(wav)])
            video = ['-framerate', '24', '-start_number', '0', '-i', str(d / 'f.%04d.ppm')]
            enc = ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2']
            amap = ['-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac']
            variants = {
                'A adelay all=1 + apad whole_dur + shortest + t':
                    video + ['-i', str(wav)] + enc + amap + ['-af', 'adelay=250:all=1,apad=whole_dur=0.5', '-shortest', '-t', '0.5'],
                'B adelay all=1 + t only':
                    video + ['-i', str(wav)] + enc + amap + ['-af', 'adelay=250:all=1', '-t', '0.5'],
                'C adelay 250|250 + t':
                    video + ['-i', str(wav)] + enc + amap + ['-af', 'adelay=250|250', '-t', '0.5'],
                'D adelay all=1 audio only':
                    ['-i', str(wav), '-af', 'adelay=250:all=1', '-t', '0.5', '-c:a', 'aac'],
                'E itsoffset + aresample async + apad whole_dur + t':
                    video + ['-itsoffset', '0.25', '-i', str(wav)] + enc + amap +
                    ['-af', 'aresample=async=1:first_pts=0,apad=whole_dur=0.5', '-t', '0.5'],
                'F anullsrc concat + apad whole_dur + t':
                    video + ['-i', str(wav), '-f', 'lavfi', '-t', '0.25', '-i', 'anullsrc=r=44100:cl=mono'] + enc +
                    ['-filter_complex', '[2:a][1:a]concat=n=2:v=0:a=1,apad=whole_dur=0.5[a]',
                     '-map', '0:v:0', '-map', '[a]', '-c:a', 'aac', '-t', '0.5'],
                'G apad whole_dur + t (no delay)':
                    video + ['-i', str(wav)] + enc + amap + ['-af', 'apad=whole_dur=0.5', '-shortest', '-t', '0.5'],
            }
            for name, args in variants.items():
                out = d / ('out_%s.mp4' % name[0])
                start = time.time()
                try:
                    code, _, err = run_bounded(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'verbose', '-y']
                                               + args + [str(out)], timeout=20)
                    tail = err.decode('utf-8', 'replace').strip().splitlines()[-3:]
                    print('=== %s: exit %s in %.1fs | %s' % (name, code, time.time() - start, ' / '.join(tail)))
                except AssertionError as exc:
                    print('=== %s: HUNG | %s' % (name, str(exc)[-1500:]))
                sys.stdout.flush()


if __name__ == '__main__':
    unittest.main()
