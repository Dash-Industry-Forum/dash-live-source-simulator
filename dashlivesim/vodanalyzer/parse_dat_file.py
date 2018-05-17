import sys
from struct import unpack

import argparse

from dashlivesim.dashlib.configprocessor import SEGTIMEFORMAT, SegTimeEntry

def parse_dat_file(infile_handle, verbosity_level):
    data = infile_handle.read(12)
    lste = None
    while data:
        ste = SegTimeEntry(*unpack(SEGTIMEFORMAT, data))
        if lste:
            last_end = lste.start_time + lste.duration * (lste.repeats + 1)
            if last_end != ste.start_time:
                print "Mismatch in end vs start time %d %d" % (
                    ste.start_time, last_end)
        if verbosity_level > 0:
            print ste
        lste = ste
        data = infile_handle.read(12)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check segment datfile')
    parser.add_argument('infile', nargs=1, type=argparse.FileType('rb'))
    parser.add_argument('--verbose', '-v', action='count')

    args = parser.parse_args()
    parse_dat_file(args.infile[0], args.verbose)