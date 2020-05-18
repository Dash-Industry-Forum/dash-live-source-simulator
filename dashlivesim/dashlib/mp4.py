"""
MP4 box parser

This file originates from the DASH Industry Forum, downloaded from here:
https://github.com/Dash-Industry-Forum/media-tools/tree/master/python/content_analyzers
"""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and
# contributor rights, including patent rights, and no such rights are granted
# under this license.
#
# Copyright (c) 2016, Dash Industry Forum.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#  * Redistributions of source code must retain the above copyright notice,
#  this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation
#  and/or other materials provided with the distribution.
#  * Neither the name of Dash Industry Forum nor the names of its
#  contributors may be used to endorse or promote products derived from this
#  software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS AS IS
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#  ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
#  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.


import base64
import bisect
from collections import namedtuple
import functools
import itertools
from struct import Struct
import struct

from dashlivesim.dashlib import bitreader

REGISTERED_BOXES = {}
CONTAINER_BOXES = set([b'root',
                       b'moov',
                       b'moof',
                       b'trak',
                       b'traf',
                       b'tfad',
                       b'mvex',
                       b'mdia',
                       b'minf',
                       b'dinf',
                       b'stbl',
                       b'mfra',
                       b'udta',
                       # b'meta',
                       b'stsd',
                       b'sinf',
                       b'schi',
                       b'encv',
                       b'enca',
                       b'avc1',
                       b'hev1',
                       b'hvc1',
                       b'mp4a',
                       b'ac_3',
                       b'ec_3',
                       b'vttc'])


UNPACK_U32 = Struct('>I').unpack
UNPACK_U64 = Struct('>Q').unpack
UNPACK_SIZE_TYPE = Struct('>I4s').unpack


def parse_generator(data):
    """ parse__generator """
    offset = 0
    fmt = yield None
    while offset < len(data):
        ret = struct.unpack_from(fmt, data, offset)
        offset += struct.calcsize(fmt)
        fmt = (yield ret) or fmt


def fomrated_parse_generator(data, fmt=''):
    """ parse__generator """
    offset = 0
    while offset < len(data):
        ret = struct.unpack_from(fmt, data, offset)
        offset += struct.calcsize(fmt)
        fmt = (yield ret) or fmt


def match_attribute(obj, crit):
    """ match_attribute """
    key, value = crit.split(b'=')
    obj_value = getattr(obj, key.decode())
    return str(obj_value) == value.decode()


def match_box(obj, criteria='xxxx'):
    """ match_box """
    if len(criteria) == 4:
        return obj.type == criteria
    elif criteria.find(b'[') != -1:
        # assume 'atom[attr=val]' notation
        return obj.type == criteria[:4] and match_attribute(obj,
                                                            criteria[5:-1])


class box:
    def __init__(self, fmap, box_type, size, offset, parent=None):
        self.fmap = fmap
        self.type = box_type
        self.size = size
        self.offset = offset
        self.children = []
        self.parent = parent

    @property
    def endpos(self):
        return self.offset + self.size

    @property
    def childpos(self):
        return self.offset + 8

    @property
    def raw_data(self):
        """Return the raw data for this box (including size and type)."""
        return self.fmap[self.offset:self.offset + self.size]

    @property
    def is_container(self):
        return self.type in CONTAINER_BOXES or self.__class__ == mp4

    @property
    def is_unparsed(self):
        return self.is_container and not self.children and self.size >= 16

    @property
    def root(self):
        root = self
        while root.parent:
            root = root.parent
        return root

    @property
    def path(self):
        if self.parent:
            path = b'.'.join((self.parent.path, self.type))
        else:
            path = b''

        if path.startswith(b'.'):
            path = path[1:]

        return path

    def find_all(self, path):
        return self.find(path, return_first=False)

    def find(self, path, return_first=True):
        # unrolled lookup for most common use-case
        if len(path) == 4:
            if (not self.children and self.size >= 16 and (
                    self.type in CONTAINER_BOXES or self.__class__ == mp4)):
                self.parse_children(recurse=False)

            if return_first:
                for child in self.children:
                    if child.type == path:
                        return child
                return []
            else:
                return [c for c in self.children if c.type == path]

        # general find algorithm
        queue = [(self, path.split(b'.'))]
        matches = []
        while queue:
            obj, parts = queue.pop(0)
            # check if children are parsed
            if obj.is_unparsed:
                obj.parse_children(recurse=False)

            # matching child?
            if parts[0]:
                if len(parts[0]) == 4:
                    matching_children = [c for c in obj.children
                                         if c.type == parts[0]]
                else:
                    matching_children = filter(functools.partial(
                        match_box, criteria=parts[0]), obj.children)
            else:
                matching_children = [obj.parent]

            if matching_children:
                if len(parts) == 1:
                    matches += matching_children

                    if return_first:
                        return matches[0]
                else:
                    new_items = [(child, parts[1:])
                                 for child in matching_children]
                    queue = new_items + queue
                    # for child in matching_children:
                    #     queue.append((child, parts[1:]))

        return matches

    def parse_children(self, stops=None, recurse=True):
        if not self.is_container:
            return

        if not stops:
            stops = []

        next_offset = self.childpos
        end_offset = self.offset + self.size

        while True:
            box_class = box
            size, box_type = UNPACK_SIZE_TYPE(self.fmap[next_offset:
                                                        next_offset + 8])

            # Need to set allowed characters for some boxes
            if box_type == b'ac-3':
                box_type = b'ac_3'
            elif box_type == b'ec-3':
                box_type = b'ec_3'

            if size == 1:  # Extended size
                size = UNPACK_U64(self.fmap[next_offset + 8:
                                            next_offset + 16])[0]
            if size > self.size or size < 8:
                print(f"WARNING: Box '{box_type}' in '{self.path}' at offset "
                      f"{next_offset} has faulty size {size} "
                      f"(> {self.size - 7} or < 8)")
                # raise Exception
                return

            normalized_box_type = box_type.replace(b' ', b'_').decode()
            box_class_name = f"{normalized_box_type}_box"
            if box_class_name in REGISTERED_BOXES:
                box_class = REGISTERED_BOXES[box_class_name]
            else:
                # print('no box:', box_class_name)
                pass

            new_box = box_class(self.fmap, box_type, size, next_offset, self)
            self.children += [new_box]
            # next_offset = new_box.endpos
            next_offset += size

            if recurse and new_box.is_container:
                new_box.parse_children(stops, recurse)

            for stop in stops:
                if stop(new_box):
                    return

            if next_offset >= end_offset:
                break

    def __str__(self):
        old = object.__str__(self)
        replacement = f"{self.path}' [{self.offset}:{self.size}] object at"
        return old.replace("object at", replacement)


class full_box(box):
    def __init__(self, *args):
        super().__init__(*args)
        if self.type == b'uuid':
            self.extended_type = self.fmap[self.offset + 8:self.offset + 24]
            self.version = struct.unpack(
                'B', self.fmap[self.offset + 24:self.offset + 25])[0]
            self.flags = struct.unpack(
                '>i', b'\x00' +
                self.fmap[self.offset + 25:self.offset + 28])[0]
        else:
            self.version = struct.unpack(
                'B', self.fmap[self.offset + 8:self.offset + 9])[0]
            self.flags = struct.unpack(
                '>i', b'\x00' + self.fmap[self.offset + 9:self.offset + 12])[0]


class bridged_box:
    def __init__(self, start, end):
        assert start.fmap == end.fmap

        self.start = start
        self.end = end
        self.fmap = start.fmap
        self.offset = start.offset
        self.size = end.offset + end.size - start.offset
        self.type = f"{start.type}->{end.type}"


