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
from math import ceil
from collections import namedtuple

from dashlivesim.dashlib.initsegmentfilter import InitLiveFilter, InitFilter
from dashlivesim.dashlib.mediasegmentfilter import MediaSegmentFilter
from dashlivesim.dashlib import segmentmuxer
from dashlivesim.dashlib.configprocessor import ConfigProcessor
from dashlivesim.dashlib import chunker

SECS_IN_DAY = 24 * 3600
DEFAULT_MINIMUM_UPDATE_PERIOD = "P100Y"
DEFAULT_PUBLISH_ADVANCE_IN_S = 7200
EXTRA_TIME_AFTER_END_IN_S = 60

UTC_HEAD_PATH = "dash/time.txt"

PUBLISH_TIME = False

ChunkedSegment = namedtuple("ChunkedSegment", "seg_start chunks")


def createProvider(host_name, url_parts, args, vod_conf_dir, content_dir, now=None, req=None, is_https=0):
    "Create DashProvider so that we can handle request later."
    return DashProvider(host_name, url_parts, args, vod_conf_dir, content_dir, now, req, is_https)


class DashProxyError(Exception):
    "Error in DashProxy."


class DashSegmentNotAvailableError(DashProxyError):
    "Segment not available."


class DashProvider(object):
    "Provide DASH manifest and segments."

    # pylint: disable=too-many-instance-attributes,too-many-arguments

    def __init__(self, host_name, url_parts, url_args, vod_conf_dir, content_dir, now=None, req=None, is_https=0):
        protocol = is_https and "https" or "http"
        self.base_url = "%s://%s/%s/" % (protocol, host_name, url_parts[0])  # The start. Adding other parts later.
        self.utc_head_url = "%s://%s/%s" % (protocol, host_name, UTC_HEAD_PATH)
        self.url_parts = url_parts[1:]
        self.url_args = url_args
        self.vod_conf_dir = vod_conf_dir
        self.content_dir = content_dir
        self.now_float = now  # float
        self.now = int(now)
        self.req = req
        self.new_tfdt_value = None
        self.cfg_processor = ConfigProcessor(self.vod_conf_dir, self.base_url)
        self.cfg_processor.process_url(self.url_parts, self.now)
        self.cfg = self.cfg_processor.getconfig()


def error_response(dashProv, msg):
    "Return a mod_python error response."
    if dashProv.req:
        dashProv.req.log_error("dash_proxy: [%s] %s" % ("/".join(dashProv.url_parts[-3:]), msg))
    return {'ok': False, 'pl': msg + "\n"}


def get_init(dashProv):
    cfg = dashProv.cfg
    if cfg.ext != ".mp4":  # Init segment
        raise ValueError("Bad extension for init segment")
    if dashProv.now < cfg.availability_start_time_in_s - cfg.init_seg_avail_offset:
        diff = (cfg.availability_start_time_in_s - cfg.init_seg_avail_offset) - dashProv.now_float
        response = error_response(dashProv, "Request for %s was %.1fs too early" % (cfg.filename, diff))
    else:
        response = process_init_segment(dashProv)
    return response


