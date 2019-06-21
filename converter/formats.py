#!/usr/bin/env python
# -*- coding: utf-8 -*-
from six import with_metaclass

format_list = list()


class MetaBaseFormat(type):

    def __new__(mcl, name, bases, dct):
        sub_class = type.__new__(mcl, name, bases, dct)
        if hasattr(mcl, "base_class"):
            for base in bases:
                if base in format_list and not base.format_name:
                    format_list.remove(base)
            if sub_class not in format_list:
                format_list.append(sub_class)
        else:
            mcl.base_class = sub_class
        return sub_class


class BaseFormat(with_metaclass(MetaBaseFormat, object)):

    """
    Base format class.

    Supported formats are: ogg, avi, mkv, webm, flv, mov, mp4, mpeg, wmv
    """

    format_name = None
    ffmpeg_format_name = None
    format_options = {
        'format': str
    }

    def parse_options(self, opt):
        safe = self.safe_options(opt)
        if 'format' not in safe or safe['format'] != self.format_name:
            raise ValueError('invalid Format format')
        optlist = ['-f', self.ffmpeg_format_name]
        safe = self._format_specific_parse_options(safe)
        optlist.extend(self._format_specific_produce_ffmpeg_list(safe))
        return optlist

    def _format_specific_parse_options(self, safe):
        return safe

    def _format_specific_produce_ffmpeg_list(self, safe):
        return []

    def safe_options(self, opts):
        safe = {}
        # Only copy options that are expected and of correct type
        # (and do typecasting on them)
        for k, v in opts.items():
            if k in self.format_options:
                typ = self.format_options[k]
                try:
                    safe[k] = typ(v)
                except Exception:
                    pass
        return safe


class OggFormat(BaseFormat):

    """
    Ogg container format, mostly used with Vorbis and Theora.
    """
    format_name = 'ogg'
    ffmpeg_format_name = 'ogg'


class AviFormat(BaseFormat):

    """
    Avi container format, often used vith DivX video.
    """
    format_name = 'avi'
    ffmpeg_format_name = 'avi'


class MkvFormat(BaseFormat):

    """
    Matroska format, often used with H.264 video.
    """
    format_name = 'mkv'
    ffmpeg_format_name = 'matroska'


class WebmFormat(BaseFormat):

    """
    WebM is Google's variant of Matroska containing only
    VP8 for video and Vorbis for audio content.
    """
    format_name = 'webm'
    ffmpeg_format_name = 'webm'


class FlvFormat(BaseFormat):

    """
    Flash Video container format.
    """
    format_name = 'flv'
    ffmpeg_format_name = 'flv'


class MovFormat(BaseFormat):

    """
    Mov container format, used mostly with H.264 video
    content, often for mobile platforms.
    """
    format_name = 'mov'
    ffmpeg_format_name = 'mov'
    format_options = BaseFormat.format_options.copy()
    format_options.update({
        'faststart': bool  # faststart mode
    })


class Mp4Format(BaseFormat):

    """
    Mp4 container format, the default Format for H.264 video content.
    """
    format_name = 'mp4'
    ffmpeg_format_name = 'mp4'
    format_options = BaseFormat.format_options.copy()
    format_options.update({
        'faststart': bool  # faststart mode
    })

    def _format_specific_parse_options(self, safe):
        optlist = []
        if safe.get('faststart', False):
            optlist.extend(['-movflags', 'faststart'])
        return optlist


class MpegFormat(BaseFormat):

    """
    MPEG(TS) container, used mainly for MPEG 1/2 video codecs.
    """
    format_name = 'mpg'
    ffmpeg_format_name = 'mpegts'


class Mp3Format(BaseFormat):

    """
    Mp3 container, used audio-only mp3 files
    """
    format_name = 'mp3'
    ffmpeg_format_name = 'mp3'


class WmvFormat(BaseFormat):

    """
    WMV container.
    """
    format_name = 'wmv'
    ffmpeg_format_name = 'msmpeg4'