class mp4(box):
    def __init__(self,
                 fmap,
                 size=0,
                 stops=None,
                 recurse=True,
                 offset=0,
                 key=None,
                 encrypted=False):
        self.key = key
        self.encrypted = encrypted

        if not stops:
            stops = []

        if not size:
            size = len(fmap)
        super().__init__(fmap, b'root', size, offset)
        if recurse:
            self.parse_children(stops=stops, recurse=recurse)

    def get_video_info(self):
        box_ = self.find(b'moov.trak.mdia.minf.vmhd')
        if not box_:
            return None, 0
        timescale = box_.parent.parent.find(b'mdhd').timescale
        track = box_.parent.parent.parent.find(b'tkhd').track_id
        return track, timescale

    def get_audio_info(self):
        box_ = self.find(b'moov.trak.mdia.minf.smhd')
        if not box:
            return None, 0
        timescale = box_.parent.parent.find(b'mdhd').timescale
        track = box_.parent.parent.parent.find(b'tkhd').track_id
        return track, timescale

    def get_timed_text_info(self):
        box_ = self.find(b'moov.trak.mdia.minf.nmhd')
        if not box:
            return None, 0
        timescale = box_.parent.parent.find(b'mdhd').timescale
        track = box_.parent.parent.parent.find(b'tkhd').track_id
        return track, timescale

    @property
    def childpos(self):
        return self.offset


class moov_box(box):
    def __init__(self, fmap, box_type, size, offset, parent=None):
        super().__init__(fmap, box_type, size, offset, parent)


class mvhd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        mvhd_format = Struct('>QQIQ' if self.version else '>IIII')
        data = self.fmap[self.offset + 12:self.offset + 12 + mvhd_format.size]
        (self.creation_time,
         self.modification_time,
         self.timescale,
         self.duration) = mvhd_format.unpack(data)


class pssh_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.system_id = self.fmap[self.offset + 12:self.offset + 28].hex()
        o = 28

        self.kids = []
        if self.version > 0:
            KID_count = UNPACK_U32(self.fmap[self.offset + o:
                                             self.offset + o + 4])[0]
            o += 4
            for k in range(KID_count):
                kid = self.fmap[self.offset + o:self.offset + o + 16].hex()
                o += 16
                self.kids.append(kid)

        self.data_size = UNPACK_U32(self.fmap[self.offset + o:
                                              self.offset + o + 4])[0]
        o += 4

    # NOTE: Uncomment this code if PSSH should be parsed as a box container
    @property
    def childpos(self):
        return self.offset + 32


class saiz_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def default_sample_info_size(self):
        offset = 12
        if self.flags and 1:
            offset += 8

        return struct.unpack('>B', self.fmap[self.offset + offset:
                                             self.offset + offset + 1])[0]

    @property
    def sample_count(self):
        offset = 13
        if self.flags and 1:
            offset += 8

        return struct.unpack('>I', self.fmap[self.offset + offset:
                                             self.offset + offset + 4])[0]

    def sample_info_size(self, index):
        if self.default_sample_info_size != 0:
            return self.default_sample_info_size

        info_offset_base = 17
        if self.flags and 1:
            info_offset_base += 8

        sample_offset = self.offset + info_offset_base + index

        return struct.unpack('>B', self.fmap[sample_offset:
                                             sample_offset + 1])[0]


class saio_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def entry_count(self):
        offset = 12
        if self.flags and 1:
            offset += 8

        return struct.unpack('>I', self.fmap[self.offset + offset:
                                             self.offset + offset + 4])[0]

    def entry_offset(self, index):
        offset = 16
        if self.flags and 1:
            offset += 8
            offset += index * 8
            return struct.unpack('>Q', self.fmap[self.offset + offset:
                                                 self.offset + offset + 8])[0]
        else:
            offset += index * 4
            return struct.unpack('>I', self.fmap[self.offset + offset:
                                                 self.offset + offset + 4])[0]


class sbgp_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def grouping_type(self):
        return self.fmap[self.offset + 12:self.offset + 16]

    @property
    def entries(self):
        return struct.unpack('>I', self.fmap[self.offset + 16:
                                             self.offset + 20])[0]

    def group_entry(self, index):
        base_offset = 20 + (self.version and 4 or 0)
        entry_offset = base_offset + 8 * index
        if entry_offset > self.size:
            return 0, 0

        offset = self.offset + entry_offset
        sample_count = struct.unpack('>I', self.fmap[offset:offset + 4])[0]
        group_description_index = struct.unpack(
            '>I', self.fmap[offset + 4:offset + 8])[0]

        return sample_count, group_description_index


class sgpd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def grouping_type(self):
        return self.fmap[self.offset + 12:self.offset + 16]

    @property
    def entries(self):
        o = (self.version and 4 or 0)
        return struct.unpack('>I', self.fmap[self.offset + o + 16:
                                             self.offset + o + 20])[0]

    def entry(self, index):
        base_offset = 20 + (self.version and 4 or 0)
        entry_offset = base_offset + 20 * index
        if entry_offset > self.size:
            return 0, 0, ''

        offset = self.offset + entry_offset

        is_encrypted = struct.unpack('>i', b'\x00' + self.fmap[offset:
                                                               offset + 3])[0]
        iv_size = struct.unpack('>b', self.fmap[offset + 3:offset + 4])[0]

        kid = self.fmap[offset + 4:offset + 20]

        return is_encrypted, iv_size, kid

    def entry_data(self, index):
        base_offset = 20 + (self.version and 4 or 0)
        entry_offset = base_offset + 20 * index
        if entry_offset > self.size:
            return ''

        offset = self.offset + entry_offset
        return self.fmap[offset:offset + 20]


class senc_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.sample_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                 self.offset + 16])[0]

        struct = Struct(f'>{self.sample_count}Q')
        sample_data = struct.unpack(self.fmap[self.offset + 16:
                                              self.offset + 16 + struct.size])
        self.samples = [hex(iv) for iv in sample_data]
        # TODO: subsamples


class genc_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        self._sample_map = {}

    def _init_sample_map_from_sbgp(self, tenc):
        sbgp = self.get_sibling('sbgp')
        if not sbgp:
            return
        sgpd = self.get_sibling('sgpd')

        entry_index = 0
        for i in range(sbgp.entries):
            count, group_index = sbgp.group_entry(i)
            if group_index == 0:
                # No group. Use default tenc values
                enc = tenc.is_encrypted
                iv_size = tenc.iv_size
                kid = tenc.key_id
            else:
                # group defined. use values from sgpd
                enc, iv_size, kid = sgpd.entry(group_index - 1)

            for sample_index in range(count):
                self._sample_map[entry_index + sample_index] = (enc,
                                                                iv_size,
                                                                kid)
            entry_index += count

    def _init_sample_map(self):
        self._sample_map = {}

        tfhd = self.get_sibling('tfhd')
        tenc = self.get_tenc_for_track_id(tfhd.track_id)

        self._init_sample_map_from_sbgp(tenc)

        saiz = self.get_sibling('saiz')

        # saio = self.get_sibling('saio')
        # moof = self.get_ancestor('moof')
        # sample_offset = moof.offset + saio.entry_offset(0)

        for i in range(saiz.sample_count):
            #  sample_info_size = saiz.sample_info_size(i)
            if i not in self._sample_map:
                self._sample_map[i] = (tenc.is_encrypted,
                                       tenc.iv_size,
                                       tenc.key_id)
            #  sample_offset += sample_info_size

    def sample_encrypted_info(self, index):
        if index in self._sample_map:
            is_enc, iv_size, kid = self._sample_map[index]
            return is_enc, iv_size, kid

        return (0, 0, '')

    def get_sibling(self, type_):
        box_list = self.parent.children
        for box_ in box_list:
            if box_.type == type_:
                return box_
        return None

    def get_ancestor(self, type_):
        p = self
        while p.parent:
            p = p.parent
            if p.type == type_:
                return p
        return None

    def get_tenc_for_track_id(self, track_id):
        trak_boxes = self.root.find_all(b'moov.trak')
        for box_ in trak_boxes:
            tkhd = box_.find(b'tkhd')
            if tkhd.track_id == track_id:
                return box_.find(b'mdia.minf.stbl.stsd.sinf.schi.tenc')
        return None


