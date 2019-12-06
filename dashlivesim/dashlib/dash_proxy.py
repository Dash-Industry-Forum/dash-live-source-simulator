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
from re import findall
from .initsegmentfilter import InitLiveFilter
from .mediasegmentfilter import MediaSegmentFilter
from . import segmentmuxer
from . import mpdprocessor
from .timeformatconversions import make_timestamp, seconds_to_iso_duration
from .configprocessor import ConfigProcessor
from xml.etree import ElementTree as ET

SECS_IN_DAY = 24 * 3600
DEFAULT_MINIMUM_UPDATE_PERIOD = "P100Y"
DEFAULT_MINIMUM_UPDATE_PERIOD_IN_S = SECS_IN_DAY * 365 * 100
DEFAULT_PUBLISH_ADVANCE_IN_S = 7200
EXTRA_TIME_AFTER_END_IN_S = 60
PATCHING_MAXIMUM_UPDATE_LATENCY = 10

UTC_HEAD_PATH = "dash/time.txt"

PUBLISH_TIME = False


def handle_request(host_name, url_parts, args, vod_conf_dir, content_dir, now=None, req=None, is_https=0):
    "Handle Apache request."
    dash_provider = DashProvider(host_name, url_parts, args, vod_conf_dir, content_dir, now, req, is_https)
    return dash_provider.handle_request()


class DashProxyError(Exception):
    "Error in DashProxy."


class DashSegmentNotAvailableError(DashProxyError):
    "Segment not available."


