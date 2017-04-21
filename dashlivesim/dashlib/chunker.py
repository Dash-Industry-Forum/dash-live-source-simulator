from repack_poc.ewmedia.mp4 import mp4, trex_box
from repack_poc.ewmedia.esf.boxes import *


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
        data = root.raw_data[base_data_offset+data_offset:][begin:end]
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
    # TODO! Add init_data to call and parse trex from moov!
    trex = trex_box('\x00\x00\x00\x20'  # size
                    'trex'              # type
                    '\x00'              # version
                    '\x00\x00\x00'      # flags
                    '\x00\x00\x00\x01'  # track_ID
                    '\x00\x00\x00\x01'  # default_sample_description_index
                    '\x00\x00\x02\x00'  # default_sample_duration
                    '\x00\x00\x00\x00'  # default_sample_size
                    '\x00\x01\x00\x00', # default_sample_flags
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

    parser = ArgumentParser(description='Repackage segment to chunked segment.')
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
