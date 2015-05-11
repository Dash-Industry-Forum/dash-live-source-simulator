"""
Make a VoD file look like infinite live DASH content. The timing is synchronized with wall clock.

The rewrites which are done are

MPD:
    @MPD
      remove mediaPresentationDuration
      set type dynamic
      set publishTime
      set timeShiftBufferDepth
      set availabilityStartTime
      set minimumUpdatePeriod
      set maxSegmentDuration
      set/add availabilityEndTIme
    @SegmentTemplate
      set startNumber

initialization segments:
   No change

Media segments
   Mapped from live number to VoD number
   tfdt and sidx updated to match live time (if KEEP_SIDX = true)
   sequenceNumber updated to be continuous (and identical to the sequenceNumber asked for)

The numbering and timing is based on the epoch time, and is generally

[time_in_epoch clipped to multiple of duration]/duration

Thus segNr corresponds to the interval [segNr*duration , (segNr+1)*duration]

For infinite content, the default is startNumber = 0, availabilityStartTime = 1970-01-01T00:00:00
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

from os.path import splitext, join

from .initsegmentfilter import InitLiveFilter
from .mediasegmentfilter import MediaSegmentFilter
from . import segmentmuxer
from . import mpdprocessor
from .timeformatconversions import make_timestamp, seconds_to_iso_duration
from .configprocessor import ConfigProcessor, quantize

SECS_IN_DAY = 24*3600
DEFAULT_MINIMUM_UPDATE_PERIOD = "P100Y"
DEFAULT_PUBLISH_ADVANCE_IN_S = 7200
EXTRA_TIME_AFTER_END_IN_S = 60

UTC_HEAD_PATH = "dash/time.txt"

PUBLISH_TIME = False

def handle_request(host_name, url_parts, args, vod_conf_dir, content_dir, now=None, req=None):
    "Handle Apache request."
    dash_provider = DashProvider(host_name, url_parts, args, vod_conf_dir, content_dir, now, req)
    return dash_provider.handle_request()


class DashProxyError(Exception):
    "Error in DashProxy."

class DashSegmentNotAvailableError(DashProxyError):
    "Segment not available."


def process_manifest(filename, in_data, now, tfdt_values_from_zero, utc_timing_methods, utc_head_url):
    "Process the manifest and provide a changed one."
    new_data = {'publishTime' : '%s' % make_timestamp(in_data['publishTime']),
                'availabilityStartTime' : '%s' % make_timestamp(in_data['availability_start_time_in_s']),
                'timeShiftBufferDepth' : '%s' % in_data['timeShiftBufferDepth'],
                'minimumUpdatePeriod' : '%s' % in_data['minimumUpdatePeriod'],
                'startNumber' : '%d' % in_data['startNumber'],
                'duration' : '%d' % in_data['segDuration'],
                'maxSegmentDuration' : 'PT%dS' % in_data['segDuration'],
                'BaseURL' : '%s' % in_data['BaseURL'],
                'periodOffset' : in_data['periodOffset'],
                'presentationTimeOffset' : 0}
    if in_data.has_key('availabilityEndTime'):
        new_data['availabilityEndTime'] = make_timestamp(in_data['availabilityEndTime'])
    if in_data.has_key('mediaPresentationDuration'):
        new_data['mediaPresentationDuration'] = in_data['mediaPresentationDuration']
    if tfdt_values_from_zero and in_data['availability_start_time_in_s'] > 0:
        new_data['presentationTimeOffset'] = in_data['availability_start_time_in_s']
    mpmod = mpdprocessor.MpdProcessor(filename, in_data['scte35Present'], utc_timing_methods, utc_head_url)
    if in_data['periodsPerHour'] < 0:
        period_data = generate_default_period_data(in_data, new_data)
    else:
        period_data = generate_multiperiod_data(in_data, new_data, now)
    mpmod.process(new_data, period_data)
    return mpmod.getstring()

def generate_default_period_data(in_data, new_data):
    "Generate period data for a single period starting at the same time as the session (start = PT0S)."
    start = 0
    seg_dur = in_data['segDuration']
    data = {'id' : "p0", 'start' : 'PT%dS' % start, 'startNumber' : "%d" % (start/seg_dur), 'duration' : seg_dur,
            'presentationTimeOffset' : "%d" % new_data['presentationTimeOffset']}
    return [data]

def generate_multiperiod_data(in_data, new_data, now):
    "Generate an array of period data depending on current time (now)."
    #pylint: disable=too-many-locals
    nr_periods_per_hour = min(in_data['periodsPerHour'], 60)
    if not nr_periods_per_hour in (0, 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60):
        raise Exception("Bad nr of periods per hour %d" % nr_periods_per_hour)
    seg_dur = in_data['segDuration']
    period_data = []
    if nr_periods_per_hour > 0:
        period_duration = 3600/nr_periods_per_hour
        minimum_update_period = "PT%dS" % (period_duration/2 - 5)
        new_data['minimumUpdatePeriod'] = minimum_update_period
        this_period_nr = now/period_duration
        nr_periods_back = in_data['timeShiftBufferDepthInS']/period_duration + 1
        start_period_nr = this_period_nr - nr_periods_back
        last_period_nr = this_period_nr + 1
        for period_nr in range(start_period_nr, last_period_nr+1):
            start_time = period_nr*period_duration
            data = {'id' : "p%d" % period_nr, 'start' : 'PT%dS' % (period_nr*period_duration),
                    'startNumber' : "%d" % (start_time/seg_dur), 'duration' : seg_dur,
                    'presentationTimeOffset' : period_nr*period_duration}
            period_data.append(data)
    else: # nrPeriodsPerHour == 0, make one old period but starting 1000h after the start of the Epoch
        start = 3600*1000
        data = {'id' : "p0", 'start' : 'PT%dS' % start, 'startNumber' : "%d" % (start/seg_dur),
                'duration' : seg_dur, 'presentationTimeOffset' : "%d" % start}
        period_data.append(data)
    return period_data


class DashProvider(object):
    "Provide DASH manifest and segments."
    #pylint: disable=too-many-instance-attributes

    def __init__(self, host_name, url_parts, url_args, vod_conf_dir, content_dir, now=None, req=None):
        self.base_url = "http://%s/%s/" % (host_name, url_parts[0]) # The start. Adding all parts up to content later.
        self.utc_head_url = "http://%s/%s" % (host_name, UTC_HEAD_PATH)
        self.url_parts = url_parts[1:]
        self.url_args = url_args
        self.vod_conf_dir = vod_conf_dir
        self.content_dir = content_dir
        self.now_float = now # float
        self.now = int(now)
        self.req = req
        self.cfg = None
        self.new_tfdt_value = None

    def handle_request(self):
        "Handle the Apache request."
        return self.parse_url()

    def error_response(self, msg):
        "Return a mod_python error response."
        if self.req:
            self.req.log_error("dash_proxy: [%s] %s" % ("/".join(self.url_parts[-3:]), msg))
        return {'ok' : False, 'pl' : msg + "\n"}

    def parse_url(self):
        "Parse the absolute URL that is received in mod_python."
        cfg_processor = ConfigProcessor(self.vod_conf_dir, self.base_url)
        cfg_processor.process_url(self.url_parts, self.now)
        cfg = cfg_processor.getconfig()
        if cfg.ext == ".mpd":
            mpd_filename = "%s/%s/%s" % (self.content_dir, cfg.content_name, cfg.filename)
            mpd_input_data = cfg_processor.get_mpd_data()
            response = self.generate_dynamic_mpd(cfg, mpd_filename, mpd_input_data, self.now)
        elif cfg.ext == ".mp4":
            if self.now < cfg.availability_start_time_in_s - cfg.init_seg_avail_offset:
                diff = (cfg.availability_start_time_in_s - cfg.init_seg_avail_offset) - self.now_float
                response = self.error_response("Request for %s was %.1fs too early" % (cfg.filename, diff))
            else:
                response = self.process_init_segment(cfg)
        elif cfg.ext == ".m4s":
            first_segment_ast = cfg.availability_start_time_in_s + cfg.seg_duration
            if self.now_float < first_segment_ast:
                diff = first_segment_ast - self.now_float
                response = self.error_response("Request %s before first seg AST. %.1fs too early" %
                                               (cfg.filename, diff))
            elif cfg.availability_end_time is not None and \
                            self.now > cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S:
                diff = self.now_float - (cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S)
                response = self.error_response("Request for %s after AET. %.1fs too late" % (cfg.filename, diff))
            else:
                response = self.process_media_segment(cfg, self.now_float)
        else:
            response = "Unknown file extension: %s" % cfg.ext
        return response

    #pylint: disable=no-self-use
    def generate_dynamic_mpd(self, cfg, mpd_filename, mpd_input_data, now):
        "Generate the dynamic MPD."
        if cfg.minimum_update_period_in_s is not None:
            mpd_input_data['minimumUpdatePeriod'] = seconds_to_iso_duration(cfg.minimum_update_period_in_s)
        else:
            mpd_input_data['minimumUpdatePeriod'] = DEFAULT_MINIMUM_UPDATE_PERIOD
        if cfg.media_presentation_duration is not None:
            mpd_input_data['mediaPresentationDuration'] = seconds_to_iso_duration(cfg.media_presentation_duration)
        mpd_input_data['timeShiftBufferDepth'] = seconds_to_iso_duration(cfg.timeshift_buffer_depth_in_s)
        mpd_input_data['timeShiftBufferDepthInS'] = cfg.timeshift_buffer_depth_in_s
        mpd_input_data['scte35Present'] = (cfg.scte35_per_minute > 0)
        tfdt_values_from_zero = not cfg.tfdt32_flag
        mpd = process_manifest(mpd_filename, mpd_input_data, now, tfdt_values_from_zero, cfg.utc_timing_methods,
                               self.utc_head_url)
        return mpd

    def process_init_segment(self, cfg):
        "Read non-multiplexed or create muxed init segments."

        nr_reps = len(cfg.reps)
        if nr_reps == 1: # Not muxed
            init_file = "%s/%s/%s/%s" % (self.content_dir, cfg.content_name, cfg.rel_path, cfg.filename)
            ilf = InitLiveFilter(init_file)
            data = ilf.filter()
        elif nr_reps == 2: # Something that can be muxed
            com_path = "/".join(cfg.rel_path.split("/")[:-1])
            init1 = "%s/%s/%s/%s/%s" % (self.content_dir, cfg.content_name, com_path, cfg.reps[0]['id'], cfg.filename)
            init2 = "%s/%s/%s/%s/%s" % (self.content_dir, cfg.content_name, com_path, cfg.reps[1]['id'], cfg.filename)
            muxed_inits = segmentmuxer.MultiplexInits(init1, init2)
            data = muxed_inits.construct_muxed()
        else:
            data = self.error_response("Bad nr of representations: %d" % nr_reps)
        return data

    def process_media_segment(self, cfg, now_float):
        """Process media segment. Return error response if timing is not OK.

        Assumes that segment ast = (seg_nr+1)*seg_dur, which is compatible with AST=0, startNumber=0."""
        #pylint: disable=too-many-locals
        seg_dur = cfg.seg_duration
        seg_name = cfg.filename
        seg_base, seg_ext = splitext(seg_name)
        seg_nr = int(seg_base)
        if cfg.last_segment_number is not None:
            if seg_nr > cfg.last_segment_number:
                return None
        lmsg = (seg_nr == cfg.last_segment_number)
        #period_start_time = 0
        #media_segment_start_nr = 0
        seg_time = seg_nr*seg_dur
        seg_ast = seg_time + seg_dur

        if not cfg.all_segments_available_flag:
            if now_float < seg_ast:
                return self.error_response("Request for %s was %.1fs too early" % (seg_name, seg_ast - now_float))
            if now_float > seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s:
                diff = now_float - (seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s)
                return self.error_response("Request for %s was %.1fs too late" % (seg_name, diff))

        ref_time_today = quantize(seg_time, SECS_IN_DAY)

        loop_duration = cfg.seg_duration * cfg.vod_nr_segments_in_loop
        time_since_ref_today = seg_time - ref_time_today
        if time_since_ref_today < 0:
            ref_time_today -= SECS_IN_DAY
            time_since_ref_today += SECS_IN_DAY
        nr_loops_done, time_in_loop = divmod(time_since_ref_today, loop_duration)
        offset_at_loop_start = ref_time_today + nr_loops_done*loop_duration
        seg_nr_in_loop = time_in_loop//seg_dur
        vod_nr = seg_nr_in_loop + cfg.vod_first_segment_in_loop
        assert 0 <= vod_nr - cfg.vod_first_segment_in_loop < cfg.vod_nr_segments_in_loop

        rel_path = cfg.rel_path
        nr_reps = len(cfg.reps)
        if nr_reps == 1: # Not muxed
            seg_content = self.filter_media_segment(cfg, cfg.reps[0], rel_path, vod_nr, seg_nr, seg_ext,
                                                    offset_at_loop_start, lmsg)
        else:
            rel_path_parts = rel_path.split("/")
            common_path_parts = rel_path_parts[:-1]
            rel_path1 = "/".join(common_path_parts + [cfg.reps[0]['id']])
            rel_path2 = "/".join(common_path_parts + [cfg.reps[1]['id']])
            seg1 = self.filter_media_segment(cfg, cfg.reps[0], rel_path1, vod_nr, seg_nr, seg_ext,
                                             offset_at_loop_start, lmsg)
            seg2 = self.filter_media_segment(cfg, cfg.reps[1], rel_path2, vod_nr, seg_nr, seg_ext,
                                             offset_at_loop_start, lmsg)
            muxed = segmentmuxer.MultiplexMediaSegments(data1=seg1, data2=seg2)
            seg_content = muxed.mux_on_sample_level()
        return seg_content

    #pylint: disable=too-many-arguments
    def filter_media_segment(self, cfg, rep, rel_path, vod_nr, seg_nr, seg_ext, offset_at_loop_start, lmsg):
        "Filter an actual media segment by using time-scale from init segment."
        media_seg_file = join(self.content_dir, cfg.content_name, rel_path, "%d%s" % (vod_nr, seg_ext))
        timescale = rep['timescale']
        scte35_per_minute = (rep['content_type'] == 'video') and cfg.scte35_per_minute or 0
        offset_from_ast = offset_at_loop_start - cfg.availability_start_time_in_s
        seg_filter = MediaSegmentFilter(media_seg_file, seg_nr, cfg.seg_duration, offset_from_ast, lmsg, timescale,
                                        scte35_per_minute, rel_path)
        seg_content = seg_filter.filter()
        self.new_tfdt_value = seg_filter.get_tfdt_value()
        return seg_content