def generate_period_data(mpd_data, now, cfg):
    """Generate an array of period data depending on current time (now) and tsbd. 0 gives one period with start=1000h.

    mpd_data is changed (minimumUpdatePeriod)."""
    # pylint: disable=too-many-locals

    nr_periods_per_hour = min(mpd_data['periodsPerHour'], 60)
    if nr_periods_per_hour not in (-1, 0, 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60):
        raise Exception("Bad nr of periods per hour %d" % nr_periods_per_hour)

    seg_dur = mpd_data['segDuration']
    period_data = []
    ad_frequency = -1
    if mpd_data['insertAd'] > 0:
        ad_frequency = nr_periods_per_hour / mpd_data['xlinkPeriodsPerHour']

    if nr_periods_per_hour == -1:  # Just one period starting at at time start relative AST
        start = 0
        start_number = mpd_data['startNumber'] + start / seg_dur
        data = {'id': "p0", 'start': 'PT%dS' % start, 'startNumber': str(start_number),
                'duration': seg_dur, 'presentationTimeOffset': "%d" % mpd_data['presentationTimeOffset'],
                'start_s' : start}
        period_data.append(data)
    elif nr_periods_per_hour == 0:  # nrPeriodsPerHour == 0, make one old period but starting 1000h after AST
        start = 3600 * 1000
        data = {'id': "p0", 'start': 'PT%dS' % start, 'startNumber': "%d" % (start / seg_dur),
                'duration': seg_dur, 'presentationTimeOffset': "%d" % start, 'start_s' : start}
        period_data.append(data)
    else:  # nr_periods_per_hour > 0
        period_duration = 3600 // nr_periods_per_hour
        half_period_duration = period_duration // 2
        minimum_update_period_s = (half_period_duration - 5)
        if cfg.seg_timeline or cfg.seg_timeline_nr:
            minimum_update_period_s = cfg.seg_duration
        minimum_update_period = "PT%dS" % minimum_update_period_s
        mpd_data['minimumUpdatePeriod'] = minimum_update_period
        this_period_nr = now // period_duration
        last_period_nr = (now + half_period_duration) // period_duration
        this_period_start = this_period_nr * period_duration
        first_period_nr = (now - mpd_data['timeShiftBufferDepthInS'] - seg_dur) // period_duration
        counter = 0
        for period_nr in range(first_period_nr, last_period_nr+1):
            start_time = period_nr * period_duration
            data = {'id' : "p%d" % period_nr, 'start' : 'PT%dS' % start_time,
                    'startNumber' : "%d" % (start_time/seg_dur), 'duration' : seg_dur,
                    'presentationTimeOffset' : period_nr*period_duration,
                    'start_s' : start_time}
            if mpd_data['etpPeriodsPerHour'] > 0:
                # Check whether the early terminated feature is enabled or not.
                # If yes, then proceed.
                nr_etp_periods_per_hour = min(mpd_data['etpPeriodsPerHour'], 60)
                # Limit the maximum value to 60, same as done for the period.
                fraction_nr_periods_to_nr_etp = float(nr_periods_per_hour)/nr_etp_periods_per_hour
                if fraction_nr_periods_to_nr_etp != int(fraction_nr_periods_to_nr_etp):
                    raise Exception("(Number of periods per hour/ Number of etp periods per hour) "
                                    "should be an integer.")
                etp_duration = mpd_data['etpDuration']
                if etp_duration == -1:
                    etp_duration = period_duration / 2
                    # Default value
                    # If no etpDuration is specified, then we take a default values, i.e, half of period duration.
                if etp_duration > period_duration:
                    raise Exception("Duration of the early terminated period should be less that the duration of a "
                                    "regular period")
                if period_nr % fraction_nr_periods_to_nr_etp == 0:
                    data['etpDuration'] = etp_duration
                    data['period_duration_s'] = etp_duration

            if mpd_data['mpdCallback'] > 0:
                # Check whether the mpdCallback feature is enabled or not.
                # If yes, then proceed.
                nr_callback_periods_per_hour = min(mpd_data['mpdCallback'], 60)
                # Limit the maximum value to 60, same as done for the period.
                fraction_nr_periods_to_nr_callback = float(nr_periods_per_hour)/nr_callback_periods_per_hour
                if fraction_nr_periods_to_nr_callback != int(fraction_nr_periods_to_nr_callback):
                    raise Exception("(Number of periods per hour/ Number of callback periods per hour) "
                                    "should be an integer.")
                if period_nr % fraction_nr_periods_to_nr_callback == 0:
                    data['mpdCallback'] = 1
                    # If this period meets the condition, we raise a flag.
                    # We use the flag later to decide to put a mpdCallback element or not.

            period_data.append(data)
            if ad_frequency > 0 and ((period_nr % ad_frequency) == 0) and counter > 0:
                period_data[counter - 1]['periodDuration'] = 'PT%dS' % period_duration
                period_data[counter - 1]['period_duration_s'] = period_duration
            counter = counter + 1
            # print period_data
        for i, pdata in enumerate(period_data):
            if i != len(period_data) - 1: # not last periodDuration
                if not pdata.has_key('period_duration_s'):
                    pdata['period_duration_s'] = period_duration
    return period_data


