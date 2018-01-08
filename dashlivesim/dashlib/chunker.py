"""Chunkify an ISOBMFF segment. Either as library or command line tool."""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2017, Dash Industry Forum.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#  * Redistributions of source code must retain the above copyright notice, this
#  list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation and/or
#  other materials provided with the distribution.
#  * Neither the name of Dash Industry Forum nor the names of its
#  contributors may be used to endorse or promote products derived from this software
#  without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS AS IS AND ANY
#  EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#  IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
#  INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#  NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
#  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.

from mp4 import mp4, trex_box
from boxes import create_moof, create_mdat, Sample


def decode_fragment(data, trex):
    root = mp4(data)
    moof = root.find('moof')
    tfhd = moof.find('traf.tfhd')
    tfdt = moof.find('traf.tfdt')
    trun = moof.find('traf.trun')

    base_data_offset = tfhd.base_data_offset if tfhd.has_base_data_offset else moof.offset
    data_offset = trun.data_offset if trun.has_data_offset else 0
    base_media_decode_time = tfdt.decode_time

    t0, t1 = base_media_decode_time, base_media_decode_time
    begin, end = 0, 0
    for entry in map(trun.sample_entry, range(trun.sample_count)):
        duration = entry['duration'] if trun.has_sample_duration else \
            tfhd.default_sample_duration if tfhd.has_default_sample_duration else \
                trex.default_sample_duration
        size = entry['size'] if trun.has_sample_size else \
            tfhd.default_sample_size if tfhd.has_default_sample_size else \
                trex.default_sample_size
        flags = entry['flags'] if trun.has_sample_flags else \
            tfhd.default_sample_flags if tfhd.has_default_sample_flags else \
                trex.default_sample_flags
        time_offset = entry['time_offset'] if trun.has_sample_composition_time_offset else 0
        begin, end = end, end + size
        data = root.fmap[base_data_offset+data_offset:][begin:end]
        t0, t1 = t1, t1 + duration
        yield Sample(data, t0, duration, flags & 0x2000000, time_offset)


def partition(samples, duration):
    d0, d1 = 0, duration
    part = []
    for sample in samples:
        if d0 >= d1:
            d1 += duration
            yield part
            part = []
        d0 += sample.duration
        part.append(sample)
    if part:
        yield part


def encode_chunked(seqno, track_id, samples, duration):
    for chunk_samples in partition(samples, duration):
        yield create_moof(seqno, track_id, chunk_samples, None)
        yield create_mdat(chunk_samples)


def chunk(data, duration, init_data=None):
    root = mp4(data)
    mfhd = root.find('moof.mfhd')
    tfhd = root.find('moof.traf.tfhd')
    #init_root = mp4(init_data)
    #trex = root.find('moov.trex')
    # TODO! Add init_data to call and parse trex from moov!
    trex = trex_box('\x00\x00\x00\x20'  # size
                    'trex'              # type
                    '\x00'              # version
                    '\x00\x00\x00'      # flags
                    '\x00\x00\x00\x01'  # track_ID
                    '\x00\x00\x00\x01'  # default_sample_description_index
                    '\x00\x00\x02\x00'  # default_sample_duration
                    '\x00\x00\x00\x00'  # default_sample_size
                    '\x02\x00\x00\x00', # default_sample_flags
                    'trex', 0x20, 0x0)

    seqno = mfhd.seqno
    track_id = tfhd.track_id

    boxes = encode_chunked(seqno,
                           track_id,
                           decode_fragment(data, trex),
                           duration)
    for moof, mdat in zip(boxes, boxes):
        yield moof.serialize()+mdat.serialize()


if __name__ == '__main__':
    from argparse import ArgumentParser
    from sys import stdout

    parser = ArgumentParser(description='Repackage a media segment to chunked '
                                        'segment to stdout')
    parser.add_argument('duration', type=int, nargs=1, help='Chunk duration in track timescale.')
    parser.add_argument('init', type=str, nargs=1, help='Initialization segment containing track header.')
    parser.add_argument('media', type=str, nargs=1, help='Media segment to repackage.')

    args = parser.parse_args()
    duration = args.duration[0]
    init = open(args.init[0], 'rb').read()
    media = open(args.media[0], 'rb').read()

    for chunk_data in chunk(media, duration, init_data=init):
        stdout.write(chunk_data)
        stdout.flush()