class SampleEntry(box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def data_reference_index(self):
        return struct.unpack('>H', self.fmap[self.offset + 14:
                                             self.offset + 16])[0]


def getDescriptorLen(i):
    tmp = i.send('>B')[0]
    len_ = 0
    while tmp & 0x80:
        len_ = ((len_ << 7) | (tmp & 0x7f))
        tmp = i.send('>B')[0]

    len_ = ((len_ << 7) | (tmp & 0x7f))

    return len_


class esds_box(box):
    def __init__(self, *args):
        super().__init__(*args)

        self.cfg = ''
        self.obj_type = b''
        self.stream_type = b''
        self.es_id = ''

        i = parse_generator(self.fmap[self.offset + 8:
                                      self.offset + self.size])
        next(i)  # prime
        i.send('>I')[0]
        tag1 = i.send('>B')[0]

        if tag1 == 3:
            descriptor_len = getDescriptorLen(i)
            self.es_id = i.send('>B')[0] << 8
            self.es_id |= i.send('>B')[0]
            i.send('>B')[0]

            tag2 = i.send('>B')[0]

            if tag2 == 4:
                descriptor_len = getDescriptorLen(i)

                self.obj_type = i.send('>B')[0]
                self.stream_type = i.send('>B')[0]

                i.send('>B')[0]
                i.send('>B')[0]

                i.send('>I')[0]
                i.send('>I')[0]
                i.send('>B')[0]

                tag3 = i.send('>B')[0]

                if tag3 == 5:

                    descriptor_len = getDescriptorLen(i)
                    cfg = bytearray()
                    for _ in range(descriptor_len):
                        X = i.send('>B')[0]
                        cfg.append(X)

                    cfg_str = '0x' + cfg.hex()
                    self.cfg = cfg_str


class mp4a_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.channels = struct.unpack(
            '>h', self.fmap[self.offset + 24:self.offset + 26])[0]
        self.sample_size = struct.unpack(
            '>h', self.fmap[self.offset + 26:self.offset + 28])[0]
        self.sample_rate = struct.unpack(
            '>I', self.fmap[self.offset + 32:self.offset + 36])[0] >> 16

    @property
    def childpos(self):
        return self.offset + 36


class ac_3_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.channels = struct.unpack(
            '>h', self.fmap[self.offset + 24:self.offset + 26])[0]
        self.sample_size = struct.unpack(
            '>h', self.fmap[self.offset + 26:self.offset + 28])[0]
        self.sample_rate = struct.unpack(
            '>I', self.fmap[self.offset + 32:self.offset + 36])[0] >> 16

    @property
    def childpos(self):
        return self.offset + 36


class ec_3_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.channels = struct.unpack(
            '>h', self.fmap[self.offset + 24:self.offset + 26])[0]
        self.sample_size = struct.unpack(
            '>h', self.fmap[self.offset + 26:self.offset + 28])[0]
        self.sample_rate = struct.unpack(
            '>I', self.fmap[self.offset + 32:self.offset + 36])[0] >> 16

    @property
    def childpos(self):
        return self.offset + 36


class dac3_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.dec_info = self.fmap[self.offset + 8:self.offset + self.size]
        self.dec_info_hex = self.dec_info.hex()

        reader = bitreader(self.dec_info)

        self.fscod = reader.get_bits(2)
        self.bsid = reader.get_bits(5)
        self.bsmod = reader.get_bits(3)
        self.acmod = reader.get_bits(3)
        self.lfeon = reader.get_bits(1)
        self.bit_rate_code = reader.get_bits(5)


DEC3SubstreamEntry = namedtuple('DEC3SubstreamEntry',
                                ['fscod',
                                 'bsid',
                                 'asvc',
                                 'bsmod',
                                 'acmod',
                                 'lfeon',
                                 'num_dep_sub',
                                 'chan_loc'])


class dec3_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.dec_info = self.fmap[self.offset + 8:self.offset + self.size]
        self.dec_info_hex = self.dec_info.hex()

        reader = bitreader(self.dec_info)

        self.data_rate = reader.get_bits(13)

        # num_ind_sub shall be equal to the substreamID value of the last
        # independent substream of the bit stream.
        self.num_ind_sub = reader.get_bits(3)
        self.ind_sub_streams = []

        for i in range(self.num_ind_sub + 1):
            fscod = reader.get_bits(2)
            bsid = reader.get_bits(5)
            reader.get_bits(1)  # reserved
            asvc = reader.get_bits(1)
            bsmod = reader.get_bits(3)
            acmod = reader.get_bits(3)
            lfeon = reader.get_bits(1)
            reader.get_bits(3)  # reserved
            num_dep_sub = reader.get_bits(4)
            if num_dep_sub > 0:
                chan_loc = reader.get_bits(9)
            else:
                chan_loc = 0
                reader.get_bits(1)  # reserved

            self.ind_sub_streams.append(
                DEC3SubstreamEntry(fscod,
                                   bsid,
                                   asvc,
                                   bsmod,
                                   acmod,
                                   lfeon,
                                   num_dep_sub,
                                   chan_loc))


class enca_box(mp4a_box):
    def __init__(self, *args):
        super().__init__(*args)


class mp4v_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)
        self.width = struct.unpack(
            '>h', self.fmap[self.offset + 32:self.offset + 34])[0]
        self.height = struct.unpack(
            '>h', self.fmap[self.offset + 34:self.offset + 36])[0]


class avcx_box(SampleEntry):
    def __init__(self, *args):
        super().__init__(*args)

        self.width = struct.unpack(
            '>h', self.fmap[self.offset + 32:self.offset + 34])[0]
        self.height = struct.unpack(
            '>h', self.fmap[self.offset + 34:self.offset + 36])[0]
        self.res_hori = struct.unpack(
            '>I', self.fmap[self.offset + 36:self.offset + 40])[0]
        self.res_vert = struct.unpack(
            '>I', self.fmap[self.offset + 40:self.offset + 44])[0]
        self.frame_count = struct.unpack(
            '>h', self.fmap[self.offset + 48:self.offset + 50])[0]
        self.compressor = str(self.fmap[self.offset + 50:self.offset + 82])
        self.depth = struct.unpack(
            '>h', self.fmap[self.offset + 82:self.offset + 84])[0]

    @property
    def childpos(self):
        return self.offset + 86


class avc1_box(avcx_box):
    def __init__(self, *args):
        super().__init__(*args)


class avc3_box(avcx_box):
    def __init__(self, *args):
        super().__init__(*args)


class hev1_box(avcx_box):
    def __init__(self, *args):
        super().__init__(*args)


class hvc1_box(avcx_box):
    def __init__(self, *args):
        super().__init__(*args)


class encv_box(avc1_box):
    def __init__(self, *args):
        # look at format box to see which box to parse here
        # mp4v_box.__init__(self, *args)
        super().__init__(*args)


