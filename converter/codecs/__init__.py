#!/usr/bin/env python
# -*- coding: utf-8 -*-
from six import with_metaclass

codec_lists = dict()
formats_supported = list()


class MetaBaseCodec(type):

    def __new__(mcl, name, bases, dct):
        sub_class = type.__new__(mcl, name, bases, dct)
        if hasattr(mcl, "base_class"):
            if mcl.base_class not in bases:
                codec_list = codec_lists.setdefault(
                    sub_class.codec_type, list())
                if hasattr(sub_class, 'formats_supported') and len(formats_supported) == 0:
                    formats_supported.insert(0, sub_class.formats_supported)
                for base in bases:
                    if base in codec_list and not base.codec_name:
                        codec_list.remove(base)
                if sub_class not in codec_list:
                    codec_list.append(sub_class)
        else:
            mcl.base_class = sub_class
        return sub_class


class BaseCodec(with_metaclass(MetaBaseCodec, object)):

    """
    Base audio/video codec class.
    """

    encoder_options = {}
    codec_name = None
    ffmpeg_codec_name = None

    def parse_options(self, opt):
        if 'codec' not in opt or opt['codec'] != self.codec_name:
            raise ValueError('invalid codec name')
        return None

    def _codec_specific_parse_options(self, safe):
        return safe

    def _codec_specific_produce_ffmpeg_list(self, safe):
        return []

    def safe_options(self, opts):
        safe = {}

        # Only copy options that are expected and of correct type
        # (and do typecasting on them)
        for k, v in opts.items():
            if k in self.encoder_options:
                typ = self.encoder_options[k]
                try:
                    safe[k] = typ(v)
                except Exception:
                    pass

        return safe


from converter.codecs.audio import *  # NOQA
from converter.codecs.subtitle import *  # NOQA
from converter.codecs.video import *  # NOQA
