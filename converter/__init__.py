#!/usr/bin/python

import errno
import logging
import os
import warnings
from converter.codecs import codec_lists
from converter.ffmpeg import FFMpeg
from converter.formats import format_list

logger = logging.getLogger(__name__)


class ConverterError(Exception):
    pass


class Converter(object):
    """
    Converter class, encapsulates formats and codecs.

    >>> c = Converter()
    """

    def __init__(self, ffmpeg_path=None, ffprobe_path=None):
        """Initialize a new Converter object."""
        self.ffmpeg = FFMpeg(
            ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)
        self.video_codecs = {}
        self.audio_codecs = {}
        self.subtitle_codecs = {}
        self.formats = {}

        for cls in codec_lists["audio"]:
            name = cls.codec_name
            self.audio_codecs[name] = cls

        for cls in codec_lists["video"]:
            name = cls.codec_name
            self.video_codecs[name] = cls

        for cls in codec_lists["subtitle"]:
            name = cls.codec_name
            self.subtitle_codecs[name] = cls

        for cls in format_list:
            name = cls.format_name
            self.formats[name] = cls

    def parse_options(self, opt, twopass=None):
        """Parse format/codec options and prepare raw ffmpeg option list."""
        if not isinstance(opt, dict):
            raise ConverterError('Invalid output specification')

        if 'format' not in opt:
            raise ConverterError('Format not specified')

        f = opt['format']
        if f not in self.formats:
            raise ConverterError('Requested unknown format: ' + str(f))

        format_options = self.formats[f]().parse_options(opt)
        if format_options is None:
            raise ConverterError('Unknown container format error')

        if 'audio' not in opt and 'video' not in opt:
            raise ConverterError('Neither audio nor video streams requested')

        # audio options
        if 'audio' not in opt or twopass == 1:
            opt_audio = {'codec': None}
        else:
            opt_audio = opt['audio']
            if not isinstance(opt_audio, dict) or 'codec' not in opt_audio:
                raise ConverterError('Invalid audio codec specification')

        c = opt_audio['codec']
        if c not in self.audio_codecs:
            raise ConverterError('Requested unknown audio codec ' + str(c))

        audio_options = self.audio_codecs[c]().parse_options(opt_audio)
        if audio_options is None:
            raise ConverterError('Unknown audio codec error')

        # video options
        if 'video' not in opt:
            opt_video = {'codec': None}
        else:
            opt_video = opt['video']
            if not isinstance(opt_video, dict) or 'codec' not in opt_video:
                raise ConverterError('Invalid video codec specification')

        c = opt_video['codec']
        if c not in self.video_codecs:
            raise ConverterError('Requested unknown video codec ' + str(c))

        video_options = self.video_codecs[c]().parse_options(opt_video)
        if video_options is None:
            raise ConverterError('Unknown video codec error')

        if 'subtitle' not in opt:
            opt_subtitle = {'codec': None}
        else:
            opt_subtitle = opt['subtitle']
            if not isinstance(opt_subtitle, dict) or 'codec' not in opt_subtitle:
                raise ConverterError('Invalid subtitle codec specification')

        c = opt_subtitle['codec']
        if c not in self.subtitle_codecs:
            raise ConverterError('Requested unknown subtitle codec ' + str(c))

        subtitle_options = self.subtitle_codecs[
            c]().parse_options(opt_subtitle)
        if subtitle_options is None:
            raise ConverterError('Unknown subtitle codec error')

        if 'map' in opt:
            opt.setdefault('maps', []).extends(['-map', str(opt['map'])])

        for input_map in opt.get('maps', []):
            format_options.extend(['-map', str(input_map)])

        if 'map_chapters' in opt:
            format_options.extend(['-map_chapters', str(opt['map_chapters'])])

        # aggregate all options
        optlist = audio_options + video_options + subtitle_options + \
            format_options

        if twopass == 1:
            optlist.extend(['-pass', '1'])
        elif twopass == 2:
            optlist.extend(['-pass', '2'])

        return optlist

    def convert(self, infile, outfiles, options, twopass=False, timeout=10):
        """
        Convert media file (infile) according to specified options, and save it to outfile. For two-pass encoding, specify the pass (1 or 2) in the twopass parameter.

        Options should be passed as a dictionary. The keys are:
            * format (mandatory, string) - container format; see
              formats.BaseFormat for list of supported formats
            * audio (optional, dict) - audio codec and options; see
              codecs.audio.AudioCodec for list of supported options
            * video (optional, dict) - video codec and options; see
              codecs.video.VideoCodec for list of supported options
            * map (optional, int) - can be used to map all content of stream 0

        Multiple audio/video streams are not supported. The output has to
        have at least an audio or a video stream (or both).

        Convert returns a generator that needs to be iterated to drive the
        conversion process. The generator will periodically yield timecode
        of currently processed part of the file (ie. at which second in the
        content is the conversion process currently).

        The optional timeout argument specifies how long should the operation
        be blocked in case ffmpeg gets stuck and doesn't report back. This
        doesn't limit the total conversion time, just the amount of time
        Converter will wait for each update from ffmpeg. As it's usually
        less than a second, the default of 10 is a reasonable default. To
        disable the timeout, set it to None. You may need to do this if
        using Converter in a threading environment, since the way the
        timeout is handled (using signals) has special restriction when
        using threads.

        >>> conv = Converter().convert('test1.ogg', '/tmp/output.mkv', {
        ...    'format': 'mkv',
        ...    'audio': { 'codec': 'aac' },
        ...    'video': { 'codec': 'h264' }
        ... })

        >>> for timecode in conv:
        ...   pass # can be used to inform the user about the progress
        """
        if isinstance(outfiles, str):
            outfiles = [outfiles]

        if isinstance(options, dict):
            options = [options]

        if len(outfiles) != len(options):
            raise ConverterError('Options are not provided for all the outputs')

        if not isinstance(options, list):
            raise ConverterError('Invalid options')

        if not os.path.exists(infile):
            raise ConverterError("Source file doesn't exist: " + infile)

        info = self.ffmpeg.probe(infile)
        if info is None:
            raise ConverterError("Can't get information about source file")

        if not info.video and not info.audio:
            raise ConverterError('Source file has no audio or video streams')

        skinopts = list()
        preopts = list()
        duration = info.format.duration
        for index in range(0, len(options)):
            if info.video and 'video' in options[index]:
                options[index] = options[index].copy()
                v = options[index]['video'] = options[index]['video'].copy()
                v['src_width'] = info.video.video_width
                v['src_height'] = info.video.video_height
                v['display_aspect_ratio'] = info.video.video_display_aspect_ratio
                v['sample_aspect_ratio'] = info.video.video_sample_aspect_ratio
                v['rotate'] = info.video.metadata.get('rotate') or info.video.metadata.get('ROTATE')
                preoptlist = options[index]['video'].get('ffmpeg_custom_launch_opts', '').split(' ')
                # Remove empty arguments (make crashes)
                preoptlist = [arg for arg in preoptlist if arg]
                preopts.append(preoptlist)
                skinoptlist = options[index]['video'].get('ffmpeg_skin_opts', '').split(' ')
                # Remove empty arguments (make crashes)
                next_arg_is_file = False
                newskinoptlist = list()
                for arg in skinoptlist:
                    if arg:
                        if arg == '-i':
                            next_arg_is_file = True
                        elif next_arg_is_file and 'aevalsrc' not in arg:
                            branded_info = self.ffmpeg.probe(arg)
                            duration += branded_info.format.duration or 0
                            next_arg_is_file = False
                        elif next_arg_is_file and 'aevalsrc' in arg:
                            next_arg_is_file = False
                        newskinoptlist.append(arg)
                skinoptlist = newskinoptlist
                skinopts.append(skinoptlist)
            if not info.format or not info.format.duration or not isinstance(info.format.duration, (float, int)) or info.format.duration < 0.01:
                raise ConverterError('Zero-length media')

        if twopass:
            optlist1 = []
            for output_options in options:
                optlist1.append(self.parse_options(output_options, 1))
            for timecode in self.ffmpeg.convert(infile, outfiles, optlist1,
                                                timeout=timeout, preopts=preopts, skinopts=skinopts):
                yield float(timecode) / duration

            optlist2 = []
            for output_options in options:
                optlist2.append(self.parse_options(output_options, 2))
            for timecode in self.ffmpeg.convert(infile, outfiles, optlist2,
                                                timeout=timeout, preopts=preopts, skinopts=skinopts):
                yield 0.5 + float(timecode) / duration
        else:
            optlist = []
            for output_options in options:
                optlist.append(self.parse_options(output_options, twopass))
            for timecode in self.ffmpeg.convert(infile, outfiles, optlist,
                                                timeout=timeout, preopts=preopts, skinopts=skinopts):
                yield float(timecode) / duration

    def segment(self, infile, working_directory, output_files, output_directories, options, timeout=10):
        """
        Segment the first video stream muxed with the first audio track
        """

        if isinstance(output_files, str):
            output_files = [output_files]

        if isinstance(output_directories, str):
            output_directories = [output_directories]

        if isinstance(options, str):
            options = [options]

        if len(output_files) != len(output_directories) != len(options):
            raise ConverterError('Input file or directories or options are not provided for all the outputs')

        outputs_options = list()
        outputs_ts_files = list()
        for index, output_file in enumerate(output_files):
            if not os.path.exists(infile):
                raise ConverterError("Source file doesn't exist: " + infile)

            info = self.ffmpeg.probe(infile)
            if info is None:
                raise ConverterError("Can't get information about source file")

            if not info.video and not info.audio:
                raise ConverterError('Source file has no audio or video streams')
            output_directory = output_directories[index]
            output_file = output_files[index]
            try:
                os.makedirs(os.path.join(working_directory, output_directory))
            except Exception as e:
                if e.errno != errno.EEXIST:
                    raise e
            segment_time = options[index].get('segment_time', 1)
            optlist = [
                "-flags", "-global_header", "-f", "segment", "-segment_time", "%s" % segment_time, "-segment_list", output_file, "-segment_list_type", "m3u8", "-segment_format", "mpegts",
                "-segment_list_entry_prefix", "%s/" % output_directory
            ]
            try:
                if options[index].get('maps'):
                    for input_map in (options[index].get('maps') or ['0']):
                        optlist.extend(['-map', str(input_map)])
                    stream_selected = None
                    if input_map.count(":") > 1:
                        input_stream = input_map.split(":")
                        count = 0
                        for stream in info.streams:
                            if (input_stream[1] == 'a' and 'audio' in stream.type) or (input_stream[1] == 'v' and 'video' in stream.type):
                                if count == int(input_stream[2]):
                                    stream_selected = stream
                                    break
                                else:
                                    count += 1
                    else:
                        track_id = int(input_map[-1])
                        stream_selected = info.streams[track_id]
                    codec = stream_selected.codec
                    codec_type = '-vcodec' if 'video' in stream_selected.type else '-acodec'
                    optlist.extend([codec_type, 'copy'])
                else:
                    input_map = ['0']
                    track_id = 0 if "video" in info.streams[0].type else 1
                    codec = info.streams[track_id].codec
                    optlist.extend(['-vcodec', 'copy', '-acodec', 'copy'])
            except Exception:
                warnings.warn('Could not determinate encoder', RuntimeWarning)
                codec = ""
            if "h264" in codec:
                optlist.insert(-4, "-vbsf")
                optlist.insert(-4, "h264_mp4toannexb")
            outfile = "%s/media%%05d.ts" % output_directory
            outputs_options.append(optlist)
            outputs_ts_files.append(outfile)
        current_directory = os.getcwd()
        os.chdir(working_directory)
        for timecode in self.ffmpeg.convert(infile, outputs_ts_files, outputs_options, timeout=timeout):
            yield float(timecode) / info.format.duration
        os.chdir(current_directory)

    def probe(self, fname, posters_as_video=True):
        """
        Examine the media file.

        See the documentation of converter.FFMpeg.probe() for details.

        :param posters_as_video: Take poster images (mainly for audio files) as
            A video stream, defaults to True
        """
        return self.ffmpeg.probe(fname, posters_as_video)

    def thumbnail(self, fname, time, outfile, size=None, quality=FFMpeg.DEFAULT_JPEG_QUALITY):
        """
        Create a thumbnail of the media file.

        See the documentation of converter.FFMpeg.thumbnail() for details.
        """
        return self.ffmpeg.thumbnail(fname, time, outfile, size, quality)

    def thumbnails(self, fname, option_list):
        """
        Create one or more thumbnail of the media file.

        See the documentation of converter.FFMpeg.thumbnails() for details.
        """
        return self.ffmpeg.thumbnails(fname, option_list)

    def mix(self, *args, **kwargs):
        return self.ffmpeg.mix(*args, **kwargs)