class avcC_box(box):
    """Extract SPS and PPS. Note, multiple PS are concatenated (not good)."""

    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 8:self.offset + self.size])
        next(i)  # prime

        self.version = i.send('>B')[0]
        self.profile_ind = i.send('>B')[0]
        self.profile_compat = i.send('>B')[0]
        self.level = i.send('>B')[0]
        self.dummy1 = i.send('>B')[0]
        tmp1 = i.send('>B')[0]
        self.num_sps = tmp1 & 0x1f

        sps_vec = bytearray()

        for j in range(0, self.num_sps):
            spsSize = i.send('>H')[0]
            for k in range(0, spsSize):
                x = i.send('>B')[0]
                sps_vec.append(x)

        sps_bin_str = sps_vec.hex()
        self.spsb64 = base64.b64encode(bytes.fromhex(sps_bin_str))

        tmp2 = i.send('>B')[0]
        self.num_pps = tmp2 & 0x1f
        pps_vec = bytearray()

        for j in range(0, self.num_pps):
            ppsSize = i.send('>H')[0]
            for k in range(ppsSize):
                x = i.send('>B')[0]
                pps_vec.append(x)

        pps_bin_str = pps_vec.hex()
        self.ppsb64 = base64.b64encode(bytes.fromhex(pps_bin_str))

        self.sps = sps_bin_str  # Hex string
        self.pps = pps_bin_str  # Hex string
        self.sps_bin = sps_vec  # Array of bytes
        self.pps_bin = pps_vec  # Array of bytes


def read_hex(reader, bytes):
    vec = bytearray()
    for i in range(bytes):
        vec.append(reader.send('>B')[0])
    hex_str = vec.hex()
    return hex_str


class hvcC_box(box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 8:self.offset + self.size])
        next(i)  # prime

        self.c = {}
        self.c['configuration_version'] = i.send('>B')[0]

        tmp = i.send('>B')[0]

        self.c['general_profile_space'] = (tmp >> 6) & 3
        self.c['general_tier_flag'] = (tmp >> 5) & 1
        self.c['general_profile_idc'] = tmp & 0x1f

        self.c['general_profile_compatibility_flags'] = read_hex(i, 4)
        self.c['general_constraint_indicator_flags'] = read_hex(i, 6)

        self.c['general_level_idc'] = i.send('>B')[0]

        tmp = i.send('>H')[0]
        self.c['min_spatial_segmentation_idc'] = tmp & 0xfff

        tmp = i.send('>B')[0]
        self.c['parallelismType'] = tmp & 0x3

        tmp = i.send('>B')[0]
        self.c['chromaFormat'] = tmp & 3

        tmp = i.send('>B')[0]
        self.c['bitDepthLumaMinus8'] = tmp & 7

        tmp = i.send('>B')[0]
        self.c['bitDepthChromaMinus8'] = tmp & 7

        self.c['avgFrameRate'] = i.send('>H')[0]

        tmp = i.send('>B')[0]

        self.c['constantFrameRate'] = (tmp >> 6) & 0x3
        self.c['numTemporalLayers'] = (tmp >> 3) & 0x7
        self.c['temporalIdNested'] = (tmp >> 2) & 0x1
        self.c['lengthSizeMinusOne'] = (tmp & 0x3)

        num_arrays = i.send('>B')[0]
        self.c['num_arrays'] = num_arrays
        self.c['array'] = []

        for j in range(num_arrays):
            tmp = i.send('>B')[0]
            a = {}
            a['array_completeness'] = (tmp >> 7) & 1
            a['NAL_unit_type'] = (tmp & 0x3f)
            a['NAL_units'] = []

            num_nal_units = i.send('>H')[0]
            for k in range(num_nal_units):
                nal_unit_length = i.send('>H')[0]
                nal_unit = read_hex(i, nal_unit_length)
                a['NAL_units'].append({'NAL_unit': nal_unit})

            self.c['array'].append(a)


class stsd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def entry_count(self):
        return struct.unpack(
            '>I', self.fmap[self.offset + 12:self.offset + 16])[0]

    @property
    def childpos(self):
        return self.offset + 16


class sinf_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class frma_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class schm_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        self.type = self.fmap[self.offset + 12:self.offset + 16]
        self.major_version = struct.unpack(
            '>H', self.fmap[self.offset + 16:self.offset + 18])[0]
        self.minor_version = struct.unpack(
            '>H', self.fmap[self.offset + 18:self.offset + 20])[0]


class schi_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class tenc_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

    @property
    def is_encrypted(self):
        return struct.unpack('>i', b'\x00' + self.fmap[self.offset + 12:
                                                       self.offset + 15])[0]

    @property
    def iv_size(self):
        return struct.unpack('>b', self.fmap[self.offset + 15:
                                             self.offset + 16])[0]

    @property
    def key_id(self):
        return self.fmap[self.offset + 16:self.offset + 32]


class tkhd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime
        self.creation_time = i.send(self.version and '>Q' or '>I')[0]
        self.modification_time = i.send(self.version and '>Q' or '>I')[0]
        self._track_id = i.send('>I')[0]
        i.send('>I')  # reserved
        self.duration = i.send(self.version and '>Q' or '>I')[0]

        for j in range(0, 13):
            # reserved, matrix etc
            i.send('>I')

        self.width = i.send('>I')[0] >> 16
        self.height = i.send('>I')[0] >> 16

    @property
    def track_id(self):
        return self._track_id


class mdhd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime
        self.creation_time = i.send(self.version and '>Q' or '>I')[0]
        self.modification_time = i.send(self.version and '>Q' or '>I')[0]
        self.timescale = i.send('>I')[0]
        self.duration = i.send(self.version and '>Q' or '>I')[0]
        lang = i.send('>H')[0]
        lang_1 = ((lang >> 10) & 0x1f) + 0x60
        lang_2 = ((lang >> 5) & 0x1f) + 0x60
        lang_3 = (lang & 0x1f) + 0x60
        self.language = bytes((lang_1, lang_2, lang_3)).decode()


class hdlr_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime
        i.send('>I')[0]  # pre_defined
        handler_type = ''
        for k in range(4):
            handler_type += chr(i.send('>B')[0])  # handler_type
        i.send('>I')[0]  # reserved
        i.send('>I')[0]  # reserved
        i.send('>I')[0]  # reserved

        rest = self.size - 12 - 5 * 4
        encoding_name = ''
        for k in range(rest):
            encoding_name += chr(i.send('>B')[0])

        self.handler_type = handler_type
        self.encoding_name = encoding_name


class moof_box(box):
    def __init__(self, fmap, box_type, size, offset, parent=None):
        super().__init__(fmap, box_type, size, offset, parent)

    def get_mdat(self):
        box_list = self.parent.children
        pindex = self.parent.children.index(self)
        while pindex < len(box_list):
            box = box_list[pindex]
            if box.type == b'mdat':
                return box
            pindex += 1

        return None


class trex_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        data = self.fmap[self.offset + 12:self.offset + 32]
        (self.track_id,
         self.default_sample_description_index,
         self.default_sample_duration,
         self.default_sample_size,
         self.default_sample_flags) = struct.unpack('>IIIII', data)


class mfhd_box(box):
    def __init__(self, *args):
        super().__init__(*args)
        self.seqno = UNPACK_U32(self.fmap[self.offset + 12:
                                          self.offset + 16])[0]

    def get_track_duration(self, track_id, timescale):
        truns = self.find(b'.traf.tfhd[track_id=%d]..trun' % track_id,
                          return_first=False)
        dur = sum([trun.total_duration for trun in truns])
        return dur / float(timescale)

    @property
    def video_duration(self):
        video_track, video_timescale = self.root.get_video_info()
        return self.get_track_duration(video_track, video_timescale)

    @property
    def audio_duration(self):
        audio_track, audio_timescale = self.root.get_audio_info()
        return self.get_track_duration(audio_track, audio_timescale)

    def get_track_sample_count(self, track_id):
        truns = self.find(b'.traf.tfhd[track_id=%d]..trun' % track_id,
                          return_first=False)
        return sum([trun.sample_count for trun in truns])

    @property
    def video_sample_count(self):
        track, timescale = self.root.get_video_info()
        return self.get_track_sample_count(track)

    @property
    def audio_sample_count(self):
        track, timescale = self.root.get_audio_info()
        return self.get_track_sample_count(track)


