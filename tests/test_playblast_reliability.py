"""Headless regression tests of the actual Maya adapter methods.

AST loading avoids importing Maya/Qt in CI; capture and QProcess are explicit
fakes. FFmpeg integration tests run real encodes and ffprobe on each host OS.
These tests do not claim to validate Maya's viewport or a physical GPU.
"""
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
import unittest
from unittest.mock import Mock, patch
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'animation tool kit scripts/Playblast_Creator/playblast_creator_ui.py'


def load_classes():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in
               ('PBCPlayblastUtils', 'PBCPlayblast')]
    qt = types.SimpleNamespace(QObject=object, Signal=lambda *a: Mock(),
                               QCoreApplication=types.SimpleNamespace(processEvents=lambda: None))
    ns = dict(os=os, sys=sys, shutil=shutil, subprocess=subprocess, tempfile=tempfile,
              re=re, traceback=traceback, time=time, QtCore=qt, cmds=Mock(), mel=Mock())
    presets = types.SimpleNamespace(parse_playblast_output_dir_path=lambda p:p,
                                   parse_playblast_output_filename=lambda p:p)
    ns['PlayblastCreatorCustomPresets'] = presets
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


NS = load_classes()
PBC = NS['PBCPlayblast']
UTIL = NS['PBCPlayblastUtils']


