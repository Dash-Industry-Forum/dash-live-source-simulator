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

from time import time, sleep

from dashlivesim.dashlib.mp4 import mp4
from dashlivesim.dashlib.boxes import create_moof, create_mdat, Sample


def decode_fragment(data, trex):
    "Extract samples from a segment."
    root = mp4(data)
    moof = root.find(b'moof')
    tfhd = moof.find(b'traf.tfhd')
    tfdt = moof.find(b'traf.tfdt')
    trun = moof.find(b'traf.trun')

    base_data_offset = tfhd.base_data_offset if tfhd.has_base_data_offset else moof.offset
    data_offset = trun.data_offset if trun.has_data_offset else 0
    base_media_decode_time = tfdt.decode_time

    t0, t1 = base_media_decode_time, base_media_decode_time
    begin, end = 0, 0
    default_sample_duration = (tfhd.default_sample_duration if tfhd.has_default_sample_duration else
                               trex.default_sample_duration)
    default_sample_size = (tfhd.default_sample_size if tfhd.has_default_sample_size else
                           trex.default_sample_size)
    default_sample_flags = (tfhd.default_sample_flags if tfhd.has_default_sample_flags else
                            trex.default_sample_flags)
    for entry in map(trun.sample_entry, range(trun.sample_count)):
        duration = entry['duration'] if trun.has_sample_duration else default_sample_duration
        size = entry['size'] if trun.has_sample_size else default_sample_size
        flags = entry['flags'] if trun.has_sample_flags else default_sample_flags
        time_offset = entry['time_offset'] if trun.has_sample_composition_time_offset else 0
        begin, end = end, end + size
        data = root.fmap[base_data_offset+data_offset:][begin:end]
        t0, t1 = t1, t1 + duration
        yield Sample(data, t0, duration, flags, time_offset)


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
        yield (create_moof(seqno, track_id, chunk_samples, None), create_mdat(chunk_samples))


def chunk(data, duration, trex_box):
    "Decode data into a segment and chunk it given duration and trex_box data."
    root = mp4(data)
    mfhd = root.find(b'moof.mfhd')
    tfhd = root.find(b'moof.traf.tfhd')

    seqno = mfhd.seqno
    track_id = tfhd.track_id

    fragments = encode_chunked(seqno,
                               track_id,
                               decode_fragment(data, trex_box),
                               duration)
    chunks = []
    for moof, mdat in fragments:
        chunks.append(moof.serialize() + mdat.serialize())
    return chunks


def simulate_continuous_production(segment, segment_start, chunk_duration, now_float):
    "Simulate continuous production by producing as many chunks as time allows."

    # print('Segment requested at %fs' % now_float)
    for i, chunk in enumerate(segment, start=1):
        chunk_availability_time = segment_start + i * chunk_duration
        time_until_available = chunk_availability_time - now_float
        if time_until_available > 0:
            now_float = time()  # Update time
            time_until_available = chunk_availability_time - now_float
            #print('Chunk %d was delayed by %fs, until %fs' % (i, time_until_available, chunk_availability_time))
            if time_until_available > 0:
                sleep(time_until_available)
                #print('Chunk %d was delayed by %fs, until %fs' % (i, time_until_available, chunk_availability_time))
        yield chunk


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser(description='Repackage a media segment to chunked '
                                        'segment to stdout')
    parser.add_argument('duration', type=int, nargs=1, help='Chunk duration in track timescale.')
    parser.add_argument('init', type=str,  help='Initialization segment containing track header.')
    parser.add_argument('media', type=str,  help='Media segment to repackage.')
    parser.add_argument("outfile", type=str, help='Output media segment.')

    args = parser.parse_args()
    duration = args.duration[0]
    init = open(args.init, 'rb').read()
    media = open(args.media, 'rb').read()

    with open(args.outfile, 'wb') as ofh:
        for chunk_data in chunk(media, duration, init_data=init):
            ofh.write(chunk_data)
            ofh.flush()