def get_media(dashProv, chunk=False):
    cfg = dashProv.cfg
    if cfg.ext not in (".m4s", ".jpg"):  # Media segment or thumbnail
        raise ValueError(f"Extension {cfg.ext} not for media")
    if cfg.availability_time_offset_in_s == -1:
        first_segment_ast = cfg.availability_start_time_in_s
    else:
        first_segment_ast = cfg.availability_start_time_in_s + cfg.seg_duration - \
                            cfg.availability_time_offset_in_s

    if dashProv.now_float < first_segment_ast:
        diff = first_segment_ast - dashProv.now_float
        response = error_response(dashProv, "Request %s before first seg AST. %.1fs too early" %
                                            (cfg.filename, diff))
    elif (cfg.availability_end_time is not None and
            dashProv.now > cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S):
        diff = dashProv.now_float - (cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S)
        response = error_response(dashProv, "Request for %s after AET. %.1fs too late" % (cfg.filename, diff))
    elif cfg.ext == ".m4s":
        response = process_media_segment(dashProv, dashProv.now_float, chunk)
        if len(cfg.multi_url) == 1:  # There is one specific baseURL with losses specified
            a_var, b_var = cfg.multi_url[0].split("_")
            dur1 = int(a_var[1:])
            dur2 = int(b_var[1:])
            total_dur = dur1 + dur2
            num_loop = int(ceil(60.0 / (float(total_dur))))
            now_mod_60 = dashProv.now % 60
            if a_var[0] == 'u' and b_var[0] == 'd':  # parse server up or down information
                for i in range(num_loop):
                    if i * total_dur + dur1 < now_mod_60 <= (i + 1) * total_dur:
                        response = error_response(dashProv, "BaseURL server down at %d" % (dashProv.now))
                        break
                    elif now_mod_60 == i * total_dur + dur1:
                        # Just before down time starts, add emsg box to the segment.
                        cfg.emsg_last_seg = True
                        response = process_media_segment(dashProv, dashProv.now_float)
                        cfg.emsg_last_seg = False
            elif a_var[0] == 'd' and b_var[0] == 'u':
                for i in range(num_loop):
                    if i * (total_dur) < now_mod_60 <= i * (total_dur) + dur1:
                        response = error_response(dashProv, "BaseURL server down at %d" % (dashProv.now))
                        break
    else:  # cfg.ext == ".jpg"
        response = process_thumbnail(dashProv, dashProv.now_float)
    return response


def process_init_segment(dashProv):
    "Read non-multiplexed or create muxed init segments."
    cfg = dashProv.cfg

    nr_reps = len(cfg.reps)
    if nr_reps == 1:  # Not muxed
        init_file = "%s/%s/%s/%s" % (dashProv.content_dir, cfg.content_name, cfg.rel_path, cfg.filename)
        ilf = InitLiveFilter(init_file)
        data = ilf.filter()
    elif nr_reps == 2:  # Something that can be muxed
        com_path = "/".join(cfg.rel_path.split("/")[:-1])
        init1 = "%s/%s/%s/%s/%s" % (dashProv.content_dir, cfg.content_name, com_path, cfg.reps[0]['id'], cfg.filename)
        init2 = "%s/%s/%s/%s/%s" % (dashProv.content_dir, cfg.content_name, com_path, cfg.reps[1]['id'], cfg.filename)
        muxed_inits = segmentmuxer.MultiplexInits(init1, init2)
        data = muxed_inits.construct_muxed()
    else:
        data = error_response(dashProv, "Bad nr of representations: %d" % nr_reps)
    return data


