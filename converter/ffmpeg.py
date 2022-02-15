#!/usr/bin/env python

from itertools import count
from subprocess import Popen, PIPE
import locale
import logging
import os
import re
import signal

logger = logging.getLogger(__name__)

console_encoding = locale.getdefaultlocale()[1] or 'UTF-8'


class ArgumentError(Exception):
    pass


class FFMpegError(Exception):

    def __init__(self, message, cmd=None, details=None, pid=None):
        """
        @param    message: Error message.
        @type     message: C{str}

        @param    cmd: Full command string used to spawn ffmpeg.
        @type     cmd: C{str}

        @param    details: Optional error details.
        @type     details: C{str}
        """
        super(FFMpegError, self).__init__(message)

        self.cmd = cmd
        self.details = details
        self.message = message
        self.pid = pid

    def __repr__(self):
        return ('<%s error="%s", details="%s", pid=%s, cmd="%s">' %
                (self.__class__.__name__, self.message, self.details, self.pid, self.cmd))

    def __str__(self):
        return self.__repr__()


class FFMpegConvertError(FFMpegError):
    pass


class MediaFormatInfo(object):

    """
    Describes the media container format. The attributes are:
      * format - format (short) name (eg. "ogg")
      * fullname - format full (descriptive) name
      * bitrate - total bitrate (bps)
      * duration - media duration in seconds
      * filesize - file size
    """

    def __init__(self):
        self.format = None
        self.fullname = None
        self.bitrate = None
        self.duration = None
        self.filesize = None
        self.metadata = {}

    def parse_ffprobe(self, key, val):
        """
        Parse raw ffprobe output (key=value).
        """
        if key == 'format_name':
            self.format = val
        elif key == 'format_long_name':
            self.fullname = val
        elif key == 'bit_rate':
            self.bitrate = MediaStreamInfo.parse_float(val, None)
        elif key == 'duration':
            self.duration = MediaStreamInfo.parse_float(val, None)
        elif key == 'size':
            self.size = MediaStreamInfo.parse_float(val, None)
        if key.startswith('TAG:'):
            key = key.split('TAG:')[1]
            value = val
            self.metadata[key] = value

    def __repr__(self):
        d = ''
        metadata_str = ['%s=%s' % (key, value) for key, value
                        in self.metadata.items()]
        metadata_str = ', '.join(metadata_str)

        if self.duration is not None:
            d += 'duration=%s, ' % self.duration
        if self.format is not None:
            d += 'format=%s, ' % self.format
        if metadata_str is not None:
            d += "%s" % metadata_str
        value = 'MediaFormatInfo(%s)' % d
        return value


