#!/usr/bin/env python

import os
import random
import shutil
import string
import sys
import unittest

# modify the path so that parent directory is in it
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))

from converter import ffmpeg, formats, codecs, Converter, ConverterError  # NOQA


FFMPEG_PATH = 'ffmpeg'
FFPROBE_PATH = 'ffprobe'


def verify_progress(p):
    if not p:
        return False

    li = list(p)
    if len(li) < 1:
        return False

    prev = 0
    for i in li:
        if not isinstance(i, float) or i < 0 or i > 1:
            return False
        if i < prev:
            return False
        prev = i
    return True


class TestFFMpeg(unittest.TestCase):

    def setUp(self):
        os.chdir(current_dir)
        temp_name = ''.join(random.choice(string.ascii_uppercase + string.digits)
                            for _ in range(20))

        self.temp_dir = os.path.join(current_dir, temp_name)

        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

        self.transcodings = [
            {
                "path": os.path.join(self.temp_dir, "output.ogg"),
                "audio_codec": "libvorbis",
                "audio_channels": 1,
                "audio_bitrate": "16k",
                "audio_samplerate": 11025,
                "video_codec": "libtheora",
                "video_framerate": 15,
                "video_width": 360,
                "video_height": 200,
                "video_bitrate": "128k"
            }
        ]
        self.video_file_path = os.path.join(self.temp_dir, 'output.ogg')
        self.audio_file_path = os.path.join(self.temp_dir, 'output.mp3')
        self.shot_file_path = os.path.join(self.temp_dir, 'shot.png')
        self.shot2_file_path = os.path.join(self.temp_dir, 'shot2.png')
        self.shot3_file_path = os.path.join(self.temp_dir, 'shot3.png')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def assertRaisesSpecific(self, exception, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
            raise Exception(
                'Expected exception %s not raised' % repr(exception))
        except exception:
            ex = sys.exc_info()[1]
            return ex

    @staticmethod
    def ensure_notexist(f):
        if os.path.exists(f):
            os.unlink(f)

    def test_ffmpeg_probe(self):
        self.assertRaisesSpecific(
            ffmpeg.FFMpegError, ffmpeg.FFMpeg, ffmpeg_path='/foo', ffprobe_path='/bar')

        f = ffmpeg.FFMpeg(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

        self.assertEqual(None, f.probe('nonexistent'))
        self.assertEqual(None, f.probe('/dev/null'))

        info = f.probe('test1.ogg')
        self.assertEqual('ogg', info.format.format)
        self.assertAlmostEqual(33.00, info.format.duration, places=2)
        self.assertEqual(2, len(info.streams))

        v = info.streams[0]
        self.assertEqual(v, info.video)
        self.assertEqual('video', v.type)
        self.assertEqual('theora', v.codec)
        self.assertEqual(720, v.video_width)
        self.assertEqual(400, v.video_height)
        self.assertEqual(None, v.bitrate)
        self.assertAlmostEqual(25.00, v.video_fps, places=2)
        self.assertEqual(v.metadata['ENCODER'], 'ffmpeg2theora 0.19')

        a = info.streams[1]
        self.assertEqual(a, info.audio)
        self.assertEqual('audio', a.type)
        self.assertEqual('vorbis', a.codec)
        self.assertEqual(2, a.audio_channels)
        self.assertEqual(80000, a.bitrate)
        self.assertEqual(48000, a.audio_samplerate)
        self.assertEqual(a.metadata['ENCODER'], 'ffmpeg2theora 0.19')
        self.assertEqual(repr(info), 'MediaInfo(format=MediaFormatInfo(duration=32.996875, format=ogg, ), streams=['
                                     'MediaStreamInfo(type=video, codec=theora, width=720, height=400, fps=25.0, start_time=0.000000, ENCODER=ffmpeg2theora 0.19), '
                                     'MediaStreamInfo(type=audio, codec=vorbis, channels=2, rate=48000, start_time=0.000000, bitrate=80000, ENCODER=ffmpeg2theora 0.19)])')

    def test_ffmpeg_convert(self):
        f = ffmpeg.FFMpeg(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

        def consume(fn, *args, **kwargs):
            return list(fn(*args, **kwargs))

        self.assertRaisesSpecific(
            ffmpeg.FFMpegError, consume, f.convert, 'nonexistent', self.video_file_path, [])

        self.assertRaisesSpecific(
            ffmpeg.FFMpegConvertError, consume, f.convert, '/etc/passwd', self.video_file_path, [])

        info = f.probe('test1.ogg')
        convert_options = list()
        convert_options.append([
            '-codec:a', 'libvorbis', '-b:a', '16k', '-ac', '1', '-ar', '11025',
            '-codec:v', 'libtheora', '-r', '15', '-s', '360x200', '-b', '128k'])
        conv = f.convert('test1.ogg', [self.video_file_path], convert_options)

        last_tc = 0.0
        for tc in conv:
            assert (last_tc < tc <= info.format.duration + 0.1), (
                last_tc, tc, info.format.duration)

        self._assert_converted_video_file()

    def _assert_converted_video_file(self):
        """
            Asserts converted test1.ogg (in path self.video_file_path) is converted correctly
        """
        f = ffmpeg.FFMpeg(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        info = f.probe(self.video_file_path)
        self.assertEqual('ogg', info.format.format)
        self.assertAlmostEqual(33.00, info.format.duration, places=0)
        self.assertEqual(2, len(info.streams))

        self.assertEqual('video', info.video.type)
        self.assertEqual('theora', info.video.codec)
        self.assertEqual(360, info.video.video_width)
        self.assertEqual(200, info.video.video_height)
        self.assertAlmostEqual(15.00, info.video.video_fps, places=2)

        self.assertEqual('audio', info.audio.type)
        self.assertEqual('vorbis', info.audio.codec)
        self.assertEqual(1, info.audio.audio_channels)
        self.assertEqual(11025, info.audio.audio_samplerate)

    def test_ffmpeg_termination(self):
        # test when ffmpeg is killed
        f = ffmpeg.FFMpeg(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        convert_options = list()
        convert_options.append([
            '-codec:a', 'libvorbis', '-b:a', '16k', '-ac', '1', '-ar', '11025',
            '-codec:v', 'libtheora', '-r', '15', '-s', '360x200', '-b', '128k'])
        p_list = {}  # modifiable object in closure
        f._spawn = lambda * \
            args: p_list.setdefault('', ffmpeg.FFMpeg._spawn(*args))
        conv = f.convert('test1.ogg', [self.video_file_path], convert_options)
        next(conv)  # let ffmpeg to start
        p = p_list['']
        p.terminate()
        self.assertRaisesSpecific(ffmpeg.FFMpegConvertError, list, conv)

    def test_ffmpeg_thumbnail(self):
        f = ffmpeg.FFMpeg(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        thumb = self.shot_file_path
        thumb2 = self.shot2_file_path

        self.assertRaisesSpecific(
            IOError, f.thumbnail, 'nonexistent', 10, thumb)

        self.ensure_notexist(thumb)
        f.thumbnail('test1.ogg', 10, thumb)
        self.assertTrue(os.path.exists(thumb))

        self.ensure_notexist(thumb)
        self.assertRaisesSpecific(
            ffmpeg.FFMpegError, f.thumbnail, 'test1.ogg', 34, thumb)
        self.assertFalse(os.path.exists(thumb))

        # test multiple thumbnail
        self.ensure_notexist(thumb)
        self.ensure_notexist(thumb2)
        f.thumbnails('test1.ogg', [
            (5, thumb),
            (10, thumb2, None, 5),  # set quality
            (5, self.shot3_file_path, '320x240'),  # set size
        ])
        self.assertTrue(os.path.exists(thumb))
        self.assertTrue(os.path.exists(thumb2))
        self.assertTrue(os.path.exists(self.shot3_file_path))

    def test_formats(self):
        self.assertRaisesSpecific(ValueError,
                                  formats.BaseFormat().parse_options, {})
        self.assertEqual(['-f', 'ogg'],
                         formats.OggFormat().parse_options({'format': 'ogg'}))
        self.assertEqual(['-f', 'avi'],
                         formats.AviFormat().parse_options({'format': 'avi'}))
        self.assertEqual(['-f', 'matroska'],
                         formats.MkvFormat().parse_options({'format': 'mkv'}))
        self.assertEqual(['-f', 'webm'],
                         formats.WebmFormat().parse_options({'format': 'webm'}))
        self.assertEqual(['-f', 'flv'],
                         formats.FlvFormat().parse_options({'format': 'flv'}))
        self.assertEqual(['-f', 'mov'],
                         formats.MovFormat().parse_options({'format': 'mov'}))
        self.assertEqual(['-f', 'mp4'],
                         formats.Mp4Format().parse_options({'format': 'mp4'}))
        self.assertEqual(['-f', 'mpegts'],
                         formats.MpegFormat().parse_options({'format': 'mpg'}))
        self.assertEqual(['-f', 'mp3'],
                         formats.Mp3Format().parse_options({'format': 'mp3'}))
        self.assertEqual(['-f', 'msmpeg4'],
                         formats.WmvFormat().parse_options({'format': 'wmv'}))

    def test_codecs(self):
        c = codecs.BaseCodec()
        self.assertRaisesSpecific(ValueError, c.parse_options, {})

        c.encoder_options = {'foo': int, 'bar': bool}
        self.assertEqual(
            {}, c.safe_options({'baz': 1, 'quux': 1, 'foo': 'w00t'}))
        self.assertEqual(
            {'foo': 42, 'bar': False}, c.safe_options({'foo': '42', 'bar': 0}))

        c = codecs.AudioCodec()
        c.codec_name = 'doctest'
        c.ffmpeg_codec_name = 'doctest'

        self.assertEqual(['-codec:a', 'doctest'], c.parse_options(
            {'codec': 'doctest', 'channels': 0, 'bitrate': 0, 'samplerate': 0}))

        self.assertEqual(
            ['-codec:a', 'doctest', '-ac', '1', '-b:a', '64k', '-ar', '44100'],
            c.parse_options({'codec': 'doctest', 'channels': '1', 'bitrate': '64', 'samplerate': '44100'}))

        c = codecs.VideoCodec()
        c.codec_name = 'doctest'
        c.ffmpeg_codec_name = 'doctest'

        self.assertEqual(['-codec:v', 'doctest', '-pix_fmt', 'yuv420p'], c.parse_options(
            {'codec': 'doctest', 'fps': 0, 'bitrate': 0, 'width': 0, 'height': '480'}))

        self.assertEqual(
            ['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-r', '25.0', '-b:v',
                '300k', '-s', '320x240', '-aspect', '320:240'],
            c.parse_options({'codec': 'doctest', 'fps': '25', 'bitrate': '300', 'width': 320, 'height': 240}))

        self.assertEqual(
            ['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '384x240',
                '-aspect', '320:240', '-vf', 'crop=320:240:32:0'],
            c.parse_options({'codec': 'doctest', 'src_width': 640, 'src_height': 400, 'mode': 'crop', 'width': 320, 'height': 240}))

        self.assertEqual(
            ['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '320x240', '-aspect',
                '320:200', '-vf', 'crop=320:200:0:20'],
            c.parse_options({'codec': 'doctest', 'src_width': 640, 'src_height': 480, 'mode': 'crop', 'width': 320, 'height': 200}))

        self.assertEqual(
            ['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '320x200',
                '-aspect', '320:240', '-vf', 'pad=320:240:0:20'],
            c.parse_options({'codec': 'doctest', 'src_width': 640, 'src_height': 400, 'mode': 'pad', 'width': 320, 'height': 240}))

        self.assertEqual(
            ['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '266x200',
                '-aspect', '320:200', '-vf', 'pad=320:200:27:0'],
            c.parse_options({'codec': 'doctest', 'src_width': 640, 'src_height': 480, 'mode': 'pad', 'width': 320, 'height': 200}))

        self.assertEqual(['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '320x240'], c.parse_options(
            {'codec': 'doctest', 'src_width': 640, 'src_height': 480, 'width': 320}))

        self.assertEqual(['-codec:v', 'doctest', '-pix_fmt', 'yuv420p', '-s', '320x240'], c.parse_options(
            {'codec': 'doctest', 'src_width': 640, 'src_height': 480, 'height': 240}))

        self.assertEqual(['-codec:a', 'aac', '-strict', 'experimental'],
                         codecs.AacCodec().parse_options({'codec': 'aac'}))
        self.assertEqual(
            ['-codec:a', 'ac3'], codecs.Ac3Codec().parse_options({'codec': 'ac3'}))
        self.assertEqual(
            ['-codec:a', 'copy'], codecs.AudioCopyCodec().parse_options({'codec': 'copy'}))
        self.assertEqual(
            ['-an'], codecs.AudioNullCodec().parse_options({'codec': None}))
        self.assertEqual(
            ['-scodec', 'dvbsub'], codecs.DVBSub().parse_options({'codec': 'dvbsub'}))
        self.assertEqual(
            ['-scodec', 'dvdsub'], codecs.DVDSub().parse_options({'codec': 'dvdsub'}))
        self.assertEqual(
            ['-codec:v', 'mpeg4', '-pix_fmt', 'yuv420p'], codecs.DivxCodec().parse_options({'codec': 'divx'}))
        self.assertEqual(
            ['-codec:a', 'dts'], codecs.DtsCodec().parse_options({'codec': 'dts'}))
        self.assertEqual(['-codec:a', 'libfdk_aac'],
                         codecs.FdkAacCodec().parse_options({'codec': 'libfdk_aac'}))
        self.assertEqual(
            ['-codec:a', 'flac'], codecs.FlacCodec().parse_options({'codec': 'flac'}))
        self.assertEqual(
            ['-codec:v', 'flv', '-pix_fmt', 'yuv420p'], codecs.FlvCodec().parse_options({'codec': 'flv'}))
        self.assertEqual(
            ['-codec:v', 'h263', '-pix_fmt', 'yuv420p'], codecs.H263Codec().parse_options({'codec': 'h263'}))
        self.assertEqual(
            ['-codec:v', 'libx264', '-pix_fmt', 'yuv420p'], codecs.H264Codec().parse_options({'codec': 'h264'}))
        self.assertEqual(
            ['-scodec', 'mov_text'], codecs.MOVTextCodec().parse_options({'codec': 'mov_text'}))
        self.assertEqual(
            ['-codec:a', 'mp2'], codecs.Mp2Codec().parse_options({'codec': 'mp2'}))
        self.assertEqual(['-codec:a', 'libmp3lame'],
                         codecs.Mp3Codec().parse_options({'codec': 'mp3'}))
        self.assertEqual(['-codec:v', 'mpeg1video', '-pix_fmt', 'yuv420p'],
                         codecs.Mpeg1Codec().parse_options({'codec': 'mpeg1'}))
        self.assertEqual(['-codec:v', 'mpeg2video', '-pix_fmt', 'yuv420p'],
                         codecs.Mpeg2Codec().parse_options({'codec': 'mpeg2'}))
        self.assertEqual(
            ['-scodec', 'ass'], codecs.SSA().parse_options({'codec': 'ass'}))
        self.assertEqual(
            ['-scodec', 'subrip'], codecs.SubRip().parse_options({'codec': 'subrip'}))
        self.assertEqual(
            ['-scodec', 'copy'], codecs.SubtitleCopyCodec().parse_options({'codec': 'copy'}))
        self.assertEqual(
            ['-sn'], codecs.SubtitleNullCodec().parse_options({'codec': None}))
        self.assertEqual(['-codec:v', 'libtheora', '-pix_fmt', 'yuv420p'],
                         codecs.TheoraCodec().parse_options({'codec': 'theora'}))
        self.assertEqual(
            ['-codec:v', 'copy'], codecs.VideoCopyCodec().parse_options({'codec': 'copy'}))
        self.assertEqual(
            ['-vn'], codecs.VideoNullCodec().parse_options({'codec': None}))
        self.assertEqual(['-codec:a', 'libvorbis'],
                         codecs.VorbisCodec().parse_options({'codec': 'vorbis'}))
        self.assertEqual(
            ['-codec:v', 'libvpx', '-pix_fmt', 'yuv420p'], codecs.Vp8Codec().parse_options({'codec': 'vp8'}))
        self.assertEqual(
            ['-codec:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p'], codecs.Vp9Codec().parse_options({'codec': 'vp9'}))
        self.assertEqual(
            ['-codec:a', 'wmav2'], codecs.WmaCodec().parse_options({'codec': 'wma'}))
        self.assertEqual(
            ['-codec:v', 'msmpeg4', '-pix_fmt', 'yuv420p'], codecs.WmvCodec().parse_options({'codec': 'wmv'}))

    def test_converter(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

        self.assertRaisesSpecific(ConverterError, c.parse_options, None)
        self.assertRaisesSpecific(ConverterError, c.parse_options, {})
        self.assertRaisesSpecific(
            ConverterError, c.parse_options, {'format': 'foo'})

        self.assertRaisesSpecific(
            ConverterError, c.parse_options, {'format': 'ogg'})
        self.assertRaisesSpecific(
            ConverterError, c.parse_options, {'format': 'ogg', 'video': 'whatever'})
        self.assertRaisesSpecific(
            ConverterError, c.parse_options, {'format': 'ogg', 'audio': {}})
        self.assertRaisesSpecific(
            ConverterError, c.parse_options, {'format': 'ogg', 'audio': {'codec': 'bogus'}})

        self.assertEqual(
            ['-an', '-codec:v', 'libtheora', '-pix_fmt', 'yuv420p', '-r', '25.0', '-sn', '-f', 'ogg'],
            c.parse_options({'format': 'ogg', 'video': {'codec': 'theora', 'fps': 25}}))
        self.assertEqual(
            ['-codec:a', 'copy', '-codec:v', 'copy', '-sn', '-f', 'ogg'],
            c.parse_options({'format': 'ogg', 'audio': {'codec': 'copy'}, 'video': {'codec': 'copy'}, 'subtitle': {'codec': None}}))

        info = c.probe('test1.ogg')
        self.assertEqual('theora', info.video.codec)
        self.assertEqual(720, info.video.video_width)
        self.assertEqual(400, info.video.video_height)

        f = self.shot_file_path

        self.ensure_notexist(f)
        c.thumbnail('test1.ogg', 10, f)
        self.assertTrue(os.path.exists(f))
        os.unlink(f)
        conv = c.convert('test1.ogg', self.video_file_path, {
            'format': 'ogg',
            'video': {
                'codec': 'theora',
                'width': 320,
                'height': 240,
                'fps': 15,
                'bitrate': 300,
                'ffmpeg_skin_opts': '-i logo.png -filter_complex [1]scale=151:138[wm];[0][wm]overlay=10:10'
            },
            'audio': {
                'codec': 'vorbis',
                'channels': 1,
                'bitrate': 32
            }
        })

        self.assertTrue(verify_progress(conv))

        conv = c.convert('test.aac', self.audio_file_path, {
            'format': 'mp3',
            'audio': {'codec': 'mp3', 'channels': 1, 'bitrate': 32}
        })

        self.assertTrue(verify_progress(conv))

    def test_converter_2pass(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        self.video_file_path = 'xx.ogg'
        options = {
            'format': 'ogg',
            'audio': {
                'codec': 'vorbis',
                'samplerate': 11025,
                'channels': 1,
                'bitrate': 16
            },
            'video': {
                'codec': 'theora',
                'bitrate': 128,
                'width': 360,
                'height': 200,
                'fps': 15
            }
        }
        options_repr = repr(options)
        conv = c.convert(
            'test1.ogg', self.video_file_path, options, twopass=True)

        verify_progress(conv)

        # Convert should not change options dict
        self.assertEqual(options_repr, repr(options))

        self._assert_converted_video_file()

    def test_converter_vp8_codec(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        conv = c.convert('test1.ogg', self.video_file_path, {
            'format': 'webm',
            'video': {
                'codec': 'vp8',
                'width': 160,
                'height': 120,
                'fps': 15,
                'bitrate': 300
            },
            'audio': {
                'codec': 'vorbis',
                'channels': 1,
                'bitrate': 32
            }
        })

        self.assertTrue(verify_progress(conv))

    def test_converter_vp9_codec(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        conv = c.convert('test1.ogg', self.video_file_path, {
            'format': 'webm',
            'video': {
                'codec': 'vp9',
                'width': 160,
                'height': 120,
                'fps': 15,
                'bitrate': 300
            },
            'audio': {
                'codec': 'vorbis',
                'channels': 1,
                'bitrate': 32
            }
        })

        self.assertTrue(verify_progress(conv))

    def test_segmenter_audio_track(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        input_file = 'test1.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'test.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 2000,
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

        input_file = self.video_file_path[0]
        work_dir = os.path.join(self.temp_dir)
        self.video_file_path = [os.path.join(self.temp_dir, 'test.m3u8')]
        output_dir_names = [os.path.join(self.temp_dir, 'test')]
        conv = c.segment(input_file, work_dir, self.video_file_path, output_dir_names, [{
            'segment_time': 6, 'maps': ['0:a:0']
        }])

        self.assertTrue(verify_progress(conv))

    def test_segmenter_video_track(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        input_file = 'test1.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'test.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 2000,
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

        input_file = self.video_file_path[0]
        work_dir = os.path.join(self.temp_dir)
        self.video_file_path = [os.path.join(self.temp_dir, 'test.m3u8')]
        output_dir_names = [os.path.join(self.temp_dir, 'test')]
        conv = c.segment(input_file, work_dir, self.video_file_path, output_dir_names, [{
            'segment_time': 1, 'maps': ['0:v:0']
        }])

        self.assertTrue(verify_progress(conv))

    def test_branding_input(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        input_file = 'test1.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'preroll.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 2000,
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

        preroll = os.path.join(self.temp_dir, 'preroll.mp4')
        input_file = preroll
        self.video_file_path = [os.path.join(self.temp_dir, 'test.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'maps': ['[outv]', '[outa]'],
            'map_chapters': '-1',
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 1000,
                'ffmpeg_skin_opts': '-i logo.png -i %s -i %s -filter_complex [1]scale=192:175[logo];[0:v:0][logo]overlay=10:10[mainv];[2:v:0]scale=720:400:force_original_aspect_ratio=decrease,pad=720:400:(ow-iw)/2:(oh-ih)/2,setdar=16/9[introv];[mainv]scale=720:400[mainv];[3:v:0]scale=720:400:force_original_aspect_ratio=decrease,pad=720:400:(ow-iw)/2:(oh-ih)/2,setdar=16/9[outrov];[introv][2:a:0][mainv][0:a:0][outrov][3:a:0]concat=n=3:v=1:a=1[outv][outa] -metadata comment=2dd18fa85d60a236e0ebe566bf14dd8d' % (preroll, preroll),
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

    def test_branding_no_audio_input(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        input_file = 'test1_no_audio.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'test1_no_audio.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 2000,
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

        input_file = 'test1.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'preroll.mp4')]
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 2000,
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

        input_file = os.path.join(self.temp_dir, 'test1_no_audio.mp4')
        self.video_file_path = [os.path.join(self.temp_dir, 'test.mp4')]
        preroll = os.path.join(self.temp_dir, 'preroll.mp4')
        conv = c.convert(input_file, self.video_file_path, [{
            'format': 'mp4',
            'faststart': True,
            'maps': ['[outv]', '[outa]'],
            'map_chapters': '-1',
            'video': {
                'codec': 'h264',
                'pix_fmt': 'yuv420p',
                'profile': 'main',
                'level': '3.1',
                'preset': 'faster',
                'width': 1280,
                'height': 720,
                'fps': 30,
                'keyframe_interval': 30,
                'max_bitrate': 1000,
                'ffmpeg_skin_opts': '-i logo.png -i %s -f lavfi -i aevalsrc=0:d=2 -i %s -filter_complex [1]scale=192:175[logo];[0:v:0][logo]overlay=10:10[mainv];[2:v:0]scale=720:400:force_original_aspect_ratio=decrease,pad=720:400:(ow-iw)/2:(oh-ih)/2,setdar=16/9[introv];[mainv]scale=720:400[mainv];[4:v:0]scale=720:400:force_original_aspect_ratio=decrease,pad=720:400:(ow-iw)/2:(oh-ih)/2,setdar=16/9[outrov];[introv][2:a:0][mainv][3:a:0][outrov][4:a:0]concat=n=3:v=1:a=1[outv][outa] -shortest -t 98 -metadata comment=2dd18fa85d60a236e0ebe566bf14dd8d' % (preroll, preroll),
                'quality': 19
            },
            'audio': {
                'codec': 'aac',
                'channels': 2,
                'samplerate': 44100,
                'quality': 3
            }
        }])

        self.assertTrue(verify_progress(conv))

    def test_converter_parallelize(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
        input_file = 'test1.ogg'
        self.video_file_path = [os.path.join(self.temp_dir, 'result1.ogg'), os.path.join(self.temp_dir, 'result2.ogg')]
        conv = c.convert(input_file, self.video_file_path, [
            {
                'format': 'ogg',
                'maps': [0, '-0:d', '-0:s'],
                'map_chapters': '-1',
                'video': {
                    'codec': 'theora',
                    'width': 1280,
                    'height': 720,
                    'fps': 30,
                    'keyframe_interval': 30,
                    'bitrate': 300
                },
                'audio': {
                    'codec': 'vorbis',
                    'channels': 1,
                    'samplerate': 44100,
                    'bitrate': 32
                }
            },
            {
                'format': 'ogg',
                'maps': [0, '-0:d', '-0:s'],
                'map_chapters': '-1',
                'video': {
                    'codec': 'theora',
                    'width': 352,
                    'height': 240,
                    'fps': 30,
                    'keyframe_interval': 30,
                    'bitrate': 300
                },
                'audio': {
                    'codec': 'vorbis',
                    'channels': 1,
                    'samplerate': 44100,
                    'bitrate': 32
                }
            }
        ])

        self.assertTrue(verify_progress(conv))

    def test_probe_audio_poster(self):
        c = Converter(ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

        info = c.probe('test.mp3', posters_as_video=True)
        self.assertNotEqual(None, info.video)
        self.assertEqual(info.video.attached_pic, 1)

        info = c.probe('test.mp3', posters_as_video=False)
        self.assertEqual(None, info.video)
        self.assertEqual(len(info.posters), 1)
        poster = info.posters[0]
        self.assertEqual(poster.type, 'video')
        self.assertEqual(poster.codec, 'png')
        self.assertEqual(poster.video_width, 32)
        self.assertEqual(poster.video_height, 32)
        self.assertEqual(poster.attached_pic, 1)


if __name__ == '__main__':
    unittest.main()