def process_media_segment(dashProv, now_float, chunk):
    """Process media segment. Return error response if timing is not OK.

    Assumes that segment_ast = (seg_nr+1-startNumber)*seg_dur + ast."""

    # pylint: disable=too-many-locals

    def get_timescale(cfg):
        "Get timescale for the current representation."
        timescale = None
        curr_rep_id = cfg.rel_path
        for rep in cfg.reps:
            if rep['id'] == curr_rep_id:
                timescale = rep['timescale']
                break
        return timescale
    cfg = dashProv.cfg
    seg_dur = cfg.seg_duration
    seg_name = cfg.filename
    seg_base, seg_ext = splitext(seg_name)
    timescale = get_timescale(cfg)
    if seg_base[0] == 't':
        # TODO. Make a more accurate test here that the timestamp is a correct one
        seg_nr = int(round(float(seg_base[1:]) / seg_dur / timescale))
    else:
        seg_nr = int(seg_base)
    seg_start_nr = cfg.start_nr == -1 and 1 or cfg.adjusted_start_number
    if seg_nr < seg_start_nr:
        return error_response(dashProv, "Request for segment %d before first %d" % (seg_nr, seg_start_nr))
    stop_number = cfg.stop_number
    if stop_number and seg_nr >= stop_number:
        return error_response(dashProv, "Beyond last segment %d" % stop_number)
    if len(cfg.last_segment_numbers) > 0:
        very_last_segment = cfg.last_segment_numbers[-1]
        if seg_nr > very_last_segment:
            return error_response(dashProv, "Request for segment %d beyond last (%d)" % (seg_nr, very_last_segment))
    lmsg = seg_nr in cfg.last_segment_numbers
    # print cfg.last_segment_numbers
    timescale = 1
    media_time_at_ast = cfg.adjusted_pto(0, timescale)
    seg_time = (seg_nr - seg_start_nr) * seg_dur + media_time_at_ast
    seg_ast = (seg_time + seg_dur - media_time_at_ast) + cfg.availability_start_time_in_s

    if cfg.availability_time_offset_in_s != -1:  # - 1 is infinity
        if now_float < seg_ast - cfg.availability_time_offset_in_s:
            return error_response(dashProv, "Request for %s was %.1fs too early" % (seg_name, seg_ast - now_float))
        # If stop_number is not None, the manifest will become static
        if ((now_float > seg_ast + seg_dur +
                cfg.timeshift_buffer_depth_in_s) and not stop_number):
            diff = now_float - (seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s)
            return error_response(dashProv, "Request for %s was %.1fs too late" % (seg_name, diff))

    loop_duration = cfg.seg_duration * cfg.vod_nr_segments_in_loop
    nr_loops_done, time_in_loop = divmod(seg_time, loop_duration)
    offset_at_loop_start = nr_loops_done * loop_duration
    seg_nr_in_loop = time_in_loop // seg_dur
    vod_nr = seg_nr_in_loop + cfg.vod_first_segment_in_loop
    assert 0 <= vod_nr - cfg.vod_first_segment_in_loop < cfg.vod_nr_segments_in_loop
    rel_path = cfg.rel_path
    nr_reps = len(cfg.reps)
    if nr_reps == 1:  # Not muxed
        if chunk:
            trex_data = get_trex_data(dashProv, rel_path)
            seg_content = filter_media_segment(dashProv, cfg.reps[0], rel_path, vod_nr, seg_nr, seg_ext,
                                               offset_at_loop_start, lmsg, trex_data)
            # Here we shall return seg_time (when the segment start to be produced)
            # and then each chunk should be delivered at seg_time + (i+1) * chunk_dur
            dur = int(cfg.chunk_duration_in_s * cfg.reps[0]['timescale'])
            chunks = [chk for chk in chunker.chunk(seg_content, dur, trex_data)]
            return ChunkedSegment(seg_time, chunks)
        else:
            seg_content = filter_media_segment(dashProv, cfg.reps[0], rel_path, vod_nr, seg_nr, seg_ext,
                                               offset_at_loop_start, lmsg)
    else:
        rel_path_parts = rel_path.split("/")
        common_path_parts = rel_path_parts[:-1]
        rel_path1 = "/".join(common_path_parts + [cfg.reps[0]['id']])
        rel_path2 = "/".join(common_path_parts + [cfg.reps[1]['id']])
        seg1 = filter_media_segment(dashProv, cfg.reps[0], rel_path1, vod_nr, seg_nr, seg_ext,
                                    offset_at_loop_start, lmsg)
        seg2 = filter_media_segment(dashProv, cfg.reps[1], rel_path2, vod_nr, seg_nr, seg_ext,
                                    offset_at_loop_start, lmsg)
        muxed = segmentmuxer.MultiplexMediaSegments(data1=seg1, data2=seg2)
        seg_content = muxed.mux_on_sample_level()
    return seg_content


def get_trex_data(dashProv, rel_path):
    "Get object which has default_sample_duration and other trex data."
    cfg = dashProv.cfg
    init_file = join(dashProv.content_dir, cfg.content_name, rel_path, "init.mp4")
    init_filter = InitFilter(init_file)
    init_filter.filter()
    return init_filter


