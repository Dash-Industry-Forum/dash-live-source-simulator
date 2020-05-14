"""
Generator of fragmented MP4 files.

The classes in this module are internal and are not accessed directly by a
user.
"""
from collections import namedtuple
from itertools import chain
import logging
import struct

MOVIE_TIMESCALE = 90000


PACK_U8 = struct.Struct('>B').pack
PACK_U16 = struct.Struct('>H').pack
PACK_U32 = struct.Struct('>L').pack
PACK_U64 = struct.Struct('>Q').pack
PACK_NAME = struct.Struct('4s').pack


def serialize_u8(x):
    """ Serialize uint_8
    """
    return PACK_U8(x & 0xff)


def serialize_u16(x):
    """ Serialize uint_16
    """
    return PACK_U16(x & 0xfffff)


def serialize_u32(x):
    """ Serialize uint_32
    """
    return PACK_U32(x & 0xffffffff)


def serialize_u64(x):
    """ Serialize uint_64
    """
    return PACK_U64(x)


def serialize_name(x):
    """ Serialize box name containing 4 characters
    """
    return PACK_NAME(x)


def serialize_string(x):
    """ Serialize string
    """
    return x


def serialize_bytes(x, n):
    """ Serialize array of bytes
    """
    return serialize_u8(x) * n


TRUNSample = namedtuple('TRUNSample', 'duration size sync offset')


SAIZSample = namedtuple('SAIZSample', 'sample_info_size')


SBGPGroup = namedtuple('TRUNSample', 'sample_count group_description_index')


SGPDGroup = namedtuple('SGPDGroup', 'is_encrypted iv_size kid')


SENCSample = namedtuple('SENCSample', 'iv subsamples')


SENCSubsample = namedtuple('SENCSubsample', 'clear_bytes enc_bytes')

SIDXReference = namedtuple('SIDXReference', 'reference_type '
                                            'referenced_size '
                                            'subsegment_duration '
                                            'starts_with_SAP '
                                            'SAP_type '
                                            'SAP_delta_time')


class Sample:

    def __init__(self, data, time=0, duration=0, sync=True, time_offset=0):
        self.data = data
        self.time = time
        self.duration = duration
        self.sync = sync
        self.time_offset = time_offset

    @property
    def size(self):
        return len(self.data)


class DataPlaceholder:

    def __init__(self, data_length):
        self.data_length = data_length

    def __len__(self):
        return self.data_length


class Box:

    def serialize(self):
        return b''.join(self)


class BoxSequence(Box):

    def __init__(self, *boxes):
        self.boxes = boxes

    def size(self):
        return sum(box.size() for box in self.boxes)

    def __iter__(self):
        for value in chain.from_iterable(self.boxes):
            yield value


class BoxContainer(Box):

    def __init__(self, name, boxes=None):
        self.name = name
        self.boxes = boxes if boxes else []

    def add_box(self, box):
        self.boxes.append(box)

    def size(self):
        return sum((box.size() for box in self.boxes), 8)

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(self.name)

        for value in chain.from_iterable(self.boxes):
            yield value


class FTYPBox(Box):
    """ File type and compatibility
    """

    def __init__(self, major_brand, minor_version, brands, styp=False):
        self.major_brand = major_brand
        self.minor_version = minor_version
        self.brands = brands if brands else []
        self.typ = b'styp' if styp else b'ftyp'

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(self.typ)
        yield serialize_name(self.major_brand)
        yield serialize_u32(self.minor_version)
        for brand in self.brands:
            yield serialize_name(brand)

    def size(self):
        return 16 + 4 * len(self.brands)


class MOOVBox(BoxContainer):
    """ Movie box, contains information about one or more tracks,
    where a track can be audio, video, or some other type of data
    """

    def __init__(self):
        super().__init__(b'moov')


class MVHDBox(Box):
    """ Movie header, overall declarations
    """

    def __init__(self, timescale, duration, next_track_id):
        self.timescale = timescale
        self.duration = duration
        self.next_track_id = next_track_id

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'mvhd')
        yield serialize_u32(0)  # version and flags

        yield serialize_u32(0)  # creation time
        yield serialize_u32(0)  # modification time
        yield serialize_u32(self.timescale)  # timescale
        yield serialize_u32(self.duration)  # duration

        # 80 bytes matrix etc
        yield serialize_u32(0x00010000)  # rate
        yield serialize_u16(0x0100)  # volume
        yield serialize_u16(0)  # reserved
        yield serialize_u32(0)  # reserved
        yield serialize_u32(0)  # reserved
        yield serialize_u32(0x00010000)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0x00010000)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0)  # matrix
        yield serialize_u32(0x40000000)  # matrix
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(0)  # pre-defined
        yield serialize_u32(self.next_track_id)

    def size(self):
        return 108


class MVEXBox(BoxContainer):
    """ Movie extends box
    """

    def __init__(self):
        super().__init__(b'mvex')


class TRAKBox(BoxContainer):
    """ Container for an individual track or stream
    """

    def __init__(self):
        super().__init__(b'trak')


class MDIABox(BoxContainer):
    """ Container for the media information in a track
    """

    def __init__(self):
        super().__init__(b'mdia')


class MINFBox(BoxContainer):
    """ Media information container
    """

    def __init__(self):
        super().__init__(b'minf')


class DINFBox(BoxContainer):
    """ Data information box, container
    """

    def __init__(self):
        super().__init__(b'dinf')


class STBLBox(BoxContainer):
    """ Sample table box, container for the time/space map
    """

    def __init__(self):
        super().__init__(b'stbl')


class TREXBox(Box):
    """ Track extends defaults
    """

    def __init__(self, track_id):
        self.track_id = track_id

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'trex')
        yield serialize_u32(0x00)  # version and flags
        yield serialize_u32(self.track_id)  # track_id
        yield serialize_u32(0x01)  # default_sample_description_index
        yield serialize_u32(0x00)  # default_sample_duration
        yield serialize_u32(0x00)  # default_sample_size
        yield serialize_u32(0x00)  # default_sample_flags

    def size(self):
        return 32