class MediaStreamInfo(object):

    """
    Describes one stream inside a media file. The general
    attributes are:
      * index - stream index inside the container (0-based)
      * type - stream type, either 'audio' or 'video'
      * codec - codec (short) name (e.g "vorbis", "theora")
      * codec_desc - codec full (descriptive) name
      * duration - stream duration in seconds
      * metadata - optional metadata associated with a video or audio stream
      * bitrate - stream bitrate in bytes/second
      * attached_pic - (0, 1 or None) is stream a poster image? (e.g. in mp3)
    Video-specific attributes are:
      * video_width - width of video in pixels
      * video_height - height of video in pixels
      * video_fps - average frames per second
      * video_pixel_format - pixel format
    Audio-specific attributes are:
      * audio_channels - the number of channels in the stream
      * audio_samplerate - sample rate (Hz)
    """

    def __init__(self):
        self.index = None
        self.type = None
        self.codec = None
        self.codec_desc = None
        self.duration = None
        self.bitrate = None
        self.video_width = None
        self.video_height = None
        self.video_fps = None
        self.video_pixel_format = None
        self.video_sample_aspect_ratio = None
        self.video_display_aspect_ratio = None
        self.audio_channels = None
        self.audio_samplerate = None
        self.start_time = None
        self.attached_pic = None
        self.sub_forced = None
        self.sub_default = None
        self.metadata = {}

    @staticmethod
    def parse_float(val, default=0.0):
        try:
            return float(val)
        except Exception:
            return default

    @staticmethod
    def parse_int(val, default=0):
        try:
            return int(val)
        except Exception:
            return default

    def parse_ffprobe(self, key, val):
        """
        Parse raw ffprobe output (key=value).
        """
        if val == 'N/A':
            return

        if key == 'index':
            self.index = self.parse_int(val)
        elif key == 'codec_type':
            self.type = val
        elif key == 'codec_name':
            self.codec = val
        elif key == 'codec_long_name':
            self.codec_desc = val
        elif key == 'duration':
            self.duration = self.parse_float(val)
        elif key == 'bit_rate':
            self.bitrate = self.parse_int(val, None)
        elif key == 'width':
            self.video_width = self.parse_int(val)
        elif key == 'height':
            self.video_height = self.parse_int(val)
        elif key == 'pix_fmt':
            self.video_pixel_format = val
        elif key == 'channels':
            self.audio_channels = self.parse_int(val)
        elif key == 'sample_rate':
            self.audio_samplerate = self.parse_float(val)
        elif key == 'start_time':
            self.start_time = self.parse_float(val)
        elif key == 'rotation':
            self.metadata['rotate'] = self.parse_int(val)
            if self.metadata['rotate'] < 0:
                self.metadata['rotate'] += 360
        elif key == 'DISPOSITION:attached_pic':
            self.attached_pic = self.parse_int(val)
        if key.startswith('TAG:'):
            key = key.split('TAG:')[1]
            value = val
            self.metadata[key] = value

        if self.type == 'audio':
            if key == 'avg_frame_rate':
                if val == '1000/1':
                    # 1000/1 is reported by ffprobe when frame rate cannot be found in some cases
                    pass
                elif '/' in val:
                    n, d = val.split('/')
                    n = self.parse_float(n)
                    d = self.parse_float(d)
                    if n > 0.0 and d > 0.0:
                        self.video_fps = float(n) / float(d)
                elif '.' in val:
                    self.video_fps = self.parse_float(val)

        if self.type == 'video':
            if key == 'r_frame_rate':
                if val == '1000/1':
                    # 1000/1 is reported by ffprobe when frame rate cannot be found in some cases
                    pass
                elif '/' in val:
                    n, d = val.split('/')
                    n = self.parse_float(n)
                    d = self.parse_float(d)
                    if n > 0.0 and d > 0.0:
                        self.video_fps = float(n) / float(d)
                elif '.' in val:
                    self.video_fps = self.parse_float(val)
            elif key == 'sample_aspect_ratio':
                n, d = val.split(':')
                n = self.parse_float(n)
                d = self.parse_float(d)
                self.video_sample_aspect_ratio = float(n) / float(d)
            elif key == 'display_aspect_ratio':
                n, d = val.split(':')
                n = self.parse_float(n)
                d = self.parse_float(d)
                if d > 0.0:
                    self.video_display_aspect_ratio = float(n) / float(d)
                else:
                    logger.warning('Could not determinate video ratio, n : %s d : %s' % (n, d))
                    self.video_display_aspect_ratio = 16.0 / 9.0

        if self.type == 'subtitle':
            if key == 'disposition:forced':
                self.sub_forced = self.parse_int(val)
            if key == 'disposition:default':
                self.sub_default = self.parse_int(val)

    def __repr__(self):
        d = ''
        metadata_str = ['%s=%s' % (key, value) for key, value
                        in self.metadata.items()]
        metadata_str = ', '.join(metadata_str)
        if self.type == 'audio':
            d = 'type=%s, codec=%s, channels=%d, rate=%.0f, start_time=%f' % (
                self.type, self.codec, self.audio_channels,
                self.audio_samplerate, self.start_time or 0)
        elif self.type == 'video':
            d = 'type=%s, codec=%s, width=%d, height=%d, fps=%.1f, start_time=%f' % (
                self.type, self.codec, self.video_width, self.video_height,
                self.video_fps, self.start_time or 0)
        elif self.type == 'subtitle':
            d = 'type=%s, codec=%s' % (self.type, self.codec)
        if self.bitrate is not None:
            d += ', bitrate=%d' % self.bitrate

        if self.metadata:
            value = 'MediaStreamInfo(%s, %s)' % (d, metadata_str)
        else:
            value = 'MediaStreamInfo(%s)' % d

        return value