def generate_response_with_xlink(response, cfg, filename, nr_periods_per_hour, nr_xlink_periods_per_hour, insert_ad):
    "Convert the normally created response into a response which has xlinks"
    # This functions has two functionality : 1.For MPD and 2.For PERIOD.
    # 1. When the normally created .mpd file is fed to this function, it removes periods and inserts xlink for the
    # corresponding periods at that place.
    # 2. When the xlink period is accessed, it extracts the corresponding period from .mpd file this function generates,
    # adds some information and returns the appropriate .xml document to the java client.
    # pylint: disable=too-many-locals, too-many-statements
    if cfg == ".mpd":
        root = ET.fromstring(response)
        period_id_all = []
        for child in root.findall('{urn:mpeg:dash:schema:mpd:2011}Period'):
            period_id_all.append(child.attrib['id'])
        # period_id_all = findall('Period id="([^"]*)"', response)
        # Find all period ids in the response file.
        one_xlinks_for_how_many_periods = nr_periods_per_hour / nr_xlink_periods_per_hour
        period_id_xlinks = [x for x in period_id_all if int(x[1:]) % one_xlinks_for_how_many_periods == 0]
        # Periods that will be replaced with links.
        base_url = findall('<BaseURL>([^"]*)</BaseURL>', response)
        counter = 0
        for period_id in period_id_all:
            # Start replacing only if this condition is met.
            start_pos_period = response.find(period_id) - 12
            # Find the position in the string file of the period that has be replaced
            end_pos_period = response.find("</Period>", start_pos_period) + 9
            # End position of the corresponding period.
            if period_id in period_id_xlinks:
                counter += 1
                original_period = response[start_pos_period:end_pos_period]
                if insert_ad == 4:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/invalid' \
                                   'url.php" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/xlink">' \
                                   '</Period>'
                elif insert_ad == 3:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php' \
                                   '?id=6_ad_twoperiods_withremote" xlink:actuate="onLoad" xmlns:xlink="http://www.' \
                                   'w3.org/1999/xlink"></Period>'
                elif insert_ad == 2:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php' \
                                   '?id=6_ad_twoperiods" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/' \
                                   'xlink"></Period>'
                elif insert_ad == 1 or insert_ad == 5:
                    xlink_period = '<Period xlink:href="http://vm1.dashif.org/dynamicxlink/ad.php?' \
                                   'id=6_ad" xlink:actuate="onLoad" xmlns:xlink="http://www.w3.org/1999/xlink">' \
                                   '</Period>'
                else:
                    xlink_period = '<Period xlink:href="%s%s+%s.period" xlink:actuate="onLoad" ' \
                                   'xmlns:xlink="http://www.w3.org/1999/xlink"></Period>' % (
                                       base_url[0], filename, period_id)
                if insert_ad > 0 and counter == 1:  # This condition ensures that the first period in the mpd is not
                    # replaced when the ads are enabled.
                    response = insert_asset_identifier(response,
                                                       start_pos_period)  # Insert asset identifier,
                                                                          # if the the period is not replaced.
                    continue
                if insert_ad == 5:  # Add additional content for the default content
                    start_pos_period_contents = original_period.find('>') + 1
                    xlink_period = xlink_period[:-9] + '\n<!--Default content that will be played if the xlink is not' \
                                                       ' able to load.-->' + original_period[start_pos_period_contents:]
                response = response.replace(original_period, xlink_period)
            else:
                if insert_ad > 0:
                    response = insert_asset_identifier(response, start_pos_period)
    else:
        # This will be done when ".period" file is being requested
        # Start manipulating the original period so that it looks like .period in the static xlink file.
        filename = filename.split('+')[1]
        # Second part of string has the period id.
        start_pos_xmlns = response.find("xmlns=")
        end_pos_xmlns = response.find('"', start_pos_xmlns + 7) + 1
        start_pos_period = response.find(filename[:-7]) - 12
        # Find the position in the string file of the period that has be replaced.
        end_pos_period = response.find("</Period>", start_pos_period) + 9
        # End position of the corresponding period.
        original_period = response[start_pos_period:end_pos_period]
        original_period = original_period.replace('">', '" ' + response[start_pos_xmlns:end_pos_xmlns] + '>', 1)
        # xml_intro = '<?xml version="1.0" encoding="utf-8"?>\n'
        # response = xml_intro + original_period
        response = original_period
    return response