class tfhd_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.has_base_data_offset = self.flags & 0x0001
        self.has_sample_description_index = self.flags & 0x0002
        self.has_default_sample_duration = self.flags & 0x0008
        self.has_default_sample_size = self.flags & 0x0010
        self.has_default_sample_flags = self.flags & 0x0020

        self.base_data_offset = 0
        self.sample_description_index = 0
        self.default_sample_duration = 0
        self.default_sample_size = 0
        self.default_sample_flags = 0

        offset = 16

        if self.has_base_data_offset:
            self.base_data_offset = struct.unpack(
                '>Q', self.fmap[self.offset + offset:
                                self.offset + offset + 8])[0]
            offset = offset + 8

        if self.has_sample_description_index:
            self.sample_description_index = struct.unpack(
                '>I', self.fmap[self.offset + offset:
                                self.offset + offset + 4])[0]
            offset = offset + 4

        if self.has_default_sample_duration:
            self.default_sample_duration = struct.unpack(
                '>I', self.fmap[self.offset + offset:
                                self.offset + offset + 4])[0]
            offset = offset + 4

        if self.has_default_sample_size:
            self.default_sample_size = struct.unpack(
                '>I', self.fmap[self.offset + offset:
                                self.offset + offset + 4])[0]
            offset = offset + 4

        if self.has_default_sample_flags:
            self.default_sample_flags = struct.unpack(
                '>I', self.fmap[self.offset + offset:
                                self.offset + offset + 4])[0]
            offset = offset + 4

    @property
    def track_id(self):
        return struct.unpack(
            '>I', self.fmap[self.offset + 12:self.offset + 16])[0]


class trun_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.has_data_offset = self.flags & 0x0001
        self.has_first_sample_flags = self.flags & 0x0004
        self.has_sample_duration = self.flags & 0x0100
        self.has_sample_size = self.flags & 0x0200
        self.has_sample_flags = self.flags & 0x0400
        self.has_sample_composition_time_offset = self.flags & 0x0800
        self.first_cto = 0

        # self.sample_count = struct.unpack(
        #    '>I', self.fmap[self.offset + 12:self.offset + 16])[0]
        self.data_offset = 0
        self.first_sample_flags = 0
        # self.decorators = {'size':self.sample_count}

        self.sample_array_offset = 16
        if self.has_data_offset:
            self.data_offset = struct.unpack(
                '>i', self.fmap[self.offset + self.sample_array_offset:
                                self.offset + self.sample_array_offset + 4])[0]
            self.sample_array_offset += 4

        if self.has_first_sample_flags:
            self.first_sample_flags = struct.unpack(
                '>I', self.fmap[self.offset + self.sample_array_offset:
                                self.offset + self.sample_array_offset + 4])[0]
            self.sample_array_offset += 4

        self.sample_row_size = (
            (self.has_sample_duration and 4) +
            (self.has_sample_size and 4) +
            (self.has_sample_flags and 4) +
            (self.has_sample_composition_time_offset and 4))

        if self.has_sample_duration:
            self.total_duration = 0
            for i in range(self.sample_count):
                offset = (self.offset + self.sample_array_offset +
                          i * self.sample_row_size)
                self.total_duration += struct.unpack(
                    '>I', self.fmap[offset:offset + 4])[0]
        else:
            sample_duration = self.parent.find(b'tfhd').default_sample_duration
            self.total_duration = sample_duration * self.sample_count

        if self.has_sample_composition_time_offset:
            offset = (self.offset + self.sample_array_offset +
                      (self.has_sample_duration and 4) +
                      (self.has_sample_size and 4) +
                      (self.has_sample_flags and 4))
            self.first_cto = (struct.unpack('>i',  # always read as unsigned
                                            self.fmap[offset:offset + 4])[0])

    def get_durations(self, default_sample_duration):
        """Returns total duration of samples and presentation range as lowest
        and highest presentation time of samples.
        Returned presentation times values are relative to base media decode
        time of a segment.
        """
        if self.has_sample_duration:
            first_duration_offset = (self.offset + self.sample_array_offset)
            last_duration_offset = (first_duration_offset +
                                    self.sample_count * self.sample_row_size)
            durations = [struct.unpack('>I', self.fmap[offset:offset + 4])[0]
                         for offset in range(first_duration_offset,
                                             last_duration_offset,
                                             self.sample_row_size)]
            total_duration = sum(durations)

        else:
            if default_sample_duration is None:
                # We don't calculate without sample durations
                return 0, 0, 0

            total_duration = default_sample_duration * self.sample_count

        if self.has_sample_composition_time_offset:
            first_cto_offset = (self.offset + self.sample_array_offset +
                                (self.has_sample_duration and 4) +
                                (self.has_sample_size and 4) +
                                (self.has_sample_flags and 4))
            last_cto_offset = (first_cto_offset +
                               self.sample_count * self.sample_row_size)
            ctos = [struct.unpack('>i', self.fmap[offset:offset + 4])[0]
                    for offset in range(first_cto_offset,
                                        last_cto_offset,
                                        self.sample_row_size)]

            if self.has_sample_duration:
                first_duration = durations[0]
            else:
                first_duration = default_sample_duration
                durations = itertools.repeat(default_sample_duration)

            presentation_min = ctos[0]
            presentation_max = ctos[0] + first_duration
            decode_time = 0
            for duration, cto in zip(durations, ctos):
                presentation_time = decode_time + cto
                decode_time += duration
                if presentation_time < presentation_min:
                    presentation_min = presentation_time
                if presentation_time + duration > presentation_max:
                    presentation_max = presentation_time + duration

        else:
            presentation_min = 0
            presentation_max = total_duration

        return total_duration, presentation_min, presentation_max

    # @property
    # def has_data_offset(self):
    #    return self.flags & 0x0001

    # @property
    # def data_offset(self):
    #    return struct.unpack('>i',
    #        self.fmap[self.offset + self.sample_array_offset:
    #                  self.offset + self.sample_array_offset + 4])[0]

    @property
    def sample_count(self):
        return struct.unpack('>I', self.fmap[self.offset + 12:
                                             self.offset + 16])[0]

    def sample_entry(self, i):
        row = {}
        offset = (self.offset + self.sample_array_offset +
                  i * self.sample_row_size)
        if self.has_sample_duration:
            row['duration'] = struct.unpack(
                '>I', self.fmap[offset:offset + 4])[0]
            offset += 4
        if self.has_sample_size:
            row['size'] = struct.unpack(
                '>I', self.fmap[offset:offset + 4])[0]
            offset += 4
        if self.has_sample_flags:
            flags = struct.unpack('>I', self.fmap[offset:offset + 4])[0]
            row['flags'] = f"0x{flags:x}"
            offset += 4
        if self.has_sample_composition_time_offset:
            # Using >i to support v0 & v1 assuming small enough numbers
            row['time_offset'] = struct.unpack(
                '>i', self.fmap[offset:offset + 4])[0]
            offset += 4

        return row


