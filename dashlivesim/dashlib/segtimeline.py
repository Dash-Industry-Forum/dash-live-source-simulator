"""SegmentTimeLine XML entry generator."""

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

import os
from struct import unpack
from xml.etree import ElementTree
import bisect

from configprocessor import SEGTIMEFORMAT, SegTimeEntry

from dash_namespace import add_ns


class SegmentTimeLineGeneratorError(Exception):
    "Something strange happened."
    pass


class SegmentTimeLineGenerator(object):
    "Generate SegmentTimeline Object with times relative to availabilityStartTime."

    def __init__(self, media_data, cfg):
        self.timescale = media_data['timescale']
        self.cfg = cfg
        try:
            dat_file = media_data['dat_file']
        except KeyError, e:
            print "Error for %s: %s" % (media_data, e)
        dat_file_path = os.path.join(self.cfg.vod_cfg_dir, dat_file)
        self.segtimedata = [] # Tuples corresponding to SegTimeEntry
        with open(dat_file_path, "rb") as ifh:
            data = ifh.read(12)
            while data:
                ste = SegTimeEntry(*unpack(SEGTIMEFORMAT, data))
                self.segtimedata.append(ste)
                data = ifh.read(12)
        self.interval_starts = [std.start_time for std in self.segtimedata]
        self.wrap_duration = cfg.vod_wrap_seconds * self.timescale
        self.nr_segments_per_wrap = cfg.vod_nr_segments_in_loop
        self.first_segment_number = cfg.vod_first_segment_in_loop
        self.start_number = None

    def create_segtimeline(self, start_time, end_time, use_closest=False):
        "Create and insert a new <SegmentTimeline> element and S entries."
        seg_timeline = ElementTree.Element(add_ns('SegmentTimeline'))
        seg_timeline.text = "\n"
        seg_timeline.tail = "\n"

        start = start_time * self.timescale
        end = end_time * self.timescale

        # The start segment is the latest one that starts before or at start
        # The end segment is the latest one that ends before or at end.

        (end_index, end_repeats, end_wraps) = self.find_latest_starting_before(end)
        if end_index is None:
            raise SegmentTimeLineGeneratorError("No end_index for %d %d. Before AST" % (start_time, end_time))
        end_tics = self.get_seg_endtime(end_wraps, end_index, end_repeats)
        #print "end_time %d %d" % (end, end_tics)

        while end_tics > end:
            if end_repeats > 0:
                end_repeats -= 1  # Just move one segment back in the repeat
            elif end_index > 0:
                end_index -= 1
                end_repeats = self.segtimedata[end_index].repeats
            else:
                end_wraps -= 1
                end_index = len(self.segtimedata) - 1
                end_repeats = self.segtimedata[end_index].repeats
                if (end_wraps < 0):
                    return (None, None, None)
            end_tics = self.get_seg_endtime(end_wraps, end_index, end_repeats)

        #print "end_time2 %d %d %d" % (end, end_tics, (end-end_tics)/(self.timescale*1.0))
        #print "end time %d %d %d" % (end_index, end_repeats, end_wraps)

        if use_closest:
            result = self.find_closest_start(start)
        else:
            result = self.find_latest_starting_before(start)
        (start_index, start_repeats, start_wraps) = result
        #print "start %d %d %d" % (start_index, start_repeats, start_wraps)
        start_tics = self.get_seg_starttime(start_wraps, start_index, start_repeats)
        start_tics_end = self.get_seg_starttime(end_wraps, end_index, end_repeats)
        if (start_tics_end < start_tics):
            return seg_timeline # Empty timeline in this case
        #print "start time %d %d %d" % (start_tics, start, start - start_tics)
        repeat_index = end_index
        nr_wraps = end_wraps
        # Create the S elements in backwards order
        while repeat_index != start_index or nr_wraps != start_wraps:
            seg_data = self.segtimedata[repeat_index]
            #print repeat_index, start_index, nr_wraps, start_wraps
            if repeat_index == end_index:
                s_elem = self.generate_s_elem(None, seg_data.duration, end_repeats)
            else:
                s_elem = self.generate_s_elem(None, seg_data.duration, seg_data.repeats)
            seg_timeline.insert(0, s_elem)
            repeat_index -= 1
            if repeat_index < 0:
                nr_wraps -= 1
                repeat_index = len(self.segtimedata) - 1
        # Now at first entry corresponding to start_index and start_wraps
        seg_data = self.segtimedata[start_index]
        seg_start_time = self.get_seg_starttime(nr_wraps, start_index, start_repeats)
        if start_index != end_index:
            nr_repeats = seg_data.repeats - start_repeats
        elif len(self.segtimedata) == 1 and end_repeats < start_repeats:
            nr_repeats = (self.segtimedata[0].repeats + end_repeats -
                          start_repeats)
        else: # There was only one entry which was repeated
            nr_repeats = end_repeats - start_repeats
        s_elem = self.generate_s_elem(seg_start_time, seg_data.duration, nr_repeats)
        seg_timeline.insert(0, s_elem)
        self.start_number = self.get_seg_number(nr_wraps, start_index,
                                                start_repeats)
        return seg_timeline

    def get_seg_starttime(self, nr_wraps, index, repeats):
        "Get the segment starttime given repeats."
        seg_data = self.segtimedata[index]
        return nr_wraps*self.wrap_duration + seg_data.start_time + repeats*seg_data.duration

    def get_seg_number(self, nr_wraps, index, repeats):
        "Get the segment number given repeats."
        seg_data = self.segtimedata[index]
        return (nr_wraps*self.nr_segments_per_wrap + seg_data.start_nr +
                repeats - self.first_segment_number)

    def get_seg_endtime(self, nr_wraps, index, repeats):
        "Get the end of a segment."
        seg_data = self.segtimedata[index]
        return nr_wraps*self.wrap_duration + seg_data.start_time + (repeats+1)*seg_data.duration

    def find_latest_starting_before(self, act_time):
        "Find the latest segment starting before act_time."
        nr_wraps, rel_time = divmod(act_time, self.wrap_duration)
        if nr_wraps < 0:
            return (None, None, None) # This is before AST
        index = bisect.bisect(self.interval_starts, rel_time) - 1
        seg_data = self.segtimedata[index]
        repeats = 0
        accumulated_end_time = seg_data.start_time + seg_data.duration
        while accumulated_end_time <= rel_time:
            accumulated_end_time += seg_data.duration
            repeats += 1
        return index, repeats, nr_wraps

    def find_closest_start(self, act_time):
        nr_wraps, rel_time = divmod(act_time, self.wrap_duration)
        if nr_wraps < 0:
            return (None, None, None) # This is before AST
        index = bisect.bisect(self.interval_starts, rel_time) - 1
        seg_data = self.segtimedata[index]
        repeats = 0
        start = seg_data.start_time
        if abs(rel_time - start) <= (seg_data.duration // 2):
            return index, repeats, nr_wraps

        while repeats < seg_data.repeats:
            repeats += 1
            start += seg_data.duration

            if abs(rel_time - start) <= (seg_data.duration // 2):
                return index, repeats, nr_wraps

        index += 1
        if index >= len(self.interval_starts):
            index = 0
            nr_wraps += 1
        return index, self.segtimedata[index].repeats, nr_wraps

    def find_closest_end(self, act_time):
        "Find "
        nr_wraps, rel_time = divmod(act_time, self.wrap_duration)
        if nr_wraps < 0:
            return (None, None, None) # This is before AST
        index = bisect.bisect(self.interval_starts, rel_time) - 1
        seg_data = self.segtimedata[index]
        repeats = 0
        start = seg_data.start_time
        if abs(act_time, start) < (seg_data.duration // 2):
            return index, repeats, nr_wraps

        while repeats < seg_data.repeats:
            repeats += 1
            start += seg_data.duration
            if abs(act_time, start) < (seg_data.duration // 2):
                return index, repeats, nr_wraps

        index += 1
        if index >= self.interval_starts:
            index = 0
            nr_wraps += 1
        return index, self.segtimedata[index].repeats, nr_wraps

    def generate_s_elem(self, start_time, duration, repeat):
        "Generate the S elements for the SegmentTimeline."
        s_elem = ElementTree.Element(add_ns('S'))
        if start_time is not None:
            s_elem.set("t", str(start_time))
        s_elem.set("d", str(duration))
        if repeat > 0:
            s_elem.set('r', str(repeat))
        s_elem.tail = "\n"
        return s_elem
