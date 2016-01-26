"""Analyze DASH content in live profile and insert cc.
"""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2015, Dash Industry Forum.
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

import sys
import os
import time
import re
import struct

from ..dashlib import initsegmentfilter, mediasegmentfilter
from ..dashlib.mp4filter import MP4Filter
from ..dashlib.structops import uint32_to_str, str_to_uint32
from .mpdprocessor import MpdProcessor

DEFAULT_DASH_NAMESPACE = "urn:mpeg:dash:schema:mpd:2011"
MUX_TYPE_NONE = 0
MUX_TYPE_FRAGMENT = 1
MUX_TYPE_SAMPLES = 2

def generate_data(scc_data):
    """Function to generate scc data"""
    output = ""

    for data in scc_data:
        cea608_bytes = data['cea608']
        payload_size = (1 + 2 + 4 + 1) + (1 + 1 + (len(cea608_bytes) * 3)) + 1
        nal_unit = [0x66, 0x04, payload_size, 0xb5, 0x00, 0x31, ord('G'), ord('A'), ord('9'),
                    ord('4'), 0x03, 0xc0 + len(cea608_bytes), 0xff]

        #print len(cea608_bytes), payload_size

        for i in cea608_bytes:
            cc_byte1 = (int(i, 16) & 0xff00) >> 8
            cc_byte2 = (int(i, 16) & 0xff)

            # Field 1
            #nal_unit.append(0xfc)
            # Field 2
            nal_unit.append(0xfd)

            nal_unit.append(cc_byte1)
            nal_unit.append(cc_byte2)

        nal_unit.append(0xff)

        #print nal_unit
        output += struct.pack('>I', len(nal_unit))
        nal_unit_string = "".join(chr(i) for i in nal_unit)
        output += nal_unit_string

    #print [b for b in output]

    return output



class CCInsertFilter(MP4Filter):
    """CC Insert filter"""
    def __init__(self, segmentFile, scc_data, time_scale, tfdt):
        MP4Filter.__init__(self, segmentFile)
        self.top_level_boxes_to_parse = ["styp", "sidx", "moof", "mdat"]
        self.composite_boxes_to_parse = ["moof", "traf"]
        self.scc_data = scc_data
        self.time_scale = time_scale
        self.tfdt = tfdt

        self.trun_offset = 0

        self.scc_map = []

    def process_trun(self, data):
        """Process trun box."""
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        output = data[:16]

        flags = str_to_uint32(data[8:12]) & 0xffffff
        sample_count = str_to_uint32(data[12:16])
        pos = 16
        #data_offset_present = False

        if flags & 0x1: # Data offset present
            #data_offset_present = True
            self.trun_offset = str_to_uint32(data[16:20])
            output += uint32_to_str(self.trun_offset)
            pos += 4
        if flags & 0x4:
            pos += 4 # First sample flags present

        sample_duration_present = flags & 0x100
        sample_size_present = flags & 0x200
        sample_flags_present = flags & 0x400
        sample_comp_time_present = flags & 0x800
        sample_time_tfdt = self.tfdt

        orig_sample_pos = 0

        for i in range(sample_count):
            duration = 0
            size = 0
            flags = 0
            comp_time = 0

            if sample_duration_present:
                duration = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_size_present:
                size = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_flags_present:
                flags = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_comp_time_present:
                comp_time = str_to_uint32(data[pos:pos+4])
                pos += 4

            start_time = 0
            if i == 0:
                start_time = (sample_time_tfdt) / float(self.time_scale)
            else:
                start_time = (sample_time_tfdt + comp_time) / float(self.time_scale)

            end_time = (sample_time_tfdt + comp_time + duration) / float(self.time_scale)
            #start_time = (sample_time_tfdt) / float(self.time_scale)
            #end_time = (sample_time_tfdt + duration) / float(self.time_scale)

            #print "startTime:", start_time, "(", comp_time, ")", ", endTime:", end_time

            scc_samples = self.get_scc_data(start_time, end_time)
            orig_sample_pos += size
            if len(scc_samples):
                #print " ", i, "SampleTime: " + str((sample_time_tfdt + comp_time) / float(self.time_scale)),
                #      "num samples to add: ", len(scc_samples)
                print " ", i, "SampleTime: " + str((sample_time_tfdt) / float(self.time_scale)), \
                      "num samples to add: ", len(scc_samples)
                scc_generated_data = generate_data(scc_samples)
                self.scc_map.append({'pos':orig_sample_pos, 'scc':scc_generated_data, 'len': len(scc_generated_data)})
                #print size, size+len(scc_generated_data)
                size += len(scc_generated_data)

            if sample_duration_present:
                output += uint32_to_str(duration)
            if sample_size_present:
                output += uint32_to_str(size)
            if sample_flags_present:
                output += uint32_to_str(flags)
            if sample_comp_time_present:
                output += uint32_to_str(comp_time)

            sample_time_tfdt += duration

        #print data == output

        #print self.scc_map

        return output

    def process_mdat(self, data):
        """Process mdat box."""
        #print "processing mdat"
        pos = 0
        offset = self.trun_offset - (self.mdat_start - self.moof_start)

        output = data[pos:offset]

        pos = offset

        #total_bytes_added = 0

        for i in self.scc_map:
            size = int(i['pos'])
            scc_data = i['scc']
            #with open('nal.dat', 'wb') as f:
            #    f.write(scc_data)
            #exit(1)
            #total_bytes_added += len(scc_data)
            output += data[pos:(offset+size)]
            output += scc_data
            pos = (offset + size)

        output += data[pos:]

        #print "total_bytes_added:", total_bytes_added
        #print output == data

        #print len(data), len(output)

        return struct.pack('>I', len(output)) + output[4:]

    def get_scc_data(self, start_time, end_time):
        """Return scc data for a specified time period"""
        result = []
        for i in self.scc_data:
            if i['start_time'] >= start_time and i['start_time'] < end_time:
                result.append(i)
        return result