class tfra_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        self.random_access_time = []
        self.random_access_moof_offset = []

    @property
    def track_id(self):
        return struct.unpack('>I',
                             self.fmap[self.offset + 12:self.offset + 16])[0]

    @property
    def length_size_of_traf_num(self):
        return (struct.unpack('>B',
                              self.fmap[self.offset + 19:
                                        self.offset + 20])[0] & 0x30) >> 4

    @property
    def length_size_of_trun_num(self):
        return (struct.unpack('>B',
                              self.fmap[self.offset + 19:
                                        self.offset + 20])[0] & 0x0C) >> 2

    @property
    def length_size_of_sample_num(self):
        return struct.unpack('>B',
                             self.fmap[self.offset + 19:
                                       self.offset + 20])[0] & 0x03

    @property
    def number_of_entry(self):
        return struct.unpack('>I',
                             self.fmap[self.offset + 20:self.offset + 24])[0]

    @property
    def end_time(self):
        if self.number_of_entry == 0:
            return 0

        # This is an approx. Assumes a full GOP.
        last_keyframe_time = self.entry(self.number_of_entry - 1)[0]
        prev_keyframe_time = self.entry(self.number_of_entry - 2)[0]
        return last_keyframe_time + (last_keyframe_time - prev_keyframe_time)

    def entry(self, index):
        intro_format, intro_length = self.version and ('>Q', 16) or ('>I', 8)
        row_length = (intro_length +
                      1 + self.length_size_of_traf_num +
                      1 + self.length_size_of_trun_num +
                      1 + self.length_size_of_sample_num)
        row_start = self.offset + 24 + (row_length * index)

        p = fomrated_parse_generator(
            self.fmap[row_start:row_start + row_length], intro_format)
        time = next(p)[0]
        moof_offset = next(p)[0]
        traf = p.send(['>B', '>H', '>BH', '>I']
                      [self.length_size_of_traf_num])[-1]
        trun = p.send(['>B', '>H', '>BH', '>I']
                      [self.length_size_of_trun_num])[-1]
        sample = p.send(['>B', '>H', '>BH', '>I']
                        [self.length_size_of_sample_num])[-1]

        return time, moof_offset, traf, trun, sample

    def parse_random_access_table(self):
        intro_format, intro_length = self.version and ('>QQ', 16) or ('>II', 8)
        row_length = (intro_length +
                      1 + self.length_size_of_traf_num +
                      1 + self.length_size_of_trun_num +
                      1 + self.length_size_of_sample_num)

        self.random_access_time = []
        self.random_access_moof_offset = []
        for i in range(self.number_of_entry):
            row_start = self.offset + 24 + (row_length * i)
            time, moof_offset = struct.unpack(
                intro_format, self.fmap[row_start:row_start + intro_length])

            if (not self.random_access_moof_offset or
                    self.random_access_moof_offset[-1] != moof_offset):
                self.random_access_time.append(time)
                self.random_access_moof_offset.append(moof_offset)

    def time_for_fragment(self, fragment):
        if not self.random_access_time:
            self.parse_random_access_table()

        if len(self.random_access_time) < fragment:
            return None

        return self.random_access_time[fragment - 1]

    def moof_offset_for_fragment(self, fragment):
        if not self.random_access_moof_offset:
            self.parse_random_access_table()

        if len(self.random_access_moof_offset) < fragment:
            return None, None

        offset = self.random_access_moof_offset[fragment - 1]
        size = 0

        if len(self.random_access_moof_offset) > fragment:
            size = self.random_access_moof_offset[fragment] - offset

        return offset, size

    def moof_offset_for_time(self, seek_time):
        if not self.random_access_moof_offset:
            self.parse_random_access_table()

        # float_time = seek_time/90000.0
        index = bisect.bisect_left(self.random_access_time, seek_time)
        index = max(index - 1, 0)
        return self.random_access_moof_offset[index]

    def time_for_moof_offset(self, offset):
        if not self.random_access_moof_offset:
            self.parse_random_access_table()

        index = self.random_access_moof_offset.index(offset)
        return self.random_access_time[index]

    @property
    def fragment_count(self):
        if not self.random_access_moof_offset:
            self.parse_random_access_table()

        return len(self.random_access_moof_offset)


class mfro_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.mfra_size = i.send('>I')[0]


class stbl_box(box):
    def __init__(self, *args):
        super().__init__(*args)


STTSEntry = namedtuple('STTSEntry', ['sample_count',
                                     'sample_delta',
                                     'cumulative_delta'])


class stts_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        self.entries = []
        self.lookup = []
        last_entry = None
        sample_index = 1
        cumulative_delta = 0

        struct = Struct(f'>{2 * self.entry_count}I')
        data = iter(struct.unpack(self.fmap[self.offset + 16:
                                            self.offset + 16 + struct.size]))

        for sample_count, sample_delta in zip(data, data):
            if last_entry:
                sample_index += last_entry.sample_count
                cumulative_delta += (last_entry.sample_count *
                                     last_entry.sample_delta)

            entry = STTSEntry(sample_count, sample_delta, cumulative_delta)

            self.entries.append(entry)
            self.lookup.append(sample_index)

            last_entry = entry

    def sample_time_and_duration(self, sample_number):
        # lookup entry, essentially the same as
        # entry_index = bisect.bisect_right(self.lookup, sample_number) - 1
        entry_index = 0
        upper_bound = self.entry_count
        while entry_index < upper_bound:
            index = (entry_index + upper_bound) // 2
            if sample_number < self.lookup[index]:
                upper_bound = index
            else:
                entry_index = index + 1
        entry_index -= 1

        start_sample = self.lookup[entry_index]
        entry = self.entries[entry_index]

        # calculate sample time based on constant sample durations from
        # looked-up entry
        sample_diff = sample_number - start_sample
        time = entry.cumulative_delta + sample_diff * entry.sample_delta
        duration = entry.sample_delta

        return time, duration


CTSSEntry = namedtuple('CTSSEntry', 'sample_count sample_offset')


class ctts_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        self.entries = []
        self.lookup = []
        last_entry = None
        sample_index = 1

        struct = Struct(f'>{2 * self.entry_count}I')
        data = iter(struct.unpack(self.fmap[self.offset + 16:
                                            self.offset + 16 + struct.size]))

        for sample_count, sample_offset in zip(data, data):
            entry = CTSSEntry(sample_count, sample_offset)

            if last_entry:
                sample_index += last_entry.sample_count

            self.entries.append(entry)
            self.lookup.append(sample_index)

            last_entry = entry

    def sample_offset(self, sample_number):
        # lookup entry, essentially the same as
        # entry_index = bisect.bisect_right(self.lookup, sample_number) - 1
        entry_index = 0
        upper_bound = self.entry_count
        while entry_index < upper_bound:
            index = (entry_index + upper_bound) // 2
            if sample_number < self.lookup[index]:
                upper_bound = index
            else:
                entry_index = index + 1
        entry_index -= 1

        return self.entries[entry_index].sample_offset


class stss_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        struct = Struct(f'>{self.entry_count}I')
        self.entries = struct.unpack(self.fmap[self.offset + 16:
                                               self.offset + 16 + struct.size])

    def has_index(self, index):
        return index in self.entries


class stsz_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.sample_size = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        self.sample_count = UNPACK_U32(self.fmap[self.offset + 16:
                                                 self.offset + 20])[0]

        if self.sample_size == 0:
            struct = Struct(f'>{self.sample_count}I')
            self.sample_sizes = struct.unpack(
                self.fmap[self.offset + 20:
                          self.offset + 20 + struct.size])

            def accumulate(sample_sizes):
                total = 0
                for x in sample_sizes:
                    yield total
                    total += x

            self.sample_sizes_sum = list(accumulate(self.sample_sizes))

        else:
            self.sample_sizes = ()
            self.sample_sizes_sum = ()

    def sample_size_and_offset(self, sample_number, index_in_chunk,
                               chunk_offset):
        if self.sample_size:
            offset = chunk_offset + self.sample_size * index_in_chunk
            size = self.sample_size
        else:
            offset_in_chunk = (self.sample_sizes_sum[sample_number - 1] -
                               self.sample_sizes_sum[sample_number -
                                                     index_in_chunk - 1])
            offset = chunk_offset + offset_in_chunk
            size = self.sample_sizes[sample_number - 1]

        return size, offset