class TKHDBox(Box):
    """ Track header, overall information about the track
    """

    def __init__(self, track_id, duration, volume, width, height):
        self.track_id = track_id
        self.duration = duration
        self.volume = volume
        self.width = width
        self.height = height

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'tkhd')
        yield serialize_u32(0x00000007)  # version and flags

        yield serialize_u32(0)  # creation time
        yield serialize_u32(0)  # modification time
        yield serialize_u32(self.track_id)  # track_id
        yield serialize_u32(0)  # reserved
        yield serialize_u32(self.duration)  # duration

        yield serialize_u64(0)  # reserved
        yield serialize_u16(0)  # layer
        yield serialize_u16(0)  # alternate_group

        yield serialize_u16(self.volume)  # volume
        yield serialize_u16(0)  # reserved

        # matrix
        yield serialize_u32(0x00010000)
        yield serialize_u32(0)
        yield serialize_u32(0)
        yield serialize_u32(0)
        yield serialize_u32(0x00010000)
        yield serialize_u32(0)
        yield serialize_u32(0)
        yield serialize_u32(0)
        yield serialize_u32(0x40000000)

        yield serialize_u32(self.width << 16)
        yield serialize_u32(self.height << 16)

    def size(self):
        return 92


class MDHDBox(Box):
    """ Media header, overall information about the media

    lang field needs to be three characters according to ISO 639-2
    """

    def __init__(self, timescale, duration, lang):
        self.timescale = timescale
        self.duration = duration
        self.lang = lang

    def make_bits_from_lang_char(self, char):
        bits = (ord(char) - 0x60) & 0x1f
        char_back = bits + 0x60
        if chr(char_back) != char:
            raise ValueError(f"Cannot code char {char}")
        return bits

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'mdhd')
        yield serialize_u32(0x00000000)  # version and flags

        yield serialize_u32(0)  # creation time
        yield serialize_u32(0)  # modification time
        yield serialize_u32(self.timescale)  # timescale
        yield serialize_u32(self.duration)  # duration

        try:
            if len(self.lang) != 3:
                raise ValueError(f"Non-3-letter language code {self.lang}")
            lang = ((self.make_bits_from_lang_char(self.lang[0]) << 10) +
                    (self.make_bits_from_lang_char(self.lang[1]) << 5) +
                    (self.make_bits_from_lang_char(self.lang[2])))

        except ValueError as e:
            logging.info('mdhd generation: %s replaced by "und"' % e)
            lang = 0x55c4  # Representation of 'und'

        yield serialize_u16(lang)  # language
        yield serialize_u16(0)  # pre_defined

    def size(self):
        return 32


class HDLRBox(Box):
    """ Handler, declares the media (handler) type
    """

    def __init__(self, handler_type, handler_name):
        self.handler_type = handler_type
        self.handler_name = handler_name

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'hdlr')
        yield serialize_u32(0x00000000)  # version and flags
        yield serialize_u32(0)  # pre_defined
        yield serialize_string(self.handler_type)
        yield serialize_u32(0)  # reserved
        yield serialize_u32(0)  # reserved
        yield serialize_u32(0)  # reserved
        yield serialize_string(self.handler_name)  # handler
        yield serialize_u8(0)  # null terminator

    def size(self):
        return 33 + len(self.handler_name)


class URLBox(Box):
    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'url ')
        yield serialize_u32(0x00000001)

    def size(self):
        return 12


class DREFBox(Box):
    """ Data reference box, declares source(s) of media data in track
    """

    def __init__(self):
        self.url = URLBox()

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'dref')
        yield serialize_u32(0x00000000)  # version and flags
        yield serialize_u32(0x00000001)  # entry count

        for value in self.url:
            yield value

    def size(self):
        return 16 + self.url.size()


class VMHDBox(Box):
    """ Video media header, overall information (video track only)
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'vmhd')
        yield serialize_u32(0x00000000)  # version and flags
        yield serialize_u16(0x0000)  # graphics_mode
        yield serialize_u8(0)  # opcolor
        yield serialize_u8(0)  # opcolor
        yield serialize_u8(0)  # opcolor
        yield serialize_u8(0)  # opcolor
        yield serialize_u8(0)  # opcolor
        yield serialize_u8(0)  # opcolor

    def size(self):
        return 20


class SMHDBox(Box):
    """  Sound media header, overall information (sound track only)
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'smhd')
        yield serialize_u32(0x00000000)  # version and flags
        yield serialize_u16(0x0000)  # balance
        yield serialize_u16(0x0000)  # reserved

    def size(self):
        return 16