# pylint: disable=too-many-arguments
def filter_media_segment(dashProv, rep, rel_path, vod_nr, seg_nr, seg_ext, offset_at_loop_start, lmsg, trex_data=None):
    "Filter an actual media segment by using time-scale from init segment."
    cfg = dashProv.cfg
    media_seg_file = join(dashProv.content_dir, cfg.content_name, rel_path, "%d%s" % (vod_nr, seg_ext))
    timescale = rep['timescale']
    scte35_per_minute = (rep['content_type'] == 'video') and cfg.scte35_per_minute or 0
    is_ttml = rep['content_type'] == 'subtitles'
    default_sample_duration = trex_data.default_sample_duration if trex_data is not None else None
    seg_filter = MediaSegmentFilter(media_seg_file, seg_nr, cfg.seg_duration, offset_at_loop_start, lmsg, timescale,
                                    scte35_per_minute, rel_path,
                                    is_ttml,
                                    default_sample_duration,
                                    insert_sidx=cfg.insert_sidx, emsg_last_seg=cfg.emsg_last_seg,
                                    now=dashProv.now)
    seg_content = seg_filter.filter()
    dashProv.new_tfdt_value = seg_filter.get_tfdt_value()  # Why set this in dashProv?? TODO
    return seg_content


def process_thumbnail(dashProv, now_float):
    """Process thumbnail. Return error response if timing is not OK.

    Assumes that segment_ast = (seg_nr+1-startNumber)*seg_dur."""

    # pylint: disable=too-many-locals

    def get_timescale(cfg):
        "Get timescale for the current representation."
        timescale = None
        curr_rep_id = cfg.rel_path
        for rep in cfg.reps:
            if rep['id'] == curr_rep_id:
                timescale = rep['timescale']
                break
        return timescale

    cfg = dashProv.cfg
    seg_dur = cfg.seg_duration
    seg_name = cfg.filename
    seg_base, seg_ext = splitext(seg_name)
    timescale = get_timescale(cfg)
    if seg_base[0] == 't':
        # TODO. Make a more accurate test here that the timestamp is a correct one
        seg_nr = int(round(float(seg_base[1:]) / seg_dur / timescale))
    else:
        seg_nr = int(seg_base)
    seg_start_nr = cfg.start_nr == -1 and 1 or cfg.start_nr
    if seg_nr < seg_start_nr:
        return error_response("Request for segment %d before first %d" % (seg_nr, seg_start_nr))
    if len(cfg.last_segment_numbers) > 0:
        very_last_segment = cfg.last_segment_numbers[-1]
        if seg_nr > very_last_segment:
            return error_response("Request for segment %d beyond last (%d)" % (seg_nr, very_last_segment))
    # lmsg = seg_nr in cfg.last_segment_numbers
    # print cfg.last_segment_numbers
    seg_time = (seg_nr - seg_start_nr) * seg_dur + cfg.availability_start_time_in_s
    seg_ast = seg_time + seg_dur

    if cfg.availability_time_offset_in_s != -1:  # -1 is infinity
        if now_float < seg_ast - cfg.availability_time_offset_in_s:
            return error_response("Request for %s was %.1fs too early" % (seg_name, seg_ast - now_float))
        if (now_float > seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s):
            diff = now_float - (seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s)
            return error_response("Request for %s was %.1fs too late" % (seg_name, diff))

    time_since_ast = seg_time - cfg.availability_start_time_in_s
    loop_duration = cfg.seg_duration * cfg.vod_nr_segments_in_loop
    nr_loops_done, time_in_loop = divmod(time_since_ast, loop_duration)
    seg_nr_in_loop = time_in_loop // seg_dur
    vod_nr = seg_nr_in_loop + cfg.vod_first_segment_in_loop
    assert 0 <= vod_nr - cfg.vod_first_segment_in_loop < cfg.vod_nr_segments_in_loop
    rel_path = cfg.rel_path
    thumb_path = join(dashProv.content_dir, cfg.content_name, rel_path,
                      "%d%s" % (vod_nr, seg_ext))
    with open(thumb_path, 'rb') as ifh:
        seg_content = ifh.read()
    return seg_content