## Utility functions
def make_time_stamp(tim):
    """Maske timestamp in ISO format from UTC time in seconds."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(tim))

def make_duration_from_seconds(nr_seconds):
    """Create ISO duration as PTxS string from seconds."""
    return "PT%dS" % nr_seconds

def transform_time(tim):
    """Transform from hh:mm:ss:fn or pts to hh:mm:ss:ms."""
    try:
        parts = tim.split(":")
        frame_nr = int(parts[-1])
        milis = min(int(frame_nr*1000/29.97), 999)
        newtime = "%s.%03d" % (":".join(parts[:-1]), milis)
    except AttributeError: # pts time
        seconds = tim/90000
        milis = int((tim % 90000)/90.0)
        hours = seconds/3600
        minutes = seconds/60
        seconds -= hours*3600 + minutes*60
        newtime = "%02d:%02d:%02d.%03d" % (hours, minutes, seconds, milis)
    return newtime

def transform_time_to_ms(tim):
    """Transform from hh:mm:ss.ms to sss.sss"""
    newtime = 0
    timems = tim.split(".")
    parts = timems[0].split(":")

    newtime += int(parts[0]) * 3600000
    newtime += int(parts[1]) * 60000
    newtime += int(parts[2]) * 1000
    newtime += int(timems[1])
    return newtime

def convert_time(tim):
    """Convert time (in format hh:mm:ss:fn or hh:mm:ss:ms) into miliseconds"""
    return transform_time_to_ms(transform_time(tim)) / 1000.0

def chunks(data, num):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(data), num):
        yield data[i:i+num]

class CCInserterError(Exception):
    "Error in CCInserter."

## Searches the directory for a representation
def get_segment_range(rep_data):
    "Search the directory for the first and last segment and set firstNumber and lastNumber for this MediaType."
    rep_id = rep_data['id']
    media_dir, media_name = os.path.split(rep_data['absMediaPath'])
    media_regexp = media_name.replace("%d", r"(\d+)").replace(".", r"\.")
    media_reg = re.compile(media_regexp)
    files = os.listdir(media_dir)
    numbers = []
    for fil in files:
        match_obj = media_reg.match(fil)
        if match_obj:
            number = int(match_obj.groups(1)[0])
            numbers.append(number)
    numbers.sort()
    for i in range(1, len(numbers)):
        if numbers[i] != numbers[i-1] + 1:
            raise CCInserterError("%s segment missing between %d and %d" % rep_id, numbers[i], numbers[i-1])
    print "Found %s segments %d - %d" % (rep_id, numbers[0], numbers[-1])
    rep_data['firstNumber'] = numbers[0]
    rep_data['lastNumber'] = numbers[-1]



## CC Inserter class, does all the heavy lifting
class CCInserter(object):
    """This class does all the work, it takes an mpd-file, an scc-file and an output
        path, an processes the segments pointed to by the mpd."""
    # pylint: disable=too-many-instance-attributes

    def __init__(self, mpd_filepath, scc_filepath, out_path, verbose=1):
        self.mpd_filepath = mpd_filepath
        self.scc_filepath = scc_filepath
        self.out_path = out_path
        path_parts = mpd_filepath.split('/')
        #print path_parts
        if len(path_parts) >= 2:
            self.config_filename = '%s.cfg' % path_parts[-2]
        else:
            self.config_filename = 'content.cfg'
        self.base_path = os.path.split(mpd_filepath)[0]
        self.verbose = verbose
        self.as_data = {} # List of adaptation sets (one for each media)
        self.muxed_rep = None
        self.muxed_paths = {}
        self.mpd_seg_start_nr = -1
        self.scc_data = None
        self.seg_duration = None
        self.first_segment_in_loop = -1
        self.last_segment_in_loop = -1
        self.nr_segments_in_loop = -1
        self.mpd_processor = MpdProcessor(self.mpd_filepath)
        self.loop_time = self.mpd_processor.media_presentation_duration_in_s

    def analyze(self):
        """Main function to call, this analyzes the input and creates a output"""
        self.init_media()

        self.check_and_update_media_data()

    def init_media(self):
        "Init media by analyzing the MPD and the media files."
        for adaptation_set in self.mpd_processor.get_adaptation_sets():
            content_type = adaptation_set.content_type
            if content_type is None:
                print "No contentType for adaptation set"
                sys.exit(1)
            if self.as_data.has_key(content_type):
                raise CCInserterError("Multiple adaptation sets for contentType " + content_type)
            as_data = {'as' : adaptation_set, 'reps' : []}
            as_data['presentationDurationInS'] = self.mpd_processor.media_presentation_duration_in_s
            self.as_data[content_type] = as_data
            for rep in adaptation_set.representations:
                rep_data = {'representation' : rep, 'id' : rep.rep_id}
                as_data['reps'].append(rep_data)
                init_path = rep.initialization_path
                rep_data['relInitPath'] = init_path
                rep_data['absInitPath'] = os.path.join(self.base_path, init_path)
                init_filter = initsegmentfilter.InitFilter(rep_data['absInitPath'])
                init_filter.filter()
                rep_data['trackID'] = init_filter.track_id
                print "%s trackID = %d" % (content_type, rep_data['trackID'])
                rep_data['relMediaPath'] = rep.get_media_path()
                rep_data['absMediaPath'] = os.path.join(self.base_path, rep.get_media_path())

                get_segment_range(rep_data)
                track_timescale = init_filter.track_timescale
                if not as_data.has_key('track_timescale'):
                    as_data['track_timescale'] = track_timescale
                elif track_timescale != as_data['track_timescale']:
                    raise CCInserterError("Timescales not consistent between %s tracks" % content_type)
                #if self.verbose:
                #    print "%s data: " % content_type
                #    for (k,v) in rep_data.items():
                #        print "  %s=%s" % (k, v)

    def get_scc_data(self, start_time, end_time):
        """This fuction takes the sccdata and returns only the parts between start_time and end_time"""
        result = []
        for i in self.scc_data:
            if i['start_time'] >= start_time and i['start_time'] < end_time:
                result.append(i)
        return result

    def check_and_update_media_data(self):
        """Check all segments for good values and return startTimes and total duration."""
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        #lastGoodSegments = []
        seg_duration = None
        print "Checking all the media segment durations for deviations."

        for content_type in self.as_data.keys():
            if content_type == "video":
                as_data = self.as_data[content_type]
                adaptation_set = as_data['as']
                print "Checking %s with timescale %d" % (content_type, as_data['track_timescale'])
                if self.seg_duration is None:
                    seg_duration = adaptation_set.duration
                    self.seg_duration = seg_duration
                else:
                    assert self.seg_duration == adaptation_set.duration

                track_timescale = as_data['track_timescale']

                # Parse SCC file
                scc_parser = SCCParser(self.scc_filepath, track_timescale)
                scc_parser.parse()
                self.scc_data = scc_parser.result


                for rep_data in as_data['reps']:
                    rep_id = rep_data['id']
                    rep_data['endNr'] = None
                    rep_data['startTick'] = None
                    rep_data['endTick'] = None
                    if self.first_segment_in_loop >= 0:
                        assert rep_data['firstNumber'] == self.first_segment_in_loop
                    else:
                        self.first_segment_in_loop = rep_data['firstNumber']
                    if self.mpd_seg_start_nr >= 0:
                        assert adaptation_set.start_number == self.mpd_seg_start_nr
                    else:
                        self.mpd_seg_start_nr = adaptation_set.start_number
                    seg_ticks = self.seg_duration*track_timescale
                    max_diff_in_ticks = int(track_timescale*0.1) # Max 100ms
                    seg_nr = rep_data['firstNumber']
                    while True:
                        segment_path = rep_data['absMediaPath'] % seg_nr
                        if not os.path.exists(segment_path):
                            if self.verbose:
                                print "\nLast good %s segment is %d, endTime=%.3fs, totalTime=%.3fs" % (
                                    rep_id, rep_data['endNr'], rep_data['endTime'],
                                    rep_data['endTime']-rep_data['startTime'])
                            break
                        #print "Parsing segment: " + segment_path
                        msf = mediasegmentfilter.MediaSegmentFilter(segment_path)
                        msf.filter()
                        tfdt = msf.get_tfdt_value()
                        duration = msf.get_duration()

                        start_time = tfdt / float(track_timescale)
                        end_time = start_time + (duration / float(track_timescale))
                        print "Segment " + str(seg_nr) + ", start:" + str(start_time) + ", end:" + str(end_time)
                        scc_data_for_segment = self.get_scc_data(start_time, end_time)
                        if len(scc_data_for_segment):
                            #for i in scc_data_for_segment:
                            #    print " ",i['start_time'], 'bytes:', len(i['cea608'])

                            # Insert data into segment
                            cc_filter = CCInsertFilter(segment_path, scc_data_for_segment, track_timescale, tfdt)
                            output = cc_filter.filter()

                            print os.path.join(self.out_path, "%d.m4s"%seg_nr)
                            with open(os.path.join(self.out_path, "%d.m4s"%seg_nr), "wb") as fil:
                                fil.write(output)
                                fil.close()

                        if rep_data['startTick'] is None:
                            rep_data['startTick'] = tfdt
                            rep_data['startTime'] = rep_data['startTick']/float(track_timescale)
                            #print "First %s segment is %d starting at time %.3fs" % (rep_id, seg_nr,
                            #                                                         rep_data['startTime'])
                        # Check that there is not too much drift. We want to end with at most max_diff_in_ticks
                        end_tick = tfdt + duration
                        ideal_ticks = (seg_nr - rep_data['firstNumber'] + 1)*seg_ticks + rep_data['startTick']
                        abs_diff_in_ticks = abs(ideal_ticks - end_tick)
                        if abs_diff_in_ticks < max_diff_in_ticks:
                            # This is a good wrap point
                            rep_data['endTick'] = tfdt + duration
                            rep_data['endTime'] = rep_data['endTick']/float(track_timescale)
                            rep_data['endNr'] = seg_nr

                        seg_nr += 1
                        if self.verbose:
                            sys.stdout.write(".")

## Scc parser class
class SCCParser(object):
    """Parser for scc files, that returns an array with time and scc data objects"""
    # pylint: disable=too-few-public-methods
    def __init__(self, scc_path, timescale):
        self.scc_path = scc_path
        self.timescale = timescale
        self.result = []

    def parse(self):
        """Returns an array of time and scc data objects"""
        with open(self.scc_path, 'r') as fil:
            lines = fil.readlines()
            start_time = 0
            for line in lines:
                line = line.rstrip()
                if len(line) > 0 and line.find(':') > 0:
                    parts = line.split(' ')
                    start_time = convert_time(parts[0])
                    chunked_data = list(chunks(parts[1:], 31))
                    for cun in chunked_data:
                        data = {'start_time': start_time, 'cea608':cun}
                        self.result.append(data)


## Main function
def main():
    """main function does all the argument parsing"""
    from optparse import OptionParser
    verbose = 0
    usage = "usage: %prog [options] mpdPath sccPath outPath"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true")

    (options, args) = parser.parse_args()
    if options.verbose:
        verbose = 1
    if len(args) != 3:
        parser.error("incorrect number of arguments")

    mpd_file = args[0]
    scc_file = args[1]
    out_path = args[2]

    cc_inserter = CCInserter(mpd_file, scc_file, out_path, verbose)
    cc_inserter.analyze()


if __name__ == "__main__":
    main()
