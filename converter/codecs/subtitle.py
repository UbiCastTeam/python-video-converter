#!/usr/bin/env python
# -*- coding: utf-8 -*-

from . import BaseCodec


class SubtitleCodec(BaseCodec):

    """
    Base subtitle codec class handles general subtitle options. Possible
    parameters are:
      * codec (string) - subtitle codec name (mov_text, subrib, ssa only supported currently)
      * language (string) - language of subtitle stream (3 char code)
      * forced (int) - force subtitles (1 true, 0 false)
      * default (int) - default subtitles (1 true, 0 false)

    Supported subtitle codecs are: null (no subtitle), mov_text
    """

    codec_type = "subtitle"
    encoder_options = {
        'codec': str,
        'language': str,
        'forced': int,
        'default': int
    }

    def parse_options(self, opt):
        super(SubtitleCodec, self).parse_options(opt)
        safe = self.safe_options(opt)

        if 'forced' in safe:
            if safe['forced'] < 0 or safe['forced'] > 1:
                del safe['forced']

        if 'default' in safe:
            if safe['default'] < 0 or safe['default'] > 1:
                del safe['default']

        if 'language' in safe:
            if len(safe['language']) > 3:
                del safe['language']

        safe = self._codec_specific_parse_options(safe)

        optlist = ['-scodec', self.ffmpeg_codec_name]

        optlist.extend(self._codec_specific_produce_ffmpeg_list(safe))
        return optlist


class SubtitleNullCodec(SubtitleCodec):

    """
    Null video codec (no video).
    """

    codec_name = None

    def parse_options(self, opt):
        return ['-sn']


class SubtitleCopyCodec(SubtitleCodec):

    """
    Copy subtitle stream directly from the source.
    """
    codec_name = 'copy'

    def parse_options(self, opt):
        return ['-scodec', 'copy']


class MOVTextCodec(SubtitleCodec):

    """
    mov_text subtitle codec.
    """
    codec_name = 'mov_text'
    ffmpeg_codec_name = 'mov_text'


class SSA(SubtitleCodec):

    """
    SSA (SubStation Alpha) subtitle.
    """
    codec_name = 'ass'
    ffmpeg_codec_name = 'ass'


class SubRip(SubtitleCodec):

    """
    SubRip subtitle.
    """
    codec_name = 'subrip'
    ffmpeg_codec_name = 'subrip'


class DVBSub(SubtitleCodec):

    """
    DVB subtitles.
    """
    codec_name = 'dvbsub'
    ffmpeg_codec_name = 'dvbsub'


class DVDSub(SubtitleCodec):

    """
    DVD subtitles.
    """
    codec_name = 'dvdsub'
    ffmpeg_codec_name = 'dvdsub'
