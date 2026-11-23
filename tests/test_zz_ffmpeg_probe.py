"""TEMPORARY diagnostic: which option makes the delayed-audio encode hang."""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_playblast_reliability import run_bounded

FULL = ['-y', '-framerate', '24.0', '-start_number', '0', '-i', '{frames}', '-i', '{wav}',
        '-c:v', 'libx264', '-crf:v', '20', '-preset:v', 'fast', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
        '-map', '0:v:0', '-map', '1:a:0', '-af', 'adelay=250:all=1,apad=whole_dur=0.500000',
        '-c:a', 'aac', '-b:a', '192k', '-shortest', '-t', '0.500000',
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart']


def without(args, *pairs):
    out = list(args)
    for flag in pairs:
        i = out.index(flag)
        del out[i:i + (1 if flag == '-shortest' else 2)]
    return out


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class ProbeDelayedAudio(unittest.TestCase):
    def test_print_variants(self):
        with tempfile.TemporaryDirectory(prefix='ATK test spaces ') as tmp:
            d = Path(tmp)
            for i in range(12):
                (d / ('frame.%04d.ppm' % i)).write_bytes(b'P6\n65 49\n255\n' + bytes([255, i * 10, 0]) * (65 * 49))
            wav = d / 'audio.wav'
            run_bounded(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                         'sine=frequency=440:duration=2', '-y', str(wav)])
            full = [a.format(frames=str(d / 'frame.%04d.ppm'), wav=str(wav)) for a in FULL]
            variants = [
                ('full', full),
                ('no faststart', without(full, '-movflags')),
                ('no -b:a', without(full, '-b:a')),
                ('no -shortest', without(full, '-shortest')),
                ('no -t', without(full, '-t')),
                ('no crf/preset/profile', without(full, '-crf:v', '-preset:v', '-profile:v')),
                ('framerate 24', [('24' if a == '24.0' else a) for a in full]),
                ('no -vf pad', without(full, '-vf')),
                ('loglevel info', full),
            ]
            for n, (name, args) in enumerate(variants):
                level = 'info' if name == 'loglevel info' else 'error'
                out = d / ('out%d.mp4' % n)
                start = time.time()
                try:
                    code, _, err = run_bounded(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', level]
                                               + args + [str(out)], timeout=15)
                    print('=== %s: exit %s in %.1fs' % (name, code, time.time() - start))
                except AssertionError as exc:
                    print('=== %s: HUNG | %s' % (name, str(exc)[-800:]))
                sys.stdout.flush()


if __name__ == '__main__':
    unittest.main()