class MediaInfo(object):

    """
    Information about media object, as parsed by ffprobe.
    The attributes are:
      * format - a MediaFormatInfo object
      * streams - a list of MediaStreamInfo objects
    """

    def __init__(self, posters_as_video=True):
        """
        :param posters_as_video: Take poster images (mainly for audio files) as
            A video stream, defaults to True
        """
        self.format = MediaFormatInfo()
        self.posters_as_video = posters_as_video
        self.streams = []

    def parse_ffprobe(self, raw):
        """
        Parse raw ffprobe output.
        """
        in_format = False
        current_stream = None

        for line in raw.split('\n'):
            line = line.strip()
            if line == '':
                continue
            elif line == '[STREAM]':
                current_stream = MediaStreamInfo()
            elif line == '[/STREAM]':
                if current_stream.type:
                    self.streams.append(current_stream)
                current_stream = None
            elif line == '[FORMAT]':
                in_format = True
            elif line == '[/FORMAT]':
                in_format = False
            elif '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
                if current_stream:
                    current_stream.parse_ffprobe(k, v)
                elif in_format:
                    self.format.parse_ffprobe(k, v)

    def __repr__(self):
        return 'MediaInfo(format=%s, streams=%s)' % (repr(self.format),
                                                     repr(self.streams))

    @property
    def video(self):
        """
        First video stream, or None if there are no video streams.
        """
        for s in self.streams:
            if s.type == 'video' and (self.posters_as_video
                                      or not s.attached_pic):
                return s
        return None

    @property
    def posters(self):
        return [s for s in self.streams if s.attached_pic]

    @property
    def audio(self):
        """
        First audio stream, or None if there are no audio streams.
        """
        for s in self.streams:
            if s.type == 'audio':
                return s
        return None


