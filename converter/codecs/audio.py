#!/usr/bin/env python
# -*- coding: utf-8 -*-

from . import BaseCodec


class AudioCodec(BaseCodec):

    """
    Base audio codec class handles general audio options. Possible
    parameters are:
      * codec (string) - audio codec name
      * channels (integer) - number of audio channels
      * bitrate (integer) - stream bitrate
      * samplerate (integer) - sample rate (frequency)

    Supported audio codecs are: null (no audio), copy (copy from original), vorbis, aac, ac3, flac, dts mp3, mp2, wma
    """

    codec_type = "audio"
    encoder_options = {
        'codec': str,
        'channels': int,
        'bitrate': int,
        'samplerate': int
    }

    def parse_options(self, opt):
        super(AudioCodec, self).parse_options(opt)

        safe = self.safe_options(opt)

        if 'channels' in safe:
            c = safe['channels']
            if c < 1 or c > 12:
                del safe['channels']

        if 'bitrate' in safe:
            br = safe['bitrate']
            if br < 8 or br > 512:
                del safe['bitrate']

        if 'samplerate' in safe:
            f = safe['samplerate']
            if f < 1000 or f > 50000:
                del safe['samplerate']

        safe = self._codec_specific_parse_options(safe)

        optlist = ['-codec:a', self.ffmpeg_codec_name]
        if 'channels' in safe:
            optlist.extend(['-ac', str(safe['channels'])])
        if 'bitrate' in safe:
            optlist.extend(['-b:a', str(safe['bitrate']) + 'k'])
        if 'samplerate' in safe:
            optlist.extend(['-ar', str(safe['samplerate'])])

        optlist.extend(self._codec_specific_produce_ffmpeg_list(safe))
        if 'filter' in opt:
            optlist.extend(['-filter:a', str(opt['filter'])])
        return optlist


class AudioNullCodec(AudioCodec):

    """
    Null audio codec (no audio).
    """
    codec_name = None

    def parse_options(self, opt):
        return ['-an']


class AudioCopyCodec(AudioCodec):

    """
    Copy audio stream directly from the source.
    """
    codec_name = 'copy'

    def parse_options(self, opt):
        return ['-codec:a', 'copy']


class VorbisCodec(AudioCodec):

    """
    Vorbis audio codec.
    @see http://ffmpeg.org/trac/ffmpeg/wiki/TheoraVorbisEncodingGuide
    """
    codec_name = 'vorbis'
    ffmpeg_codec_name = 'libvorbis'
    encoder_options = AudioCodec.encoder_options.copy()
    encoder_options.update({
        'quality': int,  # audio quality. Range is 0-10(highest quality)
        # 3-6 is a good range to try. Default is 3
    })

    def _codec_specific_produce_ffmpeg_list(self, safe):
        optlist = []
        if 'quality' in safe:
            optlist.extend(['-q:a', str(safe['quality'])])
        return optlist


class AacCodec(AudioCodec):

    """
    AAC audio codec.
    """
    codec_name = 'aac'
    ffmpeg_codec_name = 'aac'
    aac_experimental_enable = ['-strict', 'experimental']
    encoder_options = AudioCodec.encoder_options.copy()
    encoder_options.update({
        'quality': float,  # audio quality. Range is 0.1-10(highest quality)
        # Recommended: 1, https://trac.ffmpeg.org/wiki/Encode/AAC
    })

    def _codec_specific_parse_options(self, safe):
        if 'quality' in safe:
            q = safe['quality']
            if q < 0 or q > 9:
                del safe['quality']
        return safe

    def _codec_specific_produce_ffmpeg_list(self, safe):
        optlist = list(self.aac_experimental_enable)
        if 'quality' in safe:
            optlist.extend(['-q:a', str(safe['quality'])])
        return optlist


class FdkAacCodec(AudioCodec):

    """
    AAC audio codec.
    """
    codec_name = 'libfdk_aac'
    ffmpeg_codec_name = 'libfdk_aac'
    encoder_options = AudioCodec.encoder_options.copy()
    encoder_options.update({
        'quality': int,  # audio quality. Range is 1-5(highest quality)
        # Default is 4
    })

    def _codec_specific_parse_options(self, safe):
        if 'quality' in safe:
            q = safe['quality']
            if q < 1 or q > 5:
                del safe['quality']
        return safe

    def _codec_specific_produce_ffmpeg_list(self, safe):
        optlist = []
        if 'quality' in safe:
            optlist.extend(['-vbr', str(safe['quality'])])
        return optlist


class Ac3Codec(AudioCodec):

    """
    AC3 audio codec.
    """
    codec_name = 'ac3'
    ffmpeg_codec_name = 'ac3'


class FlacCodec(AudioCodec):

    """
    FLAC audio codec.
    """
    codec_name = 'flac'
    ffmpeg_codec_name = 'flac'


class DtsCodec(AudioCodec):

    """
    DTS audio codec.
    """
    codec_name = 'dts'
    ffmpeg_codec_name = 'dts'


class Mp3Codec(AudioCodec):

    """
    MP3 (MPEG layer 3) audio codec.
    """
    codec_name = 'mp3'
    ffmpeg_codec_name = 'libmp3lame'
    encoder_options = AudioCodec.encoder_options.copy()
    encoder_options.update({
        'quality': int,  # audio quality. Range is 0-9(lowest quality)
        # Recommended: 2, default is 4
    })

    def _codec_specific_parse_options(self, safe):
        if 'quality' in safe:
            q = safe['quality']
            if q < 0 or q > 9:
                del safe['quality']
        return safe

    def _codec_specific_produce_ffmpeg_list(self, safe):
        optlist = []
        if 'quality' in safe:
            optlist.extend(['-q:a', str(safe['quality'])])
        return optlist


class Mp2Codec(AudioCodec):

    """
    MP2 (MPEG layer 2) audio codec.
    """
    codec_name = 'mp2'
    ffmpeg_codec_name = 'mp2'


class WmaCodec(AudioCodec):

    """
    WMA audio codec.
    """
    codec_name = "wma"
    ffmpeg_codec_name = "wmav2"