def engine():
    p = PBC.__new__(PBC)
    p.log_error = Mock()
    p.log_warning = Mock()
    p.log_output = Mock()
    p._h264_quality = 'High'
    p._h264_preset = 'fast'
    p._overwrite_output = False
    p._container_format = 'mp4'
    p._encoder = 'h264'
    p._camera = None
    p._visibility = []
    return p


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'shot.mp4'
        self.p = engine()
        self.args = ['-y', '-i', 'frames.%04d.png', '-c:v', 'h264_nvenc',
                     '-cq:v', '20', '-preset:v', 'p4', '-pix_fmt', 'yuv420p', '-an']

    def fake_encoder(self, success):
        def run(program, args):
            Path(args[-1]).write_bytes(b'new movie' if success else b'partial')
            return success
        return run

    def test_nvenc_driver_error_retries_software(self):
        calls = []
        def run(program, args):
            calls.append(list(args))
            Path(args[-1]).write_bytes(b'partial' if len(calls) == 1 else b'new movie')
            return len(calls) > 1
        self.p.execute_ffmpeg_command = run
        with patch.object(UTIL, 'detect_available_video_encoders', return_value={'libx264'}):
            self.assertTrue(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertIn('libx264', calls[1])
        self.assertNotIn('-cq:v', calls[1])
        self.assertNotIn('p4', calls[1])
        self.assertEqual(self.out.read_bytes(), b'new movie')
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.out])

    def test_videotoolbox_failure_retries_software(self):
        self.args[5:] = ['h264_videotoolbox', '-q:v', '11', '-pix_fmt', 'yuv420p', '-an']
        count = []
        def run(program, args):
            count.append(args[:])
            Path(args[-1]).write_bytes(b'video')
            return len(count) == 2
        self.p.execute_ffmpeg_command = run
        with patch.object(UTIL, 'detect_available_video_encoders', return_value={'libx264'}):
            self.assertTrue(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertNotIn('-q:v', count[1])

    def test_failed_encode_preserves_existing_even_with_overwrite(self):
        self.out.write_bytes(b'original')
        self.p._overwrite_output = True
        self.p.execute_ffmpeg_command = self.fake_encoder(False)
        with patch.object(UTIL, 'detect_available_video_encoders', return_value={'libx264'}):
            self.assertFalse(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertEqual(self.out.read_bytes(), b'original')
        self.assertEqual(len(list(Path(self.temp.name).iterdir())), 1)

    def test_existing_video_not_overwritten_without_checkbox(self):
        self.out.write_bytes(b'original')
        self.p.execute_ffmpeg_command = self.fake_encoder(True)
        self.assertFalse(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertEqual(self.out.read_bytes(), b'original')

    def test_successful_overwrite_replaces_video(self):
        self.out.write_bytes(b'original')
        self.p._overwrite_output = True
        self.p.execute_ffmpeg_command = self.fake_encoder(True)
        self.assertTrue(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertEqual(self.out.read_bytes(), b'new movie')

    def test_missing_software_fallback_fails_cleanly(self):
        self.p.execute_ffmpeg_command = Mock(side_effect=self.fake_encoder(False))
        with patch.object(UTIL, 'detect_available_video_encoders', return_value={'h264_nvenc'}):
            self.assertFalse(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertEqual(self.p.execute_ffmpeg_command.call_count, 1)
        self.assertFalse(self.out.exists())

    def test_zero_byte_success_is_rejected(self):
        self.p.execute_ffmpeg_command = Mock(return_value=True)
        self.assertFalse(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertFalse(self.out.exists())

    def test_publish_permission_error_preserves_output(self):
        self.out.write_bytes(b'original')
        self.p._overwrite_output = True
        self.p.execute_ffmpeg_command = self.fake_encoder(True)
        with patch.object(os, 'replace', side_effect=PermissionError('locked')):
            self.assertFalse(self.p._encode_and_publish('ffmpeg', self.args, str(self.out), 'h264'))
        self.assertEqual(self.out.read_bytes(), b'original')


class PlatformTests(unittest.TestCase):
    def test_platform_selection(self):
        for platform, available, expected in [
            ('win32', {'h264_nvenc', 'libx264'}, 'h264_nvenc'),
            ('win32', {'libx264'}, 'libx264'),
            ('darwin', {'h264_videotoolbox', 'libx264'}, 'h264_videotoolbox'),
            ('darwin', {'libx264'}, 'libx264'),
            ('linux', {'h264_nvenc', 'libx264'}, 'libx264')]:
            with self.subTest(platform=platform, available=available), patch.object(sys, 'platform', platform), patch.object(UTIL, 'detect_available_video_encoders', return_value=available):
                self.assertEqual(engine().get_platform_h264_video_codec(), expected)

    def test_no_compatible_encoder_has_actionable_error(self):
        with patch.object(UTIL, 'detect_available_video_encoders', return_value=set()):
            with self.assertRaisesRegex(RuntimeError, 'libx264'):
                engine().get_platform_h264_video_codec()

    def test_executable_path_variants(self):
        with tempfile.TemporaryDirectory(prefix='atk spaces ') as tmp:
            binary = Path(tmp) / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
            binary.write_text('placeholder')
            binary.chmod(0o755)
            self.assertEqual(UTIL.resolve_ffmpeg_executable('"' + str(binary) + '"'), str(binary))
            self.assertEqual(UTIL.resolve_ffmpeg_executable(tmp), str(binary))
            self.assertEqual(UTIL.resolve_ffmpeg_executable(str(binary) + '-missing'), '')

    @unittest.skipIf(sys.platform == 'win32', 'Unix permissions')
    def test_nonexecutable_file_rejected(self):
        with tempfile.NamedTemporaryFile() as f:
            self.assertEqual(UTIL.resolve_ffmpeg_executable(f.name), '')

    def test_encoder_cache_is_keyed_by_binary(self):
        UTIL.invalidate_encoder_cache()
        with patch.object(UTIL, 'resolve_ffmpeg_executable', side_effect=lambda p:p), patch.object(subprocess, 'Popen') as popen:
            popen.return_value.communicate.side_effect = [(b' V..... libx264 Encoder', None), (b' V..... mpeg4 Encoder', None)]
            self.assertEqual(UTIL.detect_available_video_encoders('first'), {'libx264'})
            self.assertEqual(UTIL.detect_available_video_encoders('second'), {'mpeg4'})
            self.assertEqual(popen.call_count, 2)
        UTIL.invalidate_encoder_cache()

    def test_probe_timeout_reaps_process(self):
        with patch.object(UTIL, 'resolve_ffmpeg_executable', return_value='ffmpeg'), patch.object(subprocess, 'Popen') as popen:
            popen.return_value.communicate.side_effect = [subprocess.TimeoutExpired('ffmpeg', 5), (b'', None)]
            self.assertEqual(UTIL.detect_available_video_encoders('ffmpeg', use_cache=False), set())
            popen.return_value.kill.assert_called_once()
            self.assertEqual(popen.return_value.communicate.call_count, 2)

    def test_frame_rates(self):
        for unit, expected in [('film',24), ('ntsc',30), ('23.976fps',23.976), ('60fps',60)]:
            with patch.object(NS['cmds'], 'currentUnit', return_value=unit):
                self.assertEqual(engine().get_frame_rate(), expected)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.p = engine()
        self.p.get_platform_h264_video_codec = Mock(return_value='libx264')
        self.p.get_viewport_panel = Mock(return_value='modelPanel4')
        self.p.get_active_camera = Mock(return_value='persp')
        self.p.set_active_camera = Mock()
        self.p.get_viewport_visibility = Mock(return_value=[True] * len(PBC.VIEWPORT_VISIBILITY_LOOKUP))
        self.p.set_viewport_visibility = Mock()
        self.p.get_resolution_width_height = Mock(return_value=(320,240))
        self.p.get_start_end_frame = Mock(return_value=(1,24))
        self.p.get_project_dir_path = Mock(return_value=self.temp.name)
        NS['cmds'].reset_mock()
        NS['cmds'].listCameras.return_value = ['persp']
        NS['cmds'].getAttr.return_value = 1.3
        NS['cmds'].currentTime.return_value = 10
        def capture(**kwargs):
            for index in range(24):
                Path(kwargs['filename'] + '.%04d.png' % index).write_bytes(b'captured')
            return kwargs['filename'] + '.0000.png'
        NS['cmds'].playblast.side_effect = capture
        for name, value in [('get_ffmpeg_path','ffmpeg'), ('resolve_ffmpeg_executable','ffmpeg'), ('get_temp_file_format','png')]:
            patcher = patch.object(UTIL, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.p.encode_video = Mock(return_value=False)

    def run_capture(self, **kwargs):
        return self.p.execute(self.temp.name, 'shot', show_in_viewer=False, include_sound=False, **kwargs)

    def test_capture_explicit_panel_and_state_restored_on_failure(self):
        NS['cmds'].playblast.side_effect = RuntimeError('capture failed')
        self.assertIsNone(self.run_capture())
        self.assertEqual(NS['cmds'].playblast.call_args.kwargs['editorPanelName'], 'modelPanel4')
        self.p.set_active_camera.assert_called_with('persp', 'modelPanel4')
        NS['cmds'].currentTime.assert_called_with(10, edit=True)
        NS['cmds'].setAttr.assert_called_with('persp.overscan', 1.3)
        self.p.encode_video.assert_not_called()

    def test_capture_cancel_does_not_encode(self):
        NS['cmds'].playblast.side_effect = None
        NS['cmds'].playblast.return_value = None
        self.assertIsNone(self.run_capture())
        self.p.encode_video.assert_not_called()

    def test_failed_encoding_keeps_capture_in_unique_folder(self):
        self.assertIsNone(self.run_capture())
        first = NS['cmds'].playblast.call_args.kwargs['filename']
        self.assertIsNone(self.run_capture())
        second = NS['cmds'].playblast.call_args.kwargs['filename']
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).parent.is_dir())
        self.assertTrue(Path(second).parent.is_dir())

    def test_overwrite_refusal_happens_before_capture(self):
        (Path(self.temp.name)/'shot.mp4').write_bytes(b'old')
        self.assertIsNone(self.run_capture())
        NS['cmds'].playblast.assert_not_called()
        self.assertIn('Output tab', self.p.log_error.call_args.args[0])

    def test_linux_movie_preference_uses_png(self):
        with patch.object(sys, 'platform', 'linux'), patch.object(UTIL, 'get_temp_file_format', return_value='movie'):
            self.run_capture()
        args = NS['cmds'].playblast.call_args.kwargs
        self.assertEqual(args['format'], 'image')
        self.assertEqual(args['compression'], 'png')
        self.assertNotIn('sound', args)

    def test_image_output_returns_actual_result(self):
        self.p._container_format = 'Image'
        self.p._encoder = 'png'
        self.p._image_quality = 100
        self.assertTrue(self.run_capture().endswith('.0000.png'))

    def test_incomplete_capture_is_not_encoded(self):
        def capture(**kwargs):
            Path(kwargs['filename'] + '.0000.png').write_bytes(b'frame')
            return kwargs['filename'] + '.0000.png'
        NS['cmds'].playblast.side_effect = capture
        self.assertIsNone(self.run_capture())
        self.p.encode_video.assert_not_called()
        self.assertIn('Incomplete capture', self.p.log_error.call_args.args[0])

    def test_invalid_range_does_not_leave_temp_folder(self):
        self.p.get_start_end_frame.return_value = (24,1)
        self.assertIsNone(self.run_capture())
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_invalid_filename_is_rejected(self):
        for filename in ['../escape', 'shot:bad', 'CON', 'folder\\shot', 'shot?']:
            with self.subTest(filename=filename):
                self.assertIsNone(self.p.execute(self.temp.name, filename))
        NS['cmds'].playblast.assert_not_called()


class ProcessTests(unittest.TestCase):
    def test_exit_status_and_start_failure(self):
        for started, status, code, expected in [(False,0,0,False), (True,0,1,False), (True,1,0,False), (True,0,0,True)]:
            with self.subTest(started=started, status=status, code=code):
                p = engine()
                p._ffmpeg_process = Mock()
                p._ffmpeg_process.waitForStarted.return_value = started
                p._ffmpeg_process.waitForFinished.return_value = True
                p._ffmpeg_process.exitStatus.return_value = status
                p._ffmpeg_process.exitCode.return_value = code
                p._ffmpeg_process.readAllStandardError.return_value = b'invalid utf8 \xff'
                with patch.object(NS['QtCore'], 'QProcess', types.SimpleNamespace(NormalExit=0, NotRunning=0), create=True):
                    self.assertEqual(p.execute_ffmpeg_command('ffmpeg', ['-y']), expected)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg integration requires ffmpeg and ffprobe')
class RealFFmpegTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ATK test spaces ')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        # PPM input avoids external image libraries; deliberately odd dimensions.
        for i in range(12):
            (self.folder/('frame.%04d.ppm' % i)).write_bytes(b'P6\n65 49\n255\n' + bytes([255, i*10, 0]) * (65*49))
        self.pattern = str(self.folder/'frame.%04d.ppm')
        self.p = engine()
        self.p.get_frame_rate = lambda:24.0
        self.p.get_audio_attributes = lambda:(None,None)
        self.p.get_platform_h264_video_codec = lambda:'libx264'
        self.calls = []
        def run(program, args):
            self.calls.append(args[:])
            proc = subprocess.run([program, '-nostdin', '-hide_banner', '-loglevel', 'error'] + args,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.last_stderr = proc.stderr.decode('utf-8', errors='replace')
            return proc.returncode == 0
        self.p.execute_ffmpeg_command = run

    def probe(self, path):
        result = subprocess.run(['ffprobe', '-v','error','-count_frames','-show_streams','-of','json',str(path)], check=True, capture_output=True)
        return json.loads(result.stdout)['streams']

    def test_real_h264_mpeg4_prores_containers(self):
        for encoder, container, expected in [('h264','mp4','h264'), ('h264','mov','h264'), ('mpeg4','mp4','mpeg4'), ('mpeg4','mov','mpeg4'), ('prores','mov','prores')]:
            with self.subTest(encoder=encoder, container=container):
                out = self.folder/('movie-'+encoder+'.'+container)
                self.assertTrue(self.p.encode_video(encoder, 'ffmpeg', self.pattern, str(out), 1, include_audio=False), self.last_stderr)
                video = self.probe(out)[0]
                self.assertEqual(video['codec_name'], expected)
                self.assertEqual(video['nb_read_frames'], '12')
                self.assertEqual((video['width'], video['height']), (66,50))
                self.assertEqual(video['r_frame_rate'], '24/1')

    def test_real_audio_offsets_and_duration(self):
        wav = self.folder/'audio.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-y',str(wav)], check=True)
        for offset in [-6, 0, 6]:
            with self.subTest(offset=offset):
                self.p.get_audio_attributes = lambda:(str(wav), offset)
                out = self.folder/('audio%d.mp4' % offset)
                self.assertTrue(self.p.encode_video('h264','ffmpeg',self.pattern,str(out),0),self.last_stderr)
                streams = self.probe(out)
                self.assertEqual([s['codec_type'] for s in streams], ['video','audio'])
                self.assertEqual(streams[0]['nb_read_frames'],'12')
                self.assertAlmostEqual(float(streams[0]['duration']),0.5,places=2)
                if offset > 0:
                    raw = subprocess.run(['ffmpeg','-v','error','-i',str(out),'-t','0.20','-f','s16le','-ac','1','-'],check=True,capture_output=True).stdout
                    import array
                    samples = array.array('h',raw)
                    self.assertLess(max(abs(x) for x in samples),10)

    def test_real_hardware_failure_then_software(self):
        self.p.get_platform_h264_video_codec = lambda:'h264_nvenc'
        real_run = self.p.execute_ffmpeg_command
        def driver_failure(program,args):
            if 'h264_nvenc' in args:
                self.calls.append(args[:])
                Path(args[-1]).write_bytes(b'partial')
                self.p.log_warning('Driver does not support required NVENC API 13.1; found 13.0')
                return False
            return real_run(program,args)
        self.p.execute_ffmpeg_command = driver_failure
        out = self.folder/'fallback.mp4'
        with patch.object(UTIL,'detect_available_video_encoders',return_value={'libx264','h264_nvenc'}):
            self.assertTrue(self.p.encode_video('h264','ffmpeg',self.pattern,str(out),1,False), getattr(self,'last_stderr',''))
        self.assertEqual(self.probe(out)[0]['nb_read_frames'],'12')
        self.assertEqual(len(self.calls),2)

    def test_real_transcode_without_audio(self):
        source = self.folder/'source.mp4'
        self.assertTrue(self.p.encode_video('h264','ffmpeg',self.pattern,str(source),1,False))
        output = self.folder/'transcoded.mov'
        self.assertTrue(self.p.transcode_video('h264','ffmpeg',str(source),str(output),True),self.last_stderr)
        self.assertEqual(len(self.probe(output)),1)

    def test_real_missing_frames_failure_preserves_existing(self):
        output = self.folder/'existing.mp4'
        output.write_bytes(b'keep me')
        self.p._overwrite_output = True
        self.assertFalse(self.p.encode_video('h264','ffmpeg',str(self.folder/'missing.%04d.png'),str(output),1,False))
        self.assertEqual(output.read_bytes(),b'keep me')


if __name__ == '__main__':
    unittest.main()
