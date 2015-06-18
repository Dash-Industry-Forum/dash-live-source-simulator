"""Modify MPD from VoD to live (static to dynamic)."""

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

import copy
from xml.etree import ElementTree
import cStringIO
import time
import re

from .timeformatconversions import make_timestamp, iso_duration_to_seconds, seconds_to_iso_duration
from dashlivesim.dashlib import scte35

from .mpdprocessor import MpdProcessor, MpdProcessorError


def process_manifest_loop(filename, in_data, now, utc_timing_methods, utc_head_url):
    "Process the manifest and provide a changed one."
    ast_in_s = in_data['availability_start_time_in_s']
    tsbd_in_s = in_data['timeShiftBufferDepthInS']
    mup_in_s = iso_duration_to_seconds(in_data['minimumUpdatePeriod'])
    new_data = {'publishTime' : '%s' % make_timestamp(in_data['publishTime']),
                'availabilityStartTime' : '%s' % make_timestamp(ast_in_s),
                'timeShiftBufferDepth' : '%s' % in_data['timeShiftBufferDepth'],
                'minimumUpdatePeriod' : '%s' % in_data['minimumUpdatePeriod'],
                'duration' : '%d' % in_data['segDuration'],
                'maxSegmentDuration' : 'PT%dS' % in_data['segDuration'],
                'BaseURL' : '%s' % in_data['BaseURL'],
                'periodOffset' : in_data['periodOffset'],
                'presentationTimeOffset' : 0}
    if in_data.has_key('availabilityEndTime'):
        new_data['availabilityEndTime'] = make_timestamp(in_data['availabilityEndTime'])
    if in_data.has_key('mediaPresentationDuration'):
        new_data['mediaPresentationDuration'] = in_data['mediaPresentationDuration']
    mpd_proc = MpdProcessorVodLoop(filename, now, ast_in_s, tsbd_in_s, mup_in_s,
                                   in_data['scte35Present'], utc_timing_methods, utc_head_url)
    mpd_proc.process(new_data, period_data=None)
    return mpd_proc.get_full_xml()


class MpdProcessorError(Exception):
    "Generic MpdProcessor error."
    pass


class MpdProcessorVodLoop(MpdProcessor):
    "Process an MPD with multiple VoDs as Periods. Analyzer and convert it to a live (dynamic) looping session."
    # pylint: disable=no-self-use, too-many-locals

    def __init__(self, infile, now, ast_in_s, tsbd_in_s, mup_in_s,
                 scte35_present, utc_timing_methods, utc_head_url=""):
        MpdProcessor.__init__(self, infile, scte35_present, utc_timing_methods, utc_head_url)
        mpd = self.root
        self.media_presentation_duration_s = iso_duration_to_seconds(mpd.attrib['mediaPresentationDuration'])
        self.now = now
        self.ast_in_s = ast_in_s
        self.tsbd_in_s = tsbd_in_s
        self.mup_in_s = mup_in_s

    def get_period_at_time(self, time_in_s, input_period_data, total_duration):
        "Return the nr_of_loops and position corresponding to a time."
        nr_loops = max((time_in_s - self.ast_in_s)//total_duration, 0)
        time_rel_loop = time_in_s - nr_loops*total_duration
        period_index = 0
        while period_index < len(input_period_data)-1:
            pdata = input_period_data[period_index]
            if pdata['start'] > time_rel_loop:
                break
            period_index += 1
        return (nr_loops, period_index)

    def get_input_period_data(self, input_periods):
        "Get an array of data for each period in the manifest. The data is id, duration, start."
        input_period_data = []
        for period in input_periods:
            pdata = {'start' : None, 'duration' : None, 'id' : period.attrib['id']}
            if period.attrib.has_key('start'):
                pdata['start'] = iso_duration_to_seconds(period.attrib['start'])
                del period.attrib['start']
            if period.attrib.has_key('duration'):
                pdata['duration'] = iso_duration_to_seconds(period.attrib['duration'])
                del period.attrib['duration']
            input_period_data.append(pdata)

        for i in range(len(input_period_data)):
            pdata = input_period_data[i]
            if pdata['start'] is None:
                if i == 0:
                    pdata['start'] = 0
                else:
                    pdata['start'] = input_period_data[i-1]['start'] + input_period_data[i-1]['duration']
            if pdata['duration'] is None:
                if i == len(input_period_data) - 1:
                    pdata['duration'] = self.media_presentation_duration_s - pdata['start']
                else:
                    pdata['duration'] = input_period_data[i+1]['start'] - pdata['start']

        return input_period_data

    def update_periods(self, mpd, the_period_pos, period_data, offset_at_period_level=False):
        "Fix periods to cover the appropriate interval."
        input_periods = mpd.findall(self.add_ns('Period'))
        for period in input_periods:
            mpd.remove(period)

        input_period_data = self.get_input_period_data(input_periods)

        total_duration = sum([pdata['duration'] for pdata in input_period_data])
        assert total_duration == self.media_presentation_duration_s

        start_time = self.now - self.tsbd_in_s
        end_time = self.now + self.mup_in_s
        start_nr_loops, start_period = self.get_period_at_time(start_time, input_period_data, total_duration)
        end_nr_loops, end_period = self.get_period_at_time(end_time, input_period_data, total_duration)

        next_period_start = start_nr_loops*total_duration + input_period_data[start_period]['start']
        mpd_child_pos = the_period_pos
        for loop_nr in range(start_nr_loops, end_nr_loops+1):
            if loop_nr == start_nr_loops:
                start_index = start_period
            else:
                start_index = 0
            if loop_nr == end_nr_loops:
                end_index = end_period
            else:
                end_index = len(input_period_data) - 1
            for pnr in range(start_index, end_index+1):
                new_period = copy.deepcopy(input_periods[pnr])
                new_period.attrib['start'] = seconds_to_iso_duration(next_period_start)
                new_period.attrib['id'] = "%s_%d" % (new_period.attrib['id'], loop_nr)
                new_period.attrib['duration'] = seconds_to_iso_duration(input_period_data[pnr]['duration'])
                mpd.insert(mpd_child_pos, new_period)
                next_period_start += input_period_data[pnr]['duration']
                mpd_child_pos += 1