class NMHDBox(Box):
    """ Null media header, overall information (some tracks only)
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'nmhd')
        yield serialize_u32(0x00000000)  # version and flags

    def size(self):
        return 12


class VisualSampleEntry(Box):

    def __init__(self, coding, width, height, avcc, pasp):
        self.coding = coding
        self.width = width
        self.height = height
        self.avcc = avcc
        self.pasp = pasp

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(self.coding)

        yield serialize_bytes(0, 6)  # reserved
        yield serialize_u16(0x0001)  # data_reference_index

        # visual
        yield serialize_u16(0x0000)  # pre_defined
        yield serialize_u16(0x0000)  # reserved
        yield serialize_bytes(0x00, 12)  # pre_defined

        # width / height
        yield serialize_u16(self.width)  # width
        yield serialize_u16(self.height)  # height
        yield serialize_u32(0x00480000)  # horires = 72 dpi
        yield serialize_u32(0x00480000)  # vert = 72 dpi

        yield serialize_bytes(0, 4)  # reserved
        yield serialize_u16(0x0001)  # frame_count
        yield serialize_bytes(0, 32)  # compressorname
        yield serialize_u16(0x0018)  # depth
        yield serialize_u16(0xffff)  # pre_defined

        # rest of the boxes
        for value in self.avcc:
            yield value

    def size(self):
        return 86 + self.avcc.size()


class AudioSampleEntry(Box):

    def __init__(self, coding, num_channels, sample_size, sample_rate, esds):
        self.coding = coding
        self.num_channels = num_channels
        self.sample_size = sample_size
        self.sample_rate = sample_rate
        self.esds = esds

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(self.coding)

        yield serialize_bytes(0, 6)  # reserved
        yield serialize_u16(0x0001)  # data_reference_index

        # audio
        yield serialize_bytes(0, 8)  # reserved
        yield serialize_u16(self.num_channels)  # channelcount
        yield serialize_u16(self.sample_size)  # samplesize
        yield serialize_u16(0)  # pre_defined
        yield serialize_u16(0)  # reserved
        yield serialize_u32(self.sample_rate << 16)  # samplerate

        # rest of the boxes
        yield self.esds

    def size(self):
        return 36 + len(self.esds)


class WVTTSampleEntryBox(Box):
    """ WebVTT data
    """

    def __init__(self):
        self.vttC = WVTTConfigBox()

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'wvtt')
        yield b'\x00' * 6 + serialize_u16(1)  # SampleEntry data format

        for value in self.vttC:
            yield value

    def size(self):
        return 16 + self.vttC.size()


class WVTTConfigBox(Box):
    """WebVTTConfigurationBox (vttC). Contains top-level configuration."""

    def __init__(self, config_string='WEBVTT'):
        """The minimal configuration is WEBVTT."""
        self.utf8_text = config_string.encode()

    def __iter__(self):
        yield serialize_u32(self.size())
        yield b'vttC'
        yield self.utf8_text

    def size(self):
        return 8 + len(self.utf8_text)


class VTTCBox(BoxContainer):
    """VTTCueBox. Contains exactly one WebVTT Cue."""

    def __init__(self, boxes=None):
        super().__init__(b'vttc', boxes)


class VTTEBox(Box):
    """VTTEmptyCueBox. Indicates that no subtitles are available."""

    def __iter__(self):
        yield serialize_u32(self.size())
        yield b'vtte'

    def size(self):
        return 8


class PAYLBox(Box):
    """CuePayloadBox. Contains the WebVTT text."""

    def __init__(self, cue_text='place_holder'):
        self.utf8_data = cue_text.encode()

    def __iter__(self):
        yield serialize_u32(self.size())
        yield b'payl'
        yield self.utf8_data

    def size(self):
        return 8 + len(self.utf8_data)


class STSDBox(Box):
    """ Sample descriptions (codec types, initialization etc.)
    """

    def __init__(self):
        self.boxes = []

    def add_box(self, box):
        self.boxes.append(box)

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'stsd')

        yield serialize_u32(0x00)  # version and flags
        yield serialize_u32(len(self.boxes))  # entry_count

        for value in chain.from_iterable(self.boxes):
            yield value

    def size(self):
        return sum((b.size() for b in self.boxes), 16)


class AVCCBox(Box):
    """ AVC Decoder Configuration
    """

    def __init__(self, profile_ind, profile_compat, level_ind, sps, pps):
        self.profile_ind = profile_ind
        self.profile_compat = profile_compat
        self.level_ind = level_ind
        self.sps = sps
        self.pps = pps

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'avcC')

        yield serialize_u8(0x01)  # configured
        yield serialize_u8(self.profile_ind)  # AVC profile indication
        yield serialize_u8(self.profile_compat)  # AVC profile compatibility
        yield serialize_u8(self.level_ind)  # AVC level

        yield serialize_u8(0xff)  # 4 bytes NAL
        yield serialize_u8(0xe1)  # 1 SPS

        # SPS
        yield serialize_u16(len(self.sps))  # sps length
        yield self.sps

        # PPS
        yield serialize_u8(0x01)  # 1 PPS
        yield serialize_u16(len(self.pps))  # sps length
        yield self.pps

    def size(self):
        return 19 + len(self.sps) + len(self.pps)


class HVCCBox(Box):
    """ HEVC Decoder Configuration
    """

    def __init__(self, hvcc_data, vps, sps, pps):
        self.hvcc_data = hvcc_data
        self.vps = vps
        self.sps = sps
        self.pps = pps

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'hvcC')

        writer = bitwriter.Bitwriter()
        writer.add_bits(0x01, 8)  # configurationVersion
        writer.add_bits(self.hvcc_data.general_profile_space, 2)
        writer.add_bits(self.hvcc_data.general_tier_flag, 1)
        writer.add_bits(self.hvcc_data.general_profile_idc, 5)
        writer.add_bits(self.hvcc_data.general_profile_compatibility_flags, 32)

        value = self.hvcc_data.general_constraint_indicator_flags
        high_bits = value >> 32
        low_bits = value & 0xffffffff
        writer.add_bits(high_bits, 16)
        writer.add_bits(low_bits, 32)

        writer.add_bits(self.hvcc_data.general_level_idc, 8)
        writer.add_bits(0xf, 4)  # reserved
        writer.add_bits(self.hvcc_data.min_spatial_segmentation_idc, 12)
        writer.add_bits(0x3f, 6)  # reserved
        writer.add_bits(self.hvcc_data.parallelism_type, 2)
        writer.add_bits(0x3f, 6)  # reserved
        writer.add_bits(self.hvcc_data.chroma_format_idc, 2)
        writer.add_bits(0x1f, 5)  # reserved
        writer.add_bits(self.hvcc_data.bit_depth_luma_minus8, 3)
        writer.add_bits(0x1f, 5)  # reserved
        writer.add_bits(self.hvcc_data.bit_depth_chroma_minus8, 3)

        writer.add_bits(0, 16)  # avgFrameRate
        writer.add_bits(0, 2)  # constantFrameRate
        writer.add_bits(1, 3)  # numTemporalLayers
        writer.add_bits(1, 1)  # temporalIdNested
        writer.add_bits(3, 2)  # lengthSizeMinusOne
        writer.add_bits(3, 8)  # numOfArrays

        # vps
        writer.add_bits(0, 1)  # array_completeness
        writer.add_bits(0, 1)  # reserved
        writer.add_bits(32, 6)  # NAL_unit_type
        writer.add_bits(1, 16)  # numNalus
        writer.add_bits(len(self.vps), 16)  # nalUnitLength
        writer.add_bytes(self.vps)

        # sps
        writer.add_bits(0, 1)  # array_completeness
        writer.add_bits(0, 1)  # reserved
        writer.add_bits(33, 6)  # NAL_unit_type
        writer.add_bits(1, 16)  # numNalus
        writer.add_bits(len(self.sps), 16)  # nalUnitLength
        writer.add_bytes(self.sps)

        # pps
        writer.add_bits(0, 1)  # array_completeness
        writer.add_bits(0, 1)  # reserved
        writer.add_bits(34, 6)  # NAL_unit_type
        writer.add_bits(1, 16)  # numNalus
        writer.add_bits(len(self.pps), 16)  # nalUnitLength
        writer.add_bytes(self.pps)

        yield writer.get_bytes()

    def size(self):
        return 46 + len(self.vps) + len(self.sps) + len(self.pps)


class ESDSBox(Box):
    """ MPEG-4 Elementary Stream Descriptor
    """

    def __init__(self, decoder_config):
        self.decoder_config = decoder_config

    def __iter__(self):
        dec_cfg_len = len(self.decoder_config)
        yield serialize_u32(self.size())
        yield serialize_name(b'esds')

        # 9 bytes
        yield serialize_u32(0)  # version and flags
        yield serialize_u8(3)  # tag
        yield serialize_u8(23 + dec_cfg_len)  # length
        yield serialize_u16(0x0001)  # esid
        yield serialize_u8(0)  # priority

        # 15 bytes
        yield serialize_u8(4)  # tag
        yield serialize_u8(15 + dec_cfg_len)  # length
        yield serialize_u8(0x40)  # object type
        yield serialize_u8(0x15)  # stream type
        yield serialize_u8(0)  # buffer_size
        yield serialize_u8(0)  # buffer_size
        yield serialize_u8(0)  # buffer_size

        yield serialize_u32(0)  # max bitrate
        yield serialize_u32(0)  # avg bitrate

        # 2 bytes
        yield serialize_u8(5)  # tag
        yield serialize_u8(dec_cfg_len)  # length

        # decoder config
        yield self.decoder_config

        # 3 bytes
        yield serialize_u8(6)  # tag
        yield serialize_u8(1)  # length
        yield serialize_u8(2)  # constant

    def size(self):
        # 37 is the size of the esds box minus the actual decoder config
        return 37 + len(self.decoder_config)


class PASPBox(Box):
    """Picture Aspect Ratio Box
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'pasp')

        yield serialize_u32(0x00000001)  # hSpacing
        yield serialize_u32(0x00000001)  # vSpacing

    def size(self):
        return 16