STSCEntry = namedtuple('STSCEntry', ['first_chunk',
                                     'samples_per_chunk',
                                     'sample_description_index'])


class stsc_box(full_box):

    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        self.entries = []
        self.lookup = []
        last_entry = None
        sample_index = 1

        struct = Struct(f'>{3 * self.entry_count}I')
        data = iter(struct.unpack(self.fmap[self.offset + 16:
                                            self.offset + 16 + struct.size]))

        for entry_tuple in zip(data, data, data):
            entry = STSCEntry(*entry_tuple)

            if last_entry:
                chunk_delta = entry.first_chunk - last_entry.first_chunk
                sample_index += chunk_delta * last_entry.samples_per_chunk

            self.entries.append(entry)
            self.lookup.append(sample_index)

            last_entry = entry

    def chunk_and_index(self, sample_number):
        # lookup entry, essentially the same as
        # entry_index = bisect.bisect_right(self.lookup, sample_number) - 1
        entry_index = 0
        upper_bound = self.entry_count
        while entry_index < upper_bound:
            index = (entry_index + upper_bound) // 2
            if sample_number < self.lookup[index]:
                upper_bound = index
            else:
                entry_index = index + 1
        entry_index -= 1

        start_sample = self.lookup[entry_index]
        entry = self.entries[entry_index]
        sample_diff = sample_number - start_sample
        chunk = entry.first_chunk + sample_diff // entry.samples_per_chunk
        index = sample_diff % entry.samples_per_chunk
        return chunk, index


class stco_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        struct = Struct(f'>{self.entry_count}I')
        self.entries = struct.unpack(self.fmap[self.offset + 16:
                                               self.offset + 16 + struct.size])

    def chunk_offset(self, chunk):
        try:
            return self.entries[chunk - 1]
        except IndexError:
            return 0


class co64_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        self.entry_count = UNPACK_U32(self.fmap[self.offset + 12:
                                                self.offset + 16])[0]

        struct = Struct(f'>{self.entry_count}Q')
        self.entries = struct.unpack(self.fmap[self.offset + 16:
                                               self.offset + 16 + struct.size])

    def chunk_offset(self, chunk):
        try:
            return self.entries[chunk - 1]
        except IndexError:
            return 0


class ftyp_box(box):
    def __init__(self, *args):
        super().__init__(*args)

        i = parse_generator(self.fmap[self.offset + 8:self.offset + self.size])
        next(i)  # prime

        self.major_brand = (i.send('>c')[0] + i.send('>c')[0] +
                            i.send('>c')[0] + i.send('>c')[0])
        self.minor_version = i.send('>I')[0]
        self.brands = []

        num_brands = (self.size - 16) // 4
        for j in range(num_brands):
            self.brands.append(i.send('>c')[0] + i.send('>c')[0] +
                               i.send('>c')[0] + i.send('>c')[0])


class styp_box(box):
    def __init__(self, *args):
        super().__init__(*args)

        i = parse_generator(self.fmap[self.offset + 8:self.offset + self.size])
        next(i)  # prime

        self.major_brand = (i.send('>c')[0] + i.send('>c')[0] +
                            i.send('>c')[0] + i.send('>c')[0])
        self.minor_version = i.send('>I')[0]
        self.brands = []

        num_brands = (self.size - 16) // 4
        for j in range(num_brands):
            self.brands.append(i.send('>c')[0] + i.send('>c')[0] +
                               i.send('>c')[0] + i.send('>c')[0])


class tfma_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.entry_count = i.send('>I')[0]

        self.entries = []
        for j in range(self.entry_count):
            segment_duration = i.send(self.version and '>Q' or '>I')[0]
            media_time = i.send(self.version and '>q' or '>i')[0]
            media_rate_integer = i.send('>H')[0]
            media_rate_fraction = i.send('>H')[0]
            self.entries.append({'segment-duration': segment_duration,
                                 'media-time': media_time,
                                 'media-rate-integer': media_rate_integer,
                                 'media-rate-fraction': media_rate_fraction})


class tfad_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class sidx_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.reference_track_id = i.send('>I')[0]
        self.timescale = i.send('>I')[0]
        self.first_pres_time = i.send(self.version and '>Q' or '>I')[0]
        self.first_offset = i.send(self.version and '>Q' or '>I')[0]
        self.reserved = i.send('>H')[0]
        self.reference_count = i.send('>H')[0]

        self.references = []
        for j in range(self.reference_count):
            byte_1 = i.send('>I')[0]
            referenced_type = (int(byte_1) >> 31) & 0x01
            referenced_size = int(byte_1) & 0x7fffffff
            subsegment_duration = i.send('>I')[0]
            byte_3 = i.send('>I')[0]
            starts_with_sap = (int(byte_3) >> 31) & 0x01
            sap_type = (int(byte_3) >> 28) & 0x07
            sap_delta_time = int(byte_3) & 0x0fffffff

            ref_type = b'moof'
            if int(referenced_type) == 0:  # moof reference
                ref_type = b'moof'
            else:
                ref_type = b'sidx'

            self.references.append({'referenced-type': ref_type,
                                    'referenced-size': referenced_size,
                                    'subsegment-duration': subsegment_duration,
                                    'starts-with-sap': starts_with_sap,
                                    'sap-type': sap_type,
                                    'sap-delta-time': sap_delta_time})


class udta_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class meta_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class tfdt_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.decode_time = i.send(self.version and '>Q' or '>I')[0]


class afra_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        byte1 = i.send('>B')[0]
        self.long_ids = (byte1 >> 7) & 0x01
        self.long_offsets = (byte1 >> 6) & 0x01
        self.global_entries = (byte1 >> 5) & 0x01
        self.reserved = (byte1 & 0x1f)
        self.time_scale = i.send('>I')[0]
        self.entry_count = i.send('>I')[0]
        self.entries = []
        for j in range(0, self.entry_count):
            time = i.send('>Q')[0]
            offset = i.send(self.long_offsets and '>Q' or '>I')[0]
            self.entries.append({'time': time, 'offset': offset})

        self.global_entry_count = 0
        self.global_entries_list = []
        if self.global_entries:
            self.global_entry_count = i.send('>I')[0]
        for j in range(0, self.global_entry_count):
            time = i.send('>Q')[0]
            segment = i.send(self.long_ids and '>I' or '>H')[0]
            fragment = i.send(self.long_ids and '>I' or '>H')[0]
            afra_offset = i.send(self.long_ids and '>Q' or '>I')[0]
            offset_from_afra = i.send(self.long_ids and '>Q' or '>I')[0]
            self.global_entries_list.append({
                'time': time,
                'segment': segment,
                'fragment': fragment,
                'afra_offset': afra_offset,
                'offset_from_afra': offset_from_afra})


class asrt_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.quality_entry_count = i.send('>B')[0]
        self.qualities = []
        for j in range(0, self.quality_entry_count):
            self.qualities.append(read_string(i))

        self.segment_run_entry_count = i.send('>I')[0]
        self.segments = []
        for j in range(0, self.segment_run_entry_count):
            f_seg = i.send('>I')[0]
            frag_per_seg = i.send('>I')[0]
            self.segments.append((f_seg, frag_per_seg))