def insert_asset_identifier(response, start_pos_period):
    ad_pos = response.find(">", start_pos_period) + 1
    response = response[:ad_pos] + "\n<AssetIdentifier schemeIdUri=\"urn:org:dashif:asset-id:2013\" value=\"md:cid:" \
                                   "EIDR:10.5240%2f0EFB-02CD-126E-8092-1E49-W\"></AssetIdentifier>" + response[ad_pos:]
    return response


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

    def handle_request(self):
        "Handle the HTTP request."
        return self.parse_url()

    def error_response(self, msg):
        "Return a mod_python error response."
        if self.req:
            self.req.log_error("dash_proxy: [%s] %s" % ("/".join(self.url_parts[-3:]), msg))
        return {'ok': False, 'pl': msg + "\n"}

    # pylint:disable = too-many-locals, too-many-branches
    def parse_url(self):
        "Parse the absolute URL that is received in mod_python."
        cfg_processor = ConfigProcessor(self.vod_conf_dir, self.base_url)
        cfg_processor.process_url(self.url_parts, self.now)
        cfg = cfg_processor.getconfig()
        if cfg.ext == ".mpd" or cfg.ext == ".period":
            if cfg.ext == ".period":
                mpd_filename = "%s/%s/%s" % (self.content_dir, cfg.content_name, cfg.filename.split('+')[0])
                # Get the first part of the string only, which is the .manifest file name.
            else:
                mpd_filename = "%s/%s/%s" % (self.content_dir, cfg.content_name, cfg.filename)
            mpd_input_data = cfg_processor.get_mpd_data()
            nr_xlink_periods_per_hour = min(mpd_input_data['xlinkPeriodsPerHour'], 60)
            nr_periods_per_hour = min(mpd_input_data['periodsPerHour'], 60)
            # See exception description for explanation.
            if nr_xlink_periods_per_hour > 0:
                if nr_periods_per_hour == -1:
                    raise Exception("Xlinks can only be created for a multiperiod service.")
                one_xlinks_for_how_many_periods = float(nr_periods_per_hour) / nr_xlink_periods_per_hour
                if one_xlinks_for_how_many_periods != int(one_xlinks_for_how_many_periods):
                    raise Exception("(Number of periods per hour/ Number of xlinks per hour should be an integer.")
            if mpd_input_data['insertAd'] > 0 and nr_xlink_periods_per_hour < 0:
                raise Exception("Insert ad option can only be used in conjuction with the xlink option. To use the "
                                "insert ad option, also set use xlink_m in your url.")
            response = self.generate_dynamic_mpd(cfg, mpd_filename, mpd_input_data, self.now)
            #The following 'if' is for IOP 4.11.4.3 , deployment scenario when segments not found.
            if len(cfg.multi_url) > 0 and cfg.segtimelineloss == True:  # There is one specific baseURL with losses specified
                    a_var, b_var = cfg.multi_url[0].split("_")
                    dur1 = int(a_var[1:])
                    dur2 = int(b_var[1:])
                    total_dur = dur1 + dur2
                    num_loop = int(ceil(60.0 / (float(total_dur))))
                    now_mod_60 = self.now % 60
                    if a_var[0] == 'u' and b_var[0] == 'd':  # parse server up or down information
                        for i in range(num_loop):
                            if i * total_dur + dur1 < now_mod_60 <= (i + 1) * total_dur:
                                #Generate and provide mpd with the latest up time, so that last generated segment is shown
                                #and no new S element added to SegmentTimeline.
                                latestUptime= self.now - now_mod_60 + (i * total_dur + dur1)
                                response = self.generate_dynamic_mpd(cfg, mpd_filename, mpd_input_data, latestUptime)
                                break
                            elif now_mod_60 == i* total_dur +dur1:
                                #Just before down time starts, add InbandEventStream to the MPD.
                                cfg.emsg_last_seg=True
                                response = self.generate_dynamic_mpd(cfg, mpd_filename, mpd_input_data, self.now)
                                cfg.emsg_last_seg=False

            if nr_xlink_periods_per_hour > 0:
                response = generate_response_with_xlink(response, cfg.ext, cfg.filename, nr_periods_per_hour,
                                                        nr_xlink_periods_per_hour, mpd_input_data['insertAd'])

        # Manifest patch update, separate out here as the xlink logic is unsafe in assuming all periods will
        # be present in response to perform the replacement
        elif cfg.ext == ".patch":
            mpd_filename = "%s/%s/%s.mpd" % (self.content_dir, cfg.content_name, cfg.filename.split('.')[0])
            mpd_input_data = cfg_processor.get_mpd_data()
            response = self.generate_dynamic_mpd(cfg, mpd_filename, mpd_input_data, self.now)

        elif cfg.ext == ".mp4":  # Init segment
            if self.now < cfg.availability_start_time_in_s - cfg.init_seg_avail_offset:
                diff = (cfg.availability_start_time_in_s - cfg.init_seg_avail_offset) - self.now_float
                response = self.error_response("Request for %s was %.1fs too early" % (cfg.filename, diff))
            else:
                response = self.process_init_segment(cfg)
        elif cfg.ext in (".m4s", ".jpg"):  # Media segment or thumbnail
            if cfg.availability_time_offset_in_s == -1:
                first_segment_ast = cfg.availability_start_time_in_s
            else:
                first_segment_ast = cfg.availability_start_time_in_s + cfg.seg_duration - \
                                    cfg.availability_time_offset_in_s

            if self.now_float < first_segment_ast:
                diff = first_segment_ast - self.now_float
                response = self.error_response("Request %s before first seg AST. %.1fs too early" %
                                               (cfg.filename, diff))
            elif cfg.availability_end_time is not None and \
                            self.now > cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S:
                diff = self.now_float - (cfg.availability_end_time + EXTRA_TIME_AFTER_END_IN_S)
                response = self.error_response("Request for %s after AET. %.1fs too late" % (cfg.filename, diff))
            elif cfg.ext == ".m4s":
                response = self.process_media_segment(cfg, self.now_float)
                if len(cfg.multi_url) == 1:  # There is one specific baseURL with losses specified
                    a_var, b_var = cfg.multi_url[0].split("_")
                    dur1 = int(a_var[1:])
                    dur2 = int(b_var[1:])
                    total_dur = dur1 + dur2
                    num_loop = int(ceil(60.0 / (float(total_dur))))
                    now_mod_60 = self.now % 60
                    if a_var[0] == 'u' and b_var[0] == 'd':  # parse server up or down information
                        for i in range(num_loop):
                            if i * total_dur + dur1 < now_mod_60 <= (i + 1) * total_dur:
                                response = self.error_response("BaseURL server down at %d" % (self.now))
                                break
                            elif now_mod_60 == i* total_dur +dur1:     #Just before down time starts, add emsg box to the segment.
                                cfg.emsg_last_seg=True
                                response = self.process_media_segment(cfg, self.now_float)
                                cfg.emsg_last_seg=False
                    elif a_var[0] == 'd' and b_var[0] == 'u':
                        for i in range(num_loop):
                            if i * (total_dur) < now_mod_60 <= i * (total_dur) + dur1:
                                response = self.error_response("BaseURL server down at %d" % (self.now))
                                break
            else:  # cfg.ext == ".jpg"
                response = self.process_thumbnail(cfg, self.now_float)
        else:
            response = "Unknown file extension: %s" % cfg.ext
        return response

    # pylint: disable=no-self-use
    def generate_dynamic_mpd(self, cfg, mpd_filename, in_data, now):
        "Generate the dynamic MPD."
        mpd_data = in_data.copy()
        if cfg.minimum_update_period_in_s is not None:
            mpd_data['minimumUpdatePeriod'] = seconds_to_iso_duration(cfg.minimum_update_period_in_s)
            minimum_update_period_in_s = cfg.minimum_update_period_in_s
        else:
            mpd_data['minimumUpdatePeriod'] = DEFAULT_MINIMUM_UPDATE_PERIOD
            minimum_update_period_in_s = DEFAULT_MINIMUM_UPDATE_PERIOD_IN_S

        if cfg.media_presentation_duration is not None:
            mpd_data['mediaPresentationDuration'] = seconds_to_iso_duration(cfg.media_presentation_duration)
        mpd_data['id'] = cfg.content_name # default in case content has none, required for patching
        mpd_data['timeShiftBufferDepth'] = seconds_to_iso_duration(cfg.timeshift_buffer_depth_in_s)
        mpd_data['timeShiftBufferDepthInS'] = cfg.timeshift_buffer_depth_in_s
        mpd_data['startNumber'] = cfg.adjusted_start_number
        mpd_data['publishTime'] = '%s' % make_timestamp(in_data['publishTime'])
        mpd_data['availabilityStartTime'] = '%s' % make_timestamp(in_data['availability_start_time_in_s'])
        mpd_data['duration'] = '%d' % in_data['segDuration']
        mpd_data['maxSegmentDuration'] = 'PT%dS' % in_data['segDuration']
        timescale = 1
        pto = 0
        mpd_data['presentationTimeOffset'] = cfg.adjusted_pto(pto, timescale)
        mpd_data['availabilityTimeOffset'] = '%f' % in_data['availability_time_offset_in_s']
        if mpd_data['suggested_presentation_delay_in_s'] is not None:
            spd = in_data['suggested_presentation_delay_in_s']
            mpd_data['suggestedPresentationDelay'] = \
                seconds_to_iso_duration(spd)
        if in_data.has_key('availabilityEndTime'):
            mpd_data['availabilityEndTime'] = make_timestamp(in_data['availabilityEndTime'])
        if cfg.stop_time is not None and (now > cfg.stop_time):
            mpd_data['type'] = "static"
        mpd_proc_cfg = {'scte35Present': (cfg.scte35_per_minute > 0),
                        'continuous': in_data['continuous'],
                        'segtimeline': in_data['segtimeline'],
                        'segtimeline_nr': in_data['segtimeline_nr'],
                        'patching': in_data['patching'],
                        'utc_timing_methods': cfg.utc_timing_methods,
                        'utc_head_url': self.utc_head_url,
                        'now': now,
                        'patch_base': cfg.patch_base,
                        'patch_ttl': minimum_update_period_in_s * PATCHING_MAXIMUM_UPDATE_LATENCY}
        full_url = self.base_url + '/'.join(self.url_parts)
        mpmod = mpdprocessor.MpdProcessor(mpd_filename, mpd_proc_cfg, cfg,
                                          full_url)
        period_data = generate_period_data(mpd_data, now, cfg)
        mpmod.process(mpd_data, period_data)
        return mpmod.get_full_xml()

    def process_init_segment(self, cfg):
        "Read non-multiplexed or create muxed init segments."

        nr_reps = len(cfg.reps)
        if nr_reps == 1:  # Not muxed
            init_file = "%s/%s/%s/%s" % (self.content_dir, cfg.content_name, cfg.rel_path, cfg.filename)
            ilf = InitLiveFilter(init_file)
            data = ilf.filter()
        elif nr_reps == 2:  # Something that can be muxed
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
            return self.error_response("Request for segment %d before first %d" % (seg_nr, seg_start_nr))
        stop_number = cfg.stop_number
        if stop_number and seg_nr >= stop_number:
            return self.error_response("Beyond last segment %d" % stop_number)
        if len(cfg.last_segment_numbers) > 0:
            very_last_segment = cfg.last_segment_numbers[-1]
            if seg_nr > very_last_segment:
                return self.error_response("Request for segment %d beyond last (%d)" % (seg_nr, very_last_segment))
        lmsg = seg_nr in cfg.last_segment_numbers
        # print cfg.last_segment_numbers
        timescale = 1
        media_time_at_ast = cfg.adjusted_pto(0, timescale)
        seg_time = (seg_nr - seg_start_nr) * seg_dur + media_time_at_ast
        seg_ast = (seg_time + seg_dur - media_time_at_ast) + \
                  cfg.availability_start_time_in_s

        if cfg.availability_time_offset_in_s != -1:  # - 1 is infinity
            if now_float < seg_ast - cfg.availability_time_offset_in_s:
                return self.error_response("Request for %s was %.1fs too early" % (seg_name, seg_ast - now_float))
            # If stop_number is not None, the manifest will become static
            if ((now_float > seg_ast + seg_dur +
                    cfg.timeshift_buffer_depth_in_s) and not stop_number):
                diff = now_float - (seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s)
                return self.error_response("Request for %s was %.1fs too late" % (seg_name, diff))

        loop_duration = cfg.seg_duration * cfg.vod_nr_segments_in_loop
        nr_loops_done, time_in_loop = divmod(seg_time, loop_duration)
        offset_at_loop_start = nr_loops_done * loop_duration
        seg_nr_in_loop = time_in_loop // seg_dur
        vod_nr = seg_nr_in_loop + cfg.vod_first_segment_in_loop
        assert 0 <= vod_nr - cfg.vod_first_segment_in_loop < cfg.vod_nr_segments_in_loop
        rel_path = cfg.rel_path
        nr_reps = len(cfg.reps)
        if nr_reps == 1:  # Not muxed
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

    # pylint: disable=too-many-arguments
    def filter_media_segment(self, cfg, rep, rel_path, vod_nr, seg_nr, seg_ext, offset_at_loop_start, lmsg):
        "Filter an actual media segment by using time-scale from init segment."
        media_seg_file = join(self.content_dir, cfg.content_name, rel_path, "%d%s" % (vod_nr, seg_ext))
        timescale = rep['timescale']
        scte35_per_minute = (rep['content_type'] == 'video') and cfg.scte35_per_minute or 0
        is_ttml = rep['content_type'] == 'subtitles'
        seg_filter = MediaSegmentFilter(media_seg_file, seg_nr, cfg.seg_duration, offset_at_loop_start, lmsg, timescale,
                                        scte35_per_minute, rel_path,
                                        is_ttml,
                                        insert_sidx=cfg.insert_sidx,emsg_last_seg=cfg.emsg_last_seg,now=self.now)
        seg_content = seg_filter.filter()
        self.new_tfdt_value = seg_filter.get_tfdt_value()
        return seg_content

    def process_thumbnail(self, cfg, now_float):
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
            return self.error_response("Request for segment %d before first %d" % (seg_nr, seg_start_nr))
        if len(cfg.last_segment_numbers) > 0:
            very_last_segment = cfg.last_segment_numbers[-1]
            if seg_nr > very_last_segment:
                return self.error_response("Request for segment %d beyond last (%d)" % (seg_nr, very_last_segment))
        lmsg = seg_nr in cfg.last_segment_numbers
        # print cfg.last_segment_numbers
        seg_time = (seg_nr - seg_start_nr) * seg_dur + cfg.availability_start_time_in_s
        seg_ast = seg_time + seg_dur

        if cfg.availability_time_offset_in_s != -1:  # -1 is infinity
            if now_float < seg_ast - cfg.availability_time_offset_in_s:
                return self.error_response("Request for %s was %.1fs too early" % (seg_name, seg_ast - now_float))
            if ((now_float > seg_ast + seg_dur +
                    cfg.timeshift_buffer_depth_in_s) and not stop_number):
                diff = now_float - (seg_ast + seg_dur + cfg.timeshift_buffer_depth_in_s)
                return self.error_response("Request for %s was %.1fs too late" % (seg_name, diff))

        time_since_ast = seg_time - cfg.availability_start_time_in_s
        loop_duration = cfg.seg_duration * cfg.vod_nr_segments_in_loop
        nr_loops_done, time_in_loop = divmod(time_since_ast, loop_duration)
        seg_nr_in_loop = time_in_loop // seg_dur
        vod_nr = seg_nr_in_loop + cfg.vod_first_segment_in_loop
        assert 0 <= vod_nr - cfg.vod_first_segment_in_loop < cfg.vod_nr_segments_in_loop
        rel_path = cfg.rel_path
        thumb_path = join(self.content_dir, cfg.content_name, rel_path,
                        "%d%s" % (vod_nr, seg_ext))
        with open(thumb_path, 'rb') as ifh:
            seg_content = ifh.read()
        return seg_content