class STTSBox(Box):
    """ (decoding) time-to-sample
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'stts')
        yield serialize_u32(0)  # version and flags
        yield serialize_u32(0)  # entry_count

    def size(self):
        return 16


class STSCBox(Box):
    """ Sample-to-chunk, partial data-offset information
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'stsc')
        yield serialize_u32(0)  # version and flags
        yield serialize_u32(0)  # entry_count

    def size(self):
        return 16


class STSZBox(Box):
    """ Sample sizes (framing)
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'stsz')
        yield serialize_u32(0)  # version and flags
        yield serialize_u32(0)  # sample_size
        yield serialize_u32(0)  # entry_count

    def size(self):
        return 20


class STCOBox(Box):
    """ Chunk offset, partial data-offset information
    """

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'stco')
        yield serialize_u32(0)  # version and flags
        yield serialize_u32(0)  # entry_count

    def size(self):
        return 16


class MOOFBox(BoxContainer):
    """ Movie fragment
    """

    def __init__(self):
        super().__init__(b'moof')


class TRAFBox(BoxContainer):
    """ Track fragment
    """

    def __init__(self):
        super().__init__(b'traf')


class TFHDBox(Box):
    """ Track fragment header
    """

    def __init__(self, track_id):
        self.track_id = track_id

    def __iter__(self):
        flags = 0x20000  # default base is moof

        yield serialize_u32(self.size())
        yield serialize_name(b'tfhd')
        yield serialize_u32(flags)  # version and flags
        yield serialize_u32(self.track_id)  # track_id

    def size(self):
        return 16


class TFDTBox(Box):
    """ Track fragment decode time
    """
    _size = 20

    def __init__(self, decode_time):
        self.decode_time = decode_time

    def __iter__(self):
        v_and_f = 0x01000000  # Use 64 bits for timestamp

        yield serialize_u32(self.size())
        yield serialize_name(b'tfdt')
        yield serialize_u32(v_and_f)  # version and flags
        yield serialize_u64(self.decode_time)  # decode_time

    def size(self):
        return 20


class TRUNBox(Box):
    """ Track fragment run
    """

    def __init__(self, data_offset):
        self.samples = []
        self.data_offset = data_offset
        self.use_comp_off = False  # Needs to be true for dash.js

    def add_sample(self, duration, size, sync, offset):
        self.samples.append(TRUNSample(duration, size, sync, offset))
        if offset != 0:
            self.use_comp_off = True

    def set_data_offset(self, data_offset):
        self.data_offset = data_offset

    def __iter__(self):
        # Flags:
        #  data-offset     = 0x000001
        #  sample_duration = 0x000100
        #  sample_size     = 0x000200
        #  sample_flags    = 0x000400
        #  sample_time_off = 0x000800

        flags = 0x000001 | 0x000100 | 0x000200 | 0x000400
        if self.use_comp_off:
            flags |= 0x000800

        yield serialize_u32(self.size())
        yield serialize_name(b'trun')
        yield serialize_u32(flags)  # version and flags
        yield serialize_u32(len(self.samples))  # sample_count
        yield serialize_u32(self.data_offset)  # data_offset

        for sample in self.samples:
            yield serialize_u32(sample.duration)
            yield serialize_u32(sample.size)

            # The following 32-bits are defined in 14496-12 8.8.3.1 + 8.6.4.3
            # 4bits reserved (0)
            # 2bits is_leading (0 = unknown)
            # 2bits sample_depends_on (2 = I-picture or 1 = non-I-picture)
            # 2bits sample_is_dependend_on (0 = unknown)
            # 2bits has_redundancy (0 = unknown)
            # 3bits sample_padding_value
            # 1bit sample_is_non_sync_sample (0 or 1, match sync samples)
            # 16bits sample_degradation_priority (0)
            sync_flag = 0x02000000 if sample.sync else 0x01010000
            yield serialize_u32(sync_flag)

            if self.use_comp_off:
                yield serialize_u32(sample.offset)

    def size(self):
        return 20 + len(self.samples) * (12 + (4 if self.use_comp_off else 0))


class MFHDBox(Box):
    """ Movie fragment header
    """

    def __init__(self, seq_no):
        self.seq_no = seq_no

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'mfhd')
        yield serialize_u32(0)  # version and flags
        yield serialize_u32(self.seq_no)

    def size(self):
        return 16


class MDATBox(Box):
    """ Media data container
    """

    def __init__(self):
        self.data = []

    def add_data(self, data):
        self.data.append(data)

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'mdat')

        for value in self.data:
            yield value

    def size(self):
        return sum((len(x) for x in self.data), 8)


class SAIZBox(Box):
    """ Sample auxiliary information sizes
    """

    def __init__(self, default_sample_info_size):
        self.default_sample_info_size = default_sample_info_size
        self.samples = []

    def add_sample(self, sample_info_size):
        self.samples.append(SAIZSample(sample_info_size))

    def __iter__(self):
        default_size = 0 if self.samples else self.default_sample_info_size
        yield serialize_u32(self.size())
        yield serialize_name(b'saiz')
        yield serialize_u32(0x00)  # version and flags
        yield serialize_u8(default_size)  # default_sample_info_size
        yield serialize_u32(len(self.samples))  # sample_count

        for sample in self.samples:
            yield serialize_u8(sample.sample_info_size)

    def size(self):
        # 17 is the base size of the saiz box
        return 17 + len(self.samples)


class SAIOBox(Box):
    """ Sample auxiliary information offsets
    """

    def __init__(self, offset):
        self.offset = offset

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'saio')
        yield serialize_u32(0x00)  # version and flags
        yield serialize_u32(1)  # entry_count
        yield serialize_u32(self.offset)  # offset

    def size(self):
        return 20


class SBGPBox(Box):
    """ Sample to Group box
    """

    def __init__(self):
        self.groups = []

    def add_group(self, sample_count, group_description_index):
        self.groups.append(SBGPGroup(sample_count, group_description_index))

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'sbgp')
        yield serialize_u32(0x00)  # version and flags
        yield serialize_u32(len(self.groups))  # entry_count

        for group in self.groups:
            yield serialize_u32(group.sample_count)
            yield serialize_u32(group.group_description_index)

    def size(self):
        # 16 is the base size of the 'sbgp' box
        # each entry is 8 bytes long
        return 16 + 8 * len(self.groups)


class SGPDBox(Box):
    """ Sample group definition box
    """

    def __init__(self, grouping_type):
        self.grouping_type = grouping_type
        self.groups = []

    def add_group(self, is_encrypted, iv_size, kid):
        self.groups.append(SGPDGroup(is_encrypted, iv_size, kid))

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'sgpd')
        yield serialize_u32(0x00)  # version and flags
        yield serialize_u32(self.grouping_type)  # grouping_type
        yield serialize_u32(len(self.groups))  # entry_count

        for group in self.groups:
            yield serialize_u8(0)
            yield serialize_u8(0)
            yield serialize_u8(1 if group.is_encrypted else 0)
            yield serialize_u8(group.iv_size)
            yield serialize_string(group.kid)

    def size(self):
        # 20 is the base size of the 'sgpd' box
        # each item is 20 bytes long
        return 20 + 20 * len(self.groups)


class SENCBox(Box):
    """ Sample specific encryption data
    """
    _subsample_count_size = 2
    _subsample_size = 6

    def __init__(self, iv_size):
        self.iv_size = iv_size
        self.flags = 0
        self.samples = []

        # self.sz is the size of the box
        # Base size of the 'senc' box is 16 bytes
        self.sz = 16

    def add_sample(self, iv, subsamples):
        self.samples.append(SENCSample(iv, subsamples))
        self.sz += self.iv_size

        if subsamples:
            self.flags = 0x000002
            self.sz += (self._subsample_count_size +
                        len(subsamples) * self._subsample_size)

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'senc')
        yield serialize_u32(self.flags)  # version and flags
        yield serialize_u32(len(self.samples))  # sample_count

        for sample in self.samples:
            yield serialize_u64(sample.iv)  # iv

            if self.flags == 0x000002:
                yield serialize_u16(len(sample.subsamples))
                for subsample in sample.subsamples:
                    yield serialize_u16(subsample.clear_bytes)
                    yield serialize_u32(subsample.enc_bytes)

    def size(self):
        return self.sz


class SIDXBox(Box):
    """ Segment Index Box, 8.16.3
    """

    def __init__(self, reference_id, timescale, earliest_presentation_time,
                 version=0):
        self.reference_id = reference_id
        self.timescale = timescale
        self.earliest_presentation_time = earliest_presentation_time
        self.version = version
        self.first_offset = 0  # assume sidx is directly before first media seg
        self.sz = 32 + 8 * self.version  # 8 bytes extra if version == 1
        self.references = []

    def add_reference(self, referenced_size, subsegment_duration,
                      reference_type=0, starts_with_sap=1, sap_type=1,
                      sap_delta_time=0):
        self.references.append(SIDXReference(reference_type,
                                             referenced_size,
                                             subsegment_duration,
                                             starts_with_sap,
                                             sap_type,
                                             sap_delta_time))
        self.sz += 12

    def __iter__(self):
        yield serialize_u32(self.size())
        yield serialize_name(b'sidx')
        yield serialize_u8(self.version)  # version
        yield serialize_u16(0)            # flags
        yield serialize_u8(0)             # flags
        yield serialize_u32(self.reference_id)
        yield serialize_u32(self.timescale)
        if self.version == 0:
            yield serialize_u32(self.earliest_presentation_time)
            yield serialize_u32(self.first_offset)
        else:
            yield serialize_u64(self.earliest_presentation_time)
            yield serialize_u64(self.first_offset)
        yield serialize_u16(0)            # reserved
        yield serialize_u16(len(self.references))

        for ref in self.references:
            yield serialize_u32((ref.reference_type << 31) +
                                ref.referenced_size)
            yield serialize_u32(ref.subsegment_duration)
            yield serialize_u32((ref.starts_with_SAP << 31) +
                                (ref.SAP_type << 28) +
                                ref.SAP_delta_time)

    def size(self):
        return self.sz


def create_empty_sidx(track_id, timescale, no_segments):
    # Will create a "placeholder" in order to get correct sidx size.
    # References can be set later on
    sidx = SIDXBox(track_id, timescale, 0, 1)
    for _ in range(0, no_segments):
        sidx.add_reference(0, 0)
    return sidx


def create_stsd_h264(media_type, width, height, avcc):
    pasp = PASPBox()
    visual = VisualSampleEntry(media_type, width, height, avcc, pasp)

    # sinf
    # TODO

    stsd = STSDBox()
    stsd.add_box(visual)
    return stsd


def create_stsd_hevc(media_type, width, height, hvcc):
    pasp = PASPBox()
    visual = VisualSampleEntry(media_type, width, height, hvcc, pasp)

    # sinf
    # TODO

    stsd = STSDBox()
    stsd.add_box(visual)
    return stsd


def create_stsd_mp4a(media_type,
                     num_channels,
                     sample_size,
                     sample_rate,
                     esds):

    audio = AudioSampleEntry(media_type,
                             num_channels,
                             sample_size,
                             sample_rate,
                             esds)

    # sinf
    # TODO

    stsd = STSDBox()
    stsd.add_box(audio)
    return stsd


def create_stsd_ac3(media_type,
                    num_channels,
                    sample_size,
                    sample_rate,
                    specific_box):

    audio = AudioSampleEntry(media_type,
                             num_channels,
                             sample_size,
                             sample_rate,
                             specific_box)

    stsd = STSDBox()
    stsd.add_box(audio)
    return stsd


def create_stsd_mp4s():
    """Create stsd for WebVTT subtitles."""
    stsd = STSDBox()
    wvtt_box = WVTTSampleEntryBox()
    stsd.add_box(wvtt_box)
    return stsd


def create_minf_box(stsd, media_header_box):
    minf = MINFBox()

    # mdhd
    minf.add_box(media_header_box)

    # dinf / dref
    dinf = DINFBox()
    dref = DREFBox()
    dinf.add_box(dref)
    minf.add_box(dinf)

    # stbl
    stbl = STBLBox()
    stbl.add_box(stsd)
    stbl.add_box(STTSBox())
    stbl.add_box(STSCBox())
    stbl.add_box(STSZBox())
    stbl.add_box(STCOBox())
    minf.add_box(stbl)

    return minf


def create_box_mdia(media_type,
                    handler,
                    timescale,
                    duration,
                    language,
                    stsd,
                    media_header_box):
    mdia = MDIABox()

    # mdhd
    mdhd = MDHDBox(timescale, duration, language)
    mdia.add_box(mdhd)

    # hdlr
    hdlr = HDLRBox(media_type, handler)
    mdia.add_box(hdlr)

    # minf
    minf = create_minf_box(stsd, media_header_box)

    mdia.add_box(minf)

    return mdia


def create_box_trak_h264(h264_info):
    trak = TRAKBox()
    duration = h264_info.duration * MOVIE_TIMESCALE
    tkhd = TKHDBox(h264_info.track_id,
                   int(duration / h264_info.timescale),
                   0, h264_info.width, h264_info.height)
    trak.add_box(tkhd)

    # avcc
    avcc = AVCCBox(h264_info.profile_ind,
                   h264_info.profile_compat,
                   h264_info.level_ind,
                   h264_info.sps,
                   h264_info.pps)

    # stsd
    stsd = create_stsd_h264(b'avc1',
                            h264_info.width,
                            h264_info.height,
                            avcc)

    # vmhd
    vmhd = VMHDBox()

    lang = 'und'

    # mdia
    mdia = create_box_mdia(b'vide',
                           b'Edgeware Video Media Handler',
                           h264_info.timescale,
                           h264_info.duration,
                           lang,
                           stsd,
                           vmhd)
    trak.add_box(mdia)

    return trak


def create_box_trak_hevc(hevc_info):
    trak = TRAKBox()
    duration = hevc_info.duration * MOVIE_TIMESCALE
    tkhd = TKHDBox(hevc_info.track_id,
                   int(duration / hevc_info.timescale),
                   0, hevc_info.width, hevc_info.height)
    trak.add_box(tkhd)

    # hvcc
    hvcc = HVCCBox(hevc_info.hvcc_data,
                   hevc_info.vps,
                   hevc_info.sps,
                   hevc_info.pps)

    # stsd
    stsd = create_stsd_hevc(b'hev1',
                            hevc_info.width,
                            hevc_info.height,
                            hvcc)

    # vmhd
    vmhd = VMHDBox()

    lang = 'und'

    # mdia
    mdia = create_box_mdia(b'vide',
                           b'Edgeware Video Media Handler',
                           hevc_info.timescale,
                           hevc_info.duration,
                           lang,
                           stsd,
                           vmhd)
    trak.add_box(mdia)

    return trak


def create_box_trak_mp4a(mp4a_info):
    volume = 0x100
    trak = TRAKBox()
    duration = mp4a_info.duration * MOVIE_TIMESCALE
    tkhd = TKHDBox(mp4a_info.track_id,
                   int(duration / mp4a_info.timescale),
                   volume, 0, 0)
    trak.add_box(tkhd)

    # stsd
    stsd = create_stsd_mp4a(b'mp4a',
                            mp4a_info.num_channels,
                            mp4a_info.sample_size,
                            mp4a_info.sample_rate,
                            mp4a_info.esds)

    # smhd
    smhd = SMHDBox()

    # mdia
    mdia = create_box_mdia(b'soun',
                           b'Edgeware Audio Media Handler',
                           mp4a_info.timescale,
                           mp4a_info.duration,
                           mp4a_info.lang,
                           stsd,
                           smhd)
    trak.add_box(mdia)

    return trak


def create_box_trak_ac3(ac3_info):
    volume = 0x100
    trak = TRAKBox()
    duration = ac3_info.duration * MOVIE_TIMESCALE
    tkhd = TKHDBox(ac3_info.track_id,
                   int(duration / ac3_info.timescale),
                   volume, 0, 0)
    trak.add_box(tkhd)

    if ac3_info.codec == 'ac-3':
        media_type = b'ac-3'
    elif ac3_info.codec == 'ec-3' or ac3_info.codec == 'ec+3':
        media_type = b'ec-3'
    else:
        raise ValueError(f"Invalid codec {ac3_info.codec}")

    # stsd
    stsd = create_stsd_ac3(media_type,
                           ac3_info.num_channels,
                           ac3_info.sample_size,
                           ac3_info.sample_rate,
                           ac3_info.specific_box)

    # smhd
    smhd = SMHDBox()

    # mdia
    mdia = create_box_mdia(b'soun',
                           b'Edgeware Audio Media Handler',
                           ac3_info.timescale,
                           ac3_info.duration,
                           ac3_info.lang,
                           stsd,
                           smhd)
    trak.add_box(mdia)

    return trak


def create_box_trak_mp4s(mp4s_info):
    trak = TRAKBox()
    duration = mp4s_info.duration * MOVIE_TIMESCALE
    tkhd = TKHDBox(mp4s_info.track_id,
                   int(duration / mp4s_info.timescale),
                   0, 0, 0)
    trak.add_box(tkhd)

    # stsd
    stsd = create_stsd_mp4s()

    # nmhd
    nmhd = NMHDBox()

    # mdia
    mdia = create_box_mdia(b'text',
                           b'Edgeware Subtitle Media Handler',
                           mp4s_info.timescale,
                           mp4s_info.duration,
                           mp4s_info.lang,
                           stsd,
                           nmhd)
    trak.add_box(mdia)

    return trak


class MediaInfo:

    def __init__(self, track_id, timescale, duration):
        self.track_id = track_id
        self.timescale = timescale
        self.duration = duration


class H264Info(MediaInfo):

    def __init__(self, track_id, timescale, duration,
                 width, height,
                 profile_ind, profile_compat, level_ind,
                 sps, pps):
        super().__init__(track_id, timescale, duration)
        self.width = width
        self.height = height
        self.profile_ind = profile_ind
        self.profile_compat = profile_compat
        self.level_ind = level_ind
        self.sps = sps
        self.pps = pps


class HVCCData:

    def __init__(self):
        self.general_profile_space = 0
        self.general_tier_flag = 0
        self.general_profile_idc = 0
        self.general_profile_compatibility_flags = 0
        self.general_constraint_indicator_flags = 0
        self.general_level_idc = 0
        self.min_spatial_segmentation_idc = 0  # TODO: set this
        self.parallelism_type = 0  # TODO: set this

        self.chroma_format_idc = 0
        self.width = 0
        self.height = 0
        self.bit_depth_luma_minus8 = 0
        self.bit_depth_chroma_minus8 = 0


class HEVCInfo(MediaInfo):

    def __init__(self, track_id, timescale, duration,
                 width, height,
                 vps, sps, pps,
                 hvcc_data):
        super().__init__(track_id, timescale, duration)
        self.width = width
        self.height = height
        self.vps = vps
        self.sps = sps
        self.pps = pps
        self.hvcc_data = hvcc_data


class MP4AInfo(MediaInfo):

    def __init__(self, track_id, timescale, duration,
                 num_channels, sample_size, sample_rate,
                 esds, dec_cfg, lang='und'):
        super().__init__(track_id, timescale, duration)
        self.num_channels = num_channels
        self.sample_size = sample_size
        self.sample_rate = sample_rate
        self.esds = esds
        self.dec_cfg = dec_cfg
        self.lang = lang


class MP4SInfo(MediaInfo):

    def __init__(self, track_id, timescale, duration, lang='und'):
        super().__init__(track_id, timescale, duration)
        self.lang = lang


class AC3Info(MediaInfo):
    """Information needed to create and ac-3, ec-3 box.
    The specific_box should be a full binary dac3 or dec3 box."""

    def __init__(self, codec, track_id, timescale, duration,
                 num_channels, sample_size, sample_rate,
                 specific_box, lang='und'):
        super().__init__(track_id, timescale, duration)
        self.codec = codec
        self.num_channels = num_channels
        self.sample_size = sample_size
        self.sample_rate = sample_rate
        self.specific_box = specific_box
        self.lang = lang


def create_moov_h264(h264_info):
    moov = MOOVBox()

    # mvhd
    scale_from = h264_info.timescale
    scale_to = MOVIE_TIMESCALE
    dur_media = int((h264_info.duration * scale_to) / scale_from)
    mvhd = MVHDBox(MOVIE_TIMESCALE, dur_media, h264_info.track_id + 1)
    moov.add_box(mvhd)

    # trak
    trak = create_box_trak_h264(h264_info)
    moov.add_box(trak)

    # mvex/trex
    trex = TREXBox(h264_info.track_id)
    mvex = MVEXBox()
    mvex.add_box(trex)
    moov.add_box(mvex)

    return moov


def create_moov_hevc(hevc_info):
    moov = MOOVBox()

    # mvhd
    scale_from = hevc_info.timescale
    scale_to = MOVIE_TIMESCALE
    dur_media = int((hevc_info.duration * scale_to) / scale_from)
    mvhd = MVHDBox(MOVIE_TIMESCALE, dur_media, hevc_info.track_id + 1)
    moov.add_box(mvhd)

    # trak
    trak = create_box_trak_hevc(hevc_info)
    moov.add_box(trak)

    # mvex/trex
    trex = TREXBox(hevc_info.track_id)
    mvex = MVEXBox()
    mvex.add_box(trex)
    moov.add_box(mvex)

    return moov


def create_moov_mp4a(mp4a_info):
    moov = MOOVBox()

    # mvhd
    scale_from = mp4a_info.timescale
    scale_to = MOVIE_TIMESCALE
    dur_media = int((mp4a_info.duration * scale_to) / scale_from)
    mvhd = MVHDBox(MOVIE_TIMESCALE, dur_media, mp4a_info.track_id + 1)
    moov.add_box(mvhd)

    # mvex/trex
    trex = TREXBox(mp4a_info.track_id)
    mvex = MVEXBox()
    mvex.add_box(trex)
    moov.add_box(mvex)

    # trak
    trak = create_box_trak_mp4a(mp4a_info)
    moov.add_box(trak)

    return moov


def create_moov_ac3(ac3_info):
    moov = MOOVBox()

    # mvhd
    scale_from = ac3_info.timescale
    scale_to = MOVIE_TIMESCALE
    dur_media = int((ac3_info.duration * scale_to) / scale_from)
    mvhd = MVHDBox(MOVIE_TIMESCALE, dur_media, ac3_info.track_id + 1)
    moov.add_box(mvhd)

    # mvex/trex
    trex = TREXBox(ac3_info.track_id)
    mvex = MVEXBox()
    mvex.add_box(trex)
    moov.add_box(mvex)

    # trak
    trak = create_box_trak_ac3(ac3_info)
    moov.add_box(trak)

    return moov


def create_moov_mp4s(info):
    """Create subtitle movie box
    :param info: mp4s_info
    """

    moov = MOOVBox()

    # mvhd
    scale_from = info.timescale
    scale_to = MOVIE_TIMESCALE
    dur_media = int((info.duration * scale_to) / scale_from)
    mvhd = MVHDBox(MOVIE_TIMESCALE, dur_media, info.track_id + 1)
    moov.add_box(mvhd)

    # mvex/trex
    trex = TREXBox(info.track_id)
    mvex = MVEXBox()
    mvex.add_box(trex)
    moov.add_box(mvex)

    # trak
    trak = create_box_trak_mp4s(info)
    moov.add_box(trak)

    return moov


def create_moof(segment_no, track_id, samples, encryptor=None):
    mfhd = MFHDBox(segment_no)
    moof = MOOFBox()
    moof.add_box(mfhd)

    saiz = None
    senc = None

    if encryptor:
        sample_aux_data = encryptor.encrypt(samples)
        default_sample_info_size = 8
        saiz = SAIZBox(default_sample_info_size)
        senc = SENCBox(default_sample_info_size)
        for sample in sample_aux_data:
            # print(hex(sample.iv))
            senc.add_sample(sample.iv, sample.subsamples)

    traf = TRAFBox()
    moof.add_box(traf)

    # tfhd
    tfhd = TFHDBox(track_id)
    traf.add_box(tfhd)

    # tfdt
    tfdt = TFDTBox(samples[0].time)
    traf.add_box(tfdt)

    # encryption boxes
    if saiz:
        traf.add_box(saiz)
        # 16 bytes senc header and 20 bytes saio
        saio = SAIOBox(moof.size() + 16 + 20)
        traf.add_box(saio)

    if senc:
        traf.add_box(senc)

    # Add samples
    trun = TRUNBox(0)
    for sample in samples:
        trun.add_sample(sample.duration,
                        sample.size,
                        sample.sync,
                        sample.time_offset)
    traf.add_box(trun)

    # set data_offset in trun
    moof_size = moof.size()
    moof_header_size = 8
    trun.set_data_offset(moof_size + moof_header_size)

    return moof


def create_mdat(samples):
    mdat = MDATBox()
    for sample in samples:
        mdat.add_data(sample.data)
    return mdat


def create_ftyp():
    ftyp = FTYPBox(b'cmfc', 0, [b'iso9', b'dash'])
    return ftyp


def create_styp():
    ftyp = FTYPBox(b'cmfs', 0, [b'iso9', b'dash'], styp=True)
    return ftyp
