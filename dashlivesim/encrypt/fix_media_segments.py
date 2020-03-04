"""Fix media segments by adding sgpd and sbgp boxes."""

from argparse import ArgumentParser

from dashlivesim.dashlib.mp4filter import MP4Filter
from dashlivesim.dashlib.structops import (str_to_uint32, uint32_to_str,
                                           uint8_to_str, sint32_to_str,
                                           str_to_sint32)

class MediaSegmentFilterError(Exception):
    "Error in MediaSegmentFilter."


class FixEncryptedSegment(MP4Filter):
    """Add sgpd and sbgp boxes to an encrypted segment."""

    def __init__(self, file_name, key_id, iv_size=8):
        MP4Filter.__init__(self, file_name)
        self.key_id = key_id
        self.iv_size = iv_size
        self.top_level_boxes_to_parse = ["moof"]
        self.composite_boxes_to_parse = ['moof', 'traf']
        self.senc_sample_count = None
        self.size_change = 72  # sgpd + sbgp = 44 + 28

    def process_trun(self, data):
        "Get total duration from trun. Fix offset if self.size_change is non-zero."
        flags = str_to_uint32(data[8:12]) & 0xffffff
        sample_count = str_to_uint32(data[12:16])
        pos = 16
        data_offset_present = False
        if flags & 0x1:  # Data offset present
            data_offset_present = True
            pos += 4
        if flags & 0x4:
            pos += 4  # First sample flags present
        sample_duration_present = flags & 0x100
        sample_size_present = flags & 0x200
        sample_flags_present = flags & 0x400
        sample_comp_time_present = flags & 0x800
        duration = 0
        for _ in range(sample_count):
            if sample_duration_present:
                duration += str_to_uint32(data[pos:pos + 4])
                pos += 4
            else:
                duration += self.default_sample_duration
            if sample_size_present:
                pos += 4
            if sample_flags_present:
                pos += 4
            if sample_comp_time_present:
                pos += 4
        self.duration = duration

        # Modify data_offset
        output = data[:16]
        if data_offset_present and self.size_change > 0:
            offset = str_to_sint32(data[16:20])
            offset += self.size_change
            output += sint32_to_str(offset)
        else:
            output += data[16:20]
        output += data[20:]
        return output

    def process_senc(self, data):
        "Get the number of entries."
        version_and_flags = str_to_uint32(data[8:12])
        sample_count = str_to_uint32(data[12:16])
        self.senc_sample_count = sample_count
        # Skip parsing the rest
        return data + self.generate_sgpd() + self.generate_sbgp()

    def generate_sgpd(self):
        "Generate an appropriate sgpd box."
        output = uint32_to_str(44) + 'sgpd' + '\x01\x00\x00\x00' + 'seig'
        output += uint32_to_str(20) # defaultLength
        output += '\x00\x00\x00\x01' # nr groupEntries
        output += '\x00\x00\x01' + uint8_to_str(self.iv_size)
        output += self.key_id
        assert len(output) == 44
        return output

    def generate_sbgp(self):
        "Generate an appropriate sbgp box."
        output = uint32_to_str(28) + 'sbgp' + '\x00\x00\x00\x00' + 'seig'
        output += '\x00\x00\x00\x01'  # nr entries
        output += uint32_to_str(self.senc_sample_count)
        output += '\x00\x01\x00\x01'  # first local groupDescriptionIndex
        assert len(output) == 28
        return output


def fix_segment(infile, outfile, kid_hex, iv_size):
    kid = kid_hex.decode('hex')
    fs = FixEncryptedSegment(infile, kid, iv_size)
    outdata = fs.filter()
    with open(outfile, 'wb') as ofh:
        ofh.write(outdata)


def main():
    parser = ArgumentParser()
    parser.add_argument('infile')
    parser.add_argument('outfile')
    parser.add_argument('kid_hex')
    parser.add_argument('iv_size', type=int)

    args = parser.parse_args()
    print("'%s' %d" % (args.kid_hex, len(args.kid_hex)))
    fix_segment(args.infile, args.outfile, args.kid_hex, args.iv_size)


if __name__ == "__main__":
    main()