class afrt_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.time_scale = i.send('>I')[0]

        self.quality_entry_count = i.send('>B')[0]
        self.qualities = []
        for j in range(0, self.quality_entry_count):
            self.qualities.append(read_string(i))

        self.fragment_run_entry_count = i.send('>I')[0]
        self.fragments = []
        for j in range(0, self.fragment_run_entry_count):
            first_fragment = i.send('>I')[0]
            first_fragment_timestamp = i.send('>Q')[0]
            fragment_duration = i.send('>I')[0]
            discontinuity_value = ''
            if fragment_duration == 0:
                discontinuity_indicator = i.send('>B')[0]
                if discontinuity_indicator == 0:
                    discontinuity_value = ("discontinuity_indicator: "
                                           "end of pres")
                elif discontinuity_indicator == 1:
                    discontinuity_value = ("discontinuity_indicator: "
                                           "frag numbering")
                elif discontinuity_indicator == 2:
                    discontinuity_value = ("discontinuity_indicator: "
                                           "timestamps")
                elif discontinuity_indicator == 3:
                    discontinuity_value = ("discontinuity_indicator: "
                                           "timestamps + frag numbering")
                else:
                    discontinuity_value = (f"unknown "
                                           f"({discontinuity_indicator})")
            self.fragments.append(
                f"first_fragment: {first_fragment} "
                f"first_fragment_timestamp: {first_fragment_timestamp} "
                f"fragment_duration: {fragment_duration} "
                f"{discontinuity_value}")


def read_string(parser):
    msg = ''
    byte = parser.send('>B')[0]
    while byte != 0:
        msg = msg + chr(byte)
        byte = parser.send('>B')[0]
    return msg


class abst_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)
        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        self.bootstrap_info_version = i.send('>I')[0]
        byte2 = i.send('>B')[0]
        self.profile = (byte2 >> 6) & 0x03
        self.live = (byte2 >> 5) & 0x01
        self.update = (byte2 >> 4) & 0x01
        self.time_scale = i.send('>I')[0]
        self.current_media_time = i.send('>Q')[0]
        self.smtp_time_code_offset = i.send('>Q')[0]
        self.movie_identifier = read_string(i)

        o = 38 + len(self.movie_identifier)

        self.server_entry_count = i.send('>B')[0]
        o = o + 1
        self.servers = []
        for j in range(0, self.server_entry_count):
            server = read_string(i)
            self.servers.append(server)
            o = o + 1 + len(server)

        self.quality_entry_count = i.send('>B')[0]
        o = o + 1
        self.qualities = []
        for j in range(0, self.server_entry_count):
            quality = read_string(i)
            self.qualities.append(quality)
            o = o + 1 + len(quality)

        self.drm_data = read_string(i)
        self.meta_data = read_string(i)
        o = o + 2 + len(self.drm_data) + len(self.meta_data)

        # Segment run
        self.segment_run_table_count = i.send('>B')[0]
        o = o + 1
        self.segment_boxes = []
        for j in range(0, self.segment_run_table_count):
            box_size = i.send('>I')[0]
            box_type = i.send('>4s')[0]
            olas_box = asrt_box(self.fmap, box_type, box_size,
                                self.offset + o, self)
            self.segment_boxes.append(olas_box)
            o = o + box_size

            for k in range(0, box_size - 8):
                i.send('>B')[0]

        # Fragment run
        self.fragment_run_table_count = i.send('>B')[0]
        o = o + 1
        self.fragment_boxes = []
        for j in range(0, self.fragment_run_table_count):
            box_size = i.send('>I')[0]
            box_type = i.send('>4s')[0]
            olas_box = afrt_box(self.fmap, box_type, box_size,
                                self.offset + o, self)
            self.fragment_boxes.append(olas_box)
            o = o + box_size

            for _ in range(0, box_size - 8):
                i.send('>B')[0]


class mdat_box(box):
    def __init__(self, *args):
        super().__init__(*args)


class payl_box(box):
    def __init__(self, *args):
        super().__init__(*args)
        self.cue_text = self.fmap[self.offset + 8:self.offset + self.size]


class tfxd_box:
    def __init__(self, data, version, flags):
        self.data = data
        self.version = version
        self.flags = flags

        i = parse_generator(data)
        next(i)  # prime

        self.time = i.send(self.version and '>Q' or '>I')[0]
        self.duration = i.send(self.version and '>Q' or '>I')[0]


class tfrf_box:
    def __init__(self, data, version, flags):
        self.data = data
        self.version = version
        self.flags = flags
        self.times = []
        self.durations = []

        i = parse_generator(data)
        next(i)  # prime

        self.num_entries = i.send('>B')[0]

        for k in range(self.num_entries):
            self.times.append(i.send(self.version and '>Q' or '>I')[0])
            self.durations.append(i.send(self.version and '>Q' or '>I')[0])


class sampleEncryption_box:
    def __init__(self, data, version, flags, iv_size=8):
        self.data = data
        self.version = version
        self.flags = flags
        self.iv_size = iv_size


class trackEncryption_box:
    def __init__(self, data, version, flags):
        self.data = data
        self.version = version
        self.flags = flags


class pssh_uuid_box:
    def __init__(self, data, version, flags):
        self.data = data
        self.version = version
        self.flags = flags


tfxdGuid = '6D1D9B0542D544E680E2141DAFF757B2'
tfrfGuid = 'D4807EF2CA3946958E5426CB9E46A79F'
sampleEncryptionGuid = 'A2394F525A9B4F14A2446C427C648DF4'
trackEncryptionGuid = "8974DBCE7BE74C5184F97148F9882554"
psshGuid = "D08A4F1810F34A82B6C832D8ABA183D3"


class uuid_box(full_box):
    def __init__(self, *args):
        full_box.__init__(self, *args)


class sdtp_box(full_box):
    def __init__(self, *args):
        full_box.__init__(self, *args)

    def lead(self, il):
        if il == 0:
            return 'unknown'
        elif il == 1:
            return 'yes, not decodable'
        elif il == 2:
            return 'no'
        elif il == 3:
            return 'yes, decodable'

    def depends(self, v):
        if v == 0:
            return 'unknown'
        elif v == 1:
            return 'yes'
        elif v == 2:
            return 'no'
        elif v == 3:
            return 'reserved'

    def dependend(self, v):
        if 0 == v == 0:
            return 'unknown'
        elif 1 == v == 1:
            return 'yes'
        elif 2 == v == 2:
            return 'no'
        elif 3 == v == 3:
            return 'reserved'

    def redundancy(self, v):
        if v == 0:
            return 'unknown'
        elif v == 1:
            return 'yes'
        elif v == 2:
            return 'no'
        elif v == 3:
            return 'reserved'


class emsg_box(full_box):
    def __init__(self, *args):
        super().__init__(*args)

        i = parse_generator(self.fmap[self.offset + 12:
                                      self.offset + self.size])
        next(i)  # prime

        assert self.version == 0 or self.version == 1

        if self.version == 0:
            # emsg version 0
            self.scheme_id_uri = read_string(i)
            self.value = read_string(i)
            self.timescale = i.send('>I')[0]
            self.presentation_time_delta = i.send('>I')[0]
            self.event_duration = i.send('>I')[0]
            self.id = i.send('>I')[0]
        elif self.version == 1:
            # emsg version 1
            self.timescale = i.send('>I')[0]
            self.presentation_time = i.send('>Q')[0]
            self.event_duration = i.send('>I')[0]
            self.id = i.send('>I')[0]
            self.scheme_id_uri = read_string(i)
            self.value = read_string(i)

        self.message_data = []
        x = False
        try:
            while not x:
                self.message_data.append(i.send('>B')[0])
        except BaseException:
            pass

    @property
    def message(self):
        return self.message_data.hex()


REGISTERED_BOXES = {key: box for key, box in globals().items()
                    if key.endswith('_box')}