class FFMpeg(object):

    """
    FFMPeg wrapper object, takes care of calling the ffmpeg binaries,
    passing options and parsing the output.

    >>> f = FFMpeg()
    """
    DEFAULT_JPEG_QUALITY = 4

    def __init__(self, ffmpeg_path=None, ffprobe_path=None):
        """
        Initialize a new FFMpeg wrapper object. Optional parameters specify
        the paths to ffmpeg and ffprobe utilities.
        """

        def which(name):
            path = os.environ.get('PATH', os.defpath)
            for d in path.split(':'):
                fpath = os.path.join(d, name)
                if os.path.exists(fpath) and os.access(fpath, os.X_OK):
                    return fpath
            return None

        if ffmpeg_path is None:
            ffmpeg_path = 'ffmpeg'

        if ffprobe_path is None:
            ffprobe_path = 'ffprobe'

        if '/' not in ffmpeg_path:
            ffmpeg_path = which(ffmpeg_path) or ffmpeg_path
        if '/' not in ffprobe_path:
            ffprobe_path = which(ffprobe_path) or ffprobe_path

        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        if not os.path.exists(self.ffmpeg_path):
            raise FFMpegError("ffmpeg binary not found: " + self.ffmpeg_path)

        if not os.path.exists(self.ffprobe_path):
            raise FFMpegError("ffprobe binary not found: " + self.ffprobe_path)

    @staticmethod
    def _spawn(cmds, shell=False, stdin=PIPE, stdout=PIPE, stderr=PIPE):
        logger.debug('Spawning ffmpeg with command: ' + ' '.join(cmds))
        return Popen(cmds, shell=shell, stdin=stdin, stdout=stdout,
                     stderr=stderr, close_fds=True)

    def probe(self, uri, posters_as_video=True):
        """
        Examine the media file and determine its format and media streams.
        Returns the MediaInfo object, or None if the specified file is
        not a valid media file.

        >>> info = FFMpeg().probe('test1.ogg')
        >>> info.format
        'ogg'
        >>> info.duration
        33.00
        >>> info.video.codec
        'theora'
        >>> info.video.width
        720
        >>> info.video.height
        400
        >>> info.audio.codec
        'vorbis'
        >>> info.audio.channels
        2
        :param posters_as_video: Take poster images (mainly for audio files) as
            A video stream, defaults to True
        """

        info = MediaInfo(posters_as_video)

        p = self._spawn([self.ffprobe_path, '-hide_banner',
                         '-show_format', '-show_streams', '-show_error', uri])
        stdout_data, stderr_data = p.communicate()
        stdout_data = stdout_data.decode(console_encoding, 'replace')
        info.parse_ffprobe(stdout_data)

        if not info.format.format and len(info.streams) == 0:
            return None

        return info

    def convert(self, infile, outfiles, opts, timeout=10, preopts=None, skinopts=None):
        """
        Convert the source media (infile) according to specified options
        (a list of ffmpeg switches as strings) and save it to outfile.

        Convert returns a generator that needs to be iterated to drive the
        conversion process. The generator will periodically yield timecode
        of currently processed part of the file (ie. at which second in the
        content is the conversion process currently).

        The optional timeout argument specifies how long should the operation
        be blocked in case ffmpeg gets stuck and doesn't report back. See
        the documentation in Converter.convert() for more details about this
        option.

        >>> conv = FFMpeg().convert('test.ogg', '/tmp/output.mp3',
        ...    ['-acodec libmp3lame', '-vn'])
        >>> for timecode in conv:
        ...    pass  # can be used to inform the user about conversion progress

        """
        cmds = [self.ffmpeg_path, '-hide_banner']

        if not os.path.exists(infile):
            raise FFMpegError("Input file doesn't exist: " + infile)
        if preopts:
            for preopt in preopts:
                if preopt:
                    cmds.extend(preopts)
        cmds.extend(['-y', '-i', infile])
        index = 0
        for outputfile, outopts in zip(outfiles, opts):
            if skinopts and skinopts[index]:
                cmds.extend(skinopts[index])
            cmds.extend(['-max_muxing_queue_size', '99999'])
            cmds.extend(outopts)
            cmds.append(outputfile)
            index += 1
        try:
            p = self._spawn(cmds)
        except OSError as e:
            raise FFMpegError('Error while calling ffmpeg binary', details=e)

        if timeout:
            def on_sigvtalrm(*_):
                signal.signal(signal.SIGVTALRM, signal.SIG_DFL)
                if p.poll() is None:
                    p.kill()
                raise FFMpegError('timed out while waiting for ffmpeg')

            signal.signal(signal.SIGVTALRM, on_sigvtalrm)

        yielded = False
        buf = ''
        total_output = ''
        pat = re.compile(r'time=([0-9.:]+)')

        def get_timecode(out):
            tmp = pat.findall(out)
            if len(tmp) == 1:
                timespec = tmp[0]
                if ':' in timespec:
                    timecode = 0
                    for part in timespec.split(':'):
                        timecode = 60 * timecode + float(part)
                else:
                    timecode = float(tmp[0])
                return timecode
            return None

        while True:
            if timeout:
                signal.setitimer(signal.ITIMER_VIRTUAL, timeout)

            ret = p.stderr.read(10)

            if timeout:
                signal.setitimer(signal.ITIMER_VIRTUAL, 0)

            if not ret:
                break

            ret = ret.decode(console_encoding, 'replace')
            total_output += ret
            buf += ret
            if '\r' in buf:
                line, buf = buf.split('\r', 1)
                timecode = get_timecode(line)
                if timecode is not None:
                    yielded = True
                    yield timecode
        if not yielded:
            # There may have been a single time, check it
            timecode = get_timecode(total_output)
            if timecode is not None:
                yielded = True
                yield timecode

        if timeout:
            signal.signal(signal.SIGALRM, signal.SIG_DFL)

        p.communicate()  # wait for process to exit

        if total_output == '':
            raise FFMpegError('Error while calling ffmpeg binary, no output.')

        cmd = ' '.join(cmds)
        if '\n' in total_output:
            line = total_output.split('\n')[-2]

            if line.startswith('Received signal'):
                # Received signal 15: terminating.
                raise FFMpegConvertError(
                    line.split(':')[0], cmd, total_output, pid=p.pid)
            if line.startswith(infile + ': '):
                err = line[len(infile) + 2:]
                raise FFMpegConvertError(
                    'Encoding error: %s' % err, cmd, total_output, pid=p.pid)
            if line.startswith('Error while '):
                raise FFMpegConvertError(
                    'Encoding error: %s' % line, cmd, total_output, pid=p.pid)
            if not yielded:
                raise FFMpegConvertError(
                    'Unknown ffmpeg error', cmd, total_output, pid=p.pid)
        if p.returncode != 0:
            raise FFMpegConvertError(
                'Exited with code %d' % p.returncode, cmd, total_output, pid=p.pid)

    def thumbnail(self, uri, time, outfile,
                  size=None, quality=DEFAULT_JPEG_QUALITY):
        """
        Create a thumbnal of media file, and store it to outfile
        @param uri: file path or url
        @param time: time point (in seconds) (float or int)
        @param size: Size, if specified, is WxH of the desired thumbnail.
            If not specified, the video resolution is used.
        @param quality: quality of jpeg file in range 2(best)-31(worst)
            recommended range: 2-6

        >>> FFMpeg().thumbnail('test1.ogg', 5, '/tmp/shot.png', '320x240')
        """
        return self.thumbnails(uri, [(time, outfile, size, quality)])

    def thumbnails(self, uri, option_list, output_seeking=False):
        """
        Create one or more thumbnails of video.
        @param uri: file path or url
        @param option_list: a list of tuples like:
            (time, outfile, size=None, quality=DEFAULT_JPEG_QUALITY)
            see documentation of `converter.FFMpeg.thumbnail()` for details.
        @param output_seeking: a boolean whether the seeking should be done
            on the output (slow but doesn't reset the timestamps) or on the
            input

        >>> FFMpeg().thumbnails('test1.ogg', [(5, '/tmp/shot.png', '320x240'),
        >>>                                   (10, '/tmp/shot2.png', None, 5)])
        """
        if '://' not in uri and not os.path.exists(uri):
            raise IOError('No such file: ' + uri)

        output_seeking = len(option_list) > 1 or output_seeking

        cmds = [self.ffmpeg_path, '-hide_banner']
        if '://' in uri:
            # add request timeout (2 minutes in microseconds)
            cmds.extend(['-timeout', '120000000'])
        if not output_seeking:
            cmds.extend(['-ss', str(option_list[0][0])])
        cmds.extend(['-i', uri, '-y', '-an'])
        for thumb in option_list:
            if len(thumb) > 2 and thumb[2]:
                cmds.extend(['-s', str(thumb[2])])
            cmds.extend([
                '-f', 'image2', '-vframes', '1',
                '-q:v', str(
                    FFMpeg.DEFAULT_JPEG_QUALITY if len(
                        thumb) < 4 else str(thumb[3])),
            ])
            if output_seeking:
                cmds.extend(['-ss', str(thumb[0]), thumb[1]])
            else:
                cmds.append(thumb[1])

        p = self._spawn(cmds)
        _, stderr_data = p.communicate()
        if stderr_data == '':
            raise FFMpegError('Error while calling ffmpeg binary')
        stderr_data = stderr_data.decode(console_encoding, 'replace')
        if any(not os.path.exists(option[1]) for option in option_list):
            raise FFMpegError('Error creating thumbnail.', details=stderr_data)

    def mix(
        self, inputs, inputs_maps, output,
        stream_metadata_tags=None, copy_metadata_tags=False, duration=None
    ):

        if len(inputs) != len(inputs_maps):
            raise ArgumentError(
                'inputs_maps must have the same length then inputs')

        stream_metadata_tags = stream_metadata_tags or []

        command = [self.ffmpeg_path, '-hide_banner', '-y', '-nostdin']
        command_options = ['-codec', 'copy']
        if copy_metadata_tags:
            command_options.extend(['-movflags', 'use_metadata_tags'])
        if duration:
            command_options.extend(['-t', str(round(duration, 3))])

        maps_commands = []
        input_commands = []

        zip_iterator = zip(count(), inputs, inputs_maps)

        for file_index, input_file, input_mappings in zip_iterator:
            input_commands.extend(['-i', input_file])
            for input_maps in input_mappings:
                maps_commands.extend([
                    '-map',
                    '%i:%s' % (file_index, input_maps)
                ])

        command.extend(input_commands + maps_commands + command_options)

        # Warning! `metadata_tags` must have the same size then
        # the output streams. Otherwise, ffmpeg process will crash
        # as we can't check this earlier.
        metadata_tags = []
        for stream_index, stream_metadatas in enumerate(stream_metadata_tags):
            for meta_name, meta_value in stream_metadatas:
                metadata_tags.extend([
                    '-metadata:s:%i' % stream_index,
                    '"%s=%s"' % (meta_name, meta_value)
                ])

        command.extend(metadata_tags + [output])

        p = self._spawn(command)
        stdout_data, stderr_data = p.communicate()
        if p.returncode != 0:
            raise FFMpegError(
                'Error while calling ffmpeg binary, retcode %i' % p.returncode,
                details=stderr_data.decode(console_encoding, 'replace'))
