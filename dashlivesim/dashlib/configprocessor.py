"""Get config depending on url. The URL specifies content but can also have parameters."""

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

import ConfigParser
from os.path import join, splitext
from collections import namedtuple
from .moduloperiod import ModuloPeriod

DEFAULT_AVAILABILITY_STARTTIME_IN_S = 0 # Jan 1 1970 00:00 UTC
DEFAULT_AVAILABILITY_TIME_OFFSET_IN_S = 0
DEFAULT_TIMESHIFT_BUFFER_DEPTH_IN_SECS = 300
DEFAULT_SHORT_MINIMUM_UPDATE_PERIOD_IN_S = 10

MUX_DIVIDER = "__" # Multiplexed representations can be written as A__V

SEGTIMEFORMAT = 'HHII' # Format for segment durations and repeatcount (nr, repeat, start, duration)
SegTimeEntry = namedtuple('SegTimeEntry', ['start_nr', 'repeats', 'start_time', 'duration'])


class ConfigProcessorError(Exception):
    "Generic error for DASH ConfigProcessor."
    pass

def quantize(number, step):
    "Quantize number to a multiple of step."
    return (int(number)/step)*step

class Config(object):
    "Holds config from both url parts and config file for content."
    #pylint: disable=too-many-instance-attributes

    def __init__(self, vod_cfg_dir, base_url=None):

        self.availability_start_time_in_s = DEFAULT_AVAILABILITY_STARTTIME_IN_S
        self.availability_time_offset_in_s = DEFAULT_AVAILABILITY_TIME_OFFSET_IN_S
        self.availability_end_time = None
        self.media_presentation_duration = None
        self.timeshift_buffer_depth_in_s = None
        self.minimum_update_period_in_s = None
        self.modulo_period = None
        self.last_segment_numbers = [] # The last segment number in every period.
        self.init_seg_avail_offset = 0 # The number of secs before AST that one can fetch the init segments
        self.tfdt32_flag = False # Restart every 3 hours make tfdt fit into 32 bits.
        self.cont = False # Continuous update of MPD AST and seg_nr.
        self.periods_per_hour = -1 # If > 0, generates that many periods per hour. If 0, only one offset period.
        self.xlink_periods_per_hour = -1 # Number of periods per hour that are accessed via xlink.
        self.etp_periods_per_hour = -1 # Number of periods per hour that are accessed via xlink.
        self.etp_duration = -1 # Duration of the early-terminated period.
        self.insert_ad = -1 # Number of periods per hour that are accessed via xlink.
        self.mpd_callback = -1 # Number of periods per hour that have mpd callback events.
        self.cont_multiperiod = False # This flag should only be used when periods_per_hour is set
        self.seg_timeline = False # This flag is only true when there is /segtimeline_1/ in the URL
        self.multi_url = [] # If not empty, give multiple URLs in the BaseURL element
        self.period_offset = -1 # Make one period with an offset compared to ast
        self.scte35_per_minute = 0 # Number of 10s ads per minute. Maximum 3
        self.utc_timing_methods = []
        self.start_nr = 0
        self.content_name = None
        self.base_url = base_url
        self.rel_path = None
        self.filename = None
        self.reps = None # An array of representations with id, content_type, timescale (only > 1 if muxed)
        self.media_data = None  # A dictionary with timescales and paths to segment durations
        self.ext = None # File extension
        self.seg_duration = None
        self.vod_first_segment_in_loop = None
        self.vod_nr_segments_in_loop = 0
        self.vod_default_tsbd_secs = 0
        self.publish_time = None
        self.vod_cfg_dir = vod_cfg_dir
        self.vod_wrap_seconds = None

    def __str__(self):
        lines = ["%s=%s" % (k, v) for (k, v) in self.__dict__.items() if not k.startswith("_")]
        lines.sort()
        return "<Config>:\n" + "\n".join(lines)

    def update_with_filedata(self, url_parts, url_pos):
        "Find the content_name, file_name, and representations (if muxed as signalled by MUX_DIVIDER)."
        self.content_name = url_parts[url_pos]
        self.base_url += "/".join(url_parts[:url_pos+1]) + "/"
        rel_path_parts = url_parts[url_pos+1:-1]
        self.rel_path = "/".join(rel_path_parts)
        self.filename = url_parts[-1]
        self.ext = splitext(self.filename)[1]

    def update_with_reps(self, vod_cfg, url_parts, url_pos):
        "Update config with representations and their data."
        self.reps = []
        if len(url_parts) > url_pos +2: # More than just a manifest
            reps = url_parts[-2].split(MUX_DIVIDER)
            for rep in reps:
                content_type = vod_cfg.content_type_for_rep(rep)
                timescale = vod_cfg.media_data[content_type]['timescale']
                rep_data = {'id' : rep, 'content_type' : content_type, 'timescale' :timescale}
                self.reps.append(rep_data)


    def update_with_vodcfg(self, vod_cfg):
        "Update config with data from VoD content."
        if self.timeshift_buffer_depth_in_s is None:
            self.timeshift_buffer_depth_in_s = vod_cfg.default_tsbd_secs
        self.vod_first_segment_in_loop = vod_cfg.first_segment_in_loop
        self.vod_nr_segments_in_loop = vod_cfg.nr_segments_in_loop
        self.media_data = vod_cfg.media_data
        self.seg_duration = vod_cfg.segment_duration_s
        self.vod_wrap_seconds = vod_cfg.segment_duration_s * vod_cfg.nr_segments_in_loop

    def update_for_tfdt32(self, now_int):
        "Set MPD values for 32-bit tfdt (reset session every 3 hours)."
        self.availability_start_time_in_s = quantize(now_int, 10800)
        self.availability_end_time = self.availability_start_time_in_s + 10800
        self.media_presentation_duration = 10800
        self.minimum_update_period_in_s = 10800/2

    def update_for_cont_update(self, now_int):
        "Set values for case of continuous MPD updates (3hours session)."
        seg_dur = self.seg_duration
        self.availability_start_time_in_s = quantize(now_int - seg_dur, seg_dur)
        self.availability_end_time = self.availability_start_time_in_s + 10800
        self.media_presentation_duration = 10800
        self.minimum_update_period_in_s = 10800

    def update_with_modulo_period(self, modulo_period, seg_dur):
        "Update cfg data according to a modulo period."
        self.minimum_update_period_in_s = modulo_period.minimum_update_period
        self.availability_start_time_in_s = modulo_period.availability_start_time
        self.media_presentation_duration = modulo_period.media_presentation_duration
        self.availability_end_time = modulo_period.availability_end_time
        self.last_segment_numbers.append(modulo_period.calc_last_segment_number(seg_dur))

    def update_with_aet(self, now_int, availability_end_times, media_presentation_durations):
        "Find the proper availabilityEndTime and mediaPresentation duration for now and set in cfg."
        end_time = None
        media_presentation_duration = None
        if len(availability_end_times) > 0:
            end_time = availability_end_times[-1]
            for aet, media_pre_dur in zip(availability_end_times[::-1], media_presentation_durations[::-1]):
                if now_int > aet - 2*self.minimum_update_period_in_s:
                    break
                end_time = aet
                media_presentation_duration = media_pre_dur
        if end_time is not None:
            self.availability_end_time = end_time
            self.media_presentation_duration = media_presentation_duration

    def process_start_time(self, start_time, durations, now_int):
        "Process start_time and durations and set appropriate values."
        self.availability_start_time_in_s = quantize(start_time, self.seg_duration)
        if self.minimum_update_period_in_s is None:
            self.minimum_update_period_in_s = DEFAULT_SHORT_MINIMUM_UPDATE_PERIOD_IN_S
        if len(durations) > 0:
            total_dur = 0
            availability_end_times = []
            media_presentation_durations = []
            for dur in durations:
                total_dur += dur
                end_time = quantize(start_time + total_dur, self.seg_duration)
                availability_end_times.append(end_time)
                media_presentation_durations.append(total_dur)
            last_segment_number = (end_time-self.availability_start_time_in_s)//self.seg_duration - 1
            self.last_segment_numbers.append(last_segment_number)
            self.update_with_aet(now_int, availability_end_times, media_presentation_durations)

    def update_publish_time(self, now_int):
        """The publishTime to be written in the MPD. Changed according to the rules:
            if availabilityStartTimeInS == DEFAULT_AVAILABILITY_STARTTIME_IN_S."""
        if self.availability_start_time_in_s != DEFAULT_AVAILABILITY_STARTTIME_IN_S:
            publish_time = quantize(now_int, self.minimum_update_period_in_s)
        else:
            publish_time = DEFAULT_AVAILABILITY_STARTTIME_IN_S
        self.publish_time = publish_time


class VodConfig(object):
    "Configuration of the actual content."

    def __init__(self):
        self.good_versions = ("1.0", "1.1")
        self.first_segment_in_loop = None
        self.nr_segments_in_loop = 0
        self.segment_duration_s = 0
        self.default_tsbd_secs = DEFAULT_TIMESHIFT_BUFFER_DEPTH_IN_SECS
        self.possible_media = ('video', 'audio', 'subtitles', 'image')
        self.media_data = {}

    def read_config(self, config_file):
        "Read VoD config data."
        config = ConfigParser.RawConfigParser()
        with open(config_file, 'rb') as cfg_file:
            config.readfp(cfg_file)
            version = config.get('General', 'version')
            if version not in self.good_versions:
                raise ConfigProcessorError("Bad config file version: %s (should be in %s)" % (version,
                                                                                              self.good_versions))
            self.first_segment_in_loop = config.getint("Setup", "first_segment_in_loop")
            self.segment_duration_s = config.getint("Setup", "segment_duration_s")
            self.nr_segments_in_loop = config.getint("Setup", "nr_segments_in_loop")
            self.default_tsbd_secs = config.getint("Setup", "default_tsbd_secs")
            for media in self.possible_media:
                try:
                    reps = config.get(media, "representations")
                    timescale = config.getint(media, "timescale")
                    representations = [rep.strip() for rep in reps.split(",")]
                    self.media_data[media] = {'timescale' : timescale, 'representations' : representations}
                    if version == "1.1":
                        self.media_data[media]['total_duration'] = config.getint(media, "total_duration")
                        self.media_data[media]['dat_file'] = config.get(media, 'dat_file')
                except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                    pass

    #pylint: disable=dangerous-default-value
    def write_config(self, config_file, data={}):
        "Write a config file for the analyzed content, that can then be used to serve it efficiently."
        # Note that one needs to write in reverse order
        config = ConfigParser.RawConfigParser()
        config.add_section('General')
        config.set('General', 'version', '1.1')
        config.add_section('Setup')
        config.set('Setup', 'default_tsbd_secs', data.get('default_tsbd_secs', self.default_tsbd_secs))
        config.set('Setup', 'segment_duration_s', data.get('segment_duration_s', self.segment_duration_s))
        config.set('Setup', 'nr_segments_in_loop', data.get('nr_segments_in_loop', self.nr_segments_in_loop))
        config.set('Setup', 'first_segment_in_loop', data.get('first_segment_in_loop', self.first_segment_in_loop))
        for content_type in ('video', 'audio', 'subtitles'):
            media_data = data.get('media_data', self.media_data)
            if media_data.has_key(content_type):
                config.add_section(content_type)
                mdata = media_data[content_type]
                config.set(content_type, 'representations', ','.join(mdata['representations']))
                config.set(content_type, 'timescale', mdata['timescale'])
                config.set(content_type, 'total_duration', mdata['totalDuration'])
                config.set(content_type, 'dat_file', mdata['datFile'])
        with open(config_file, 'wb') as cfg_file:
            config.write(cfg_file)

    def content_type_for_rep(self, representation):
        "Find the ContentType for a representation."
        for content_type in self.media_data.keys():
            mdata = self.media_data[content_type]
            if representation in mdata['representations']:
                return content_type
        return None


class ConfigProcessor(object):
    "Process the url and VoD config files and setup configuration."

    url_cfg_keys = ("start", "ast", "dur", "init", "tsbd", "mup", "modulo", "tfdt", "cont",
                    "periods", "xlink", "etp", "etpDuration", "insertad", "mpdcallback", "continuous", "segtimeline", "baseurl",
                    "peroff", "scte35", "utc", "snr", "ato")

    def __init__(self, vod_cfg_dir, base_url):
        self.vod_cfg_dir = vod_cfg_dir
        self.cfg = Config(vod_cfg_dir, base_url)

    def getconfig(self):
        "Get the config object."
        return self.cfg

    def get_mpd_data(self):
        "Get data needed for generating the dynamic MPD."
        mpd = {'segDuration' : self.cfg.seg_duration,
               'availability_start_time_in_s' : self.cfg.availability_start_time_in_s,
               'availability_time_offset_in_s' :self.cfg.availability_time_offset_in_s,
               'BaseURL' : self.cfg.base_url,
               'startNumber' : self.cfg.availability_start_time_in_s//self.cfg.seg_duration,
               'periodsPerHour' : self.cfg.periods_per_hour,
               'xlinkPeriodsPerHour' : self.cfg.xlink_periods_per_hour,
               'etpPeriodsPerHour' : self.cfg.etp_periods_per_hour,
               'etpDuration' : self.cfg.etp_duration,
               'insertAd' : self.cfg.insert_ad,
               'mpdCallback':self.cfg.mpd_callback,
               'continuous' : self.cfg.cont_multiperiod,
               'segtimeline' : self.cfg.seg_timeline,
               'urls' : self.cfg.multi_url,
               'periodOffset' : self.cfg.period_offset,
               'publishTime' : self.cfg.publish_time,
               'mediaData' : self.cfg.media_data}
        if self.cfg.availability_end_time:
            mpd['availabilityEndTime'] = self.cfg.availability_end_time
        return mpd

    def process_url(self, url_parts, now_int=0):
        """Extract config and calculate availabilityStartTimeInS and availabilityEndTime from URL."""
        #pylint: disable=too-many-branches, too-many-statements
        start_time = None
        durations = []
        cont_update_flag = False
        modulo_period = None
        cfg = self.cfg

        url_pos = 0
        for part in url_parts: # Should be listed in self.configParts to make sure it works.
            cfg_parts = part.split("_", 1)
            if cfg_parts[0] not in self.url_cfg_keys: #Must handle content like testpic_2s
                break
            key, value = cfg_parts
            if key == "start" or key == "ast": # Change availability start time in s.
                start_time = int(value)
            elif key == "dur": # Add a presentation duration for multiple periods
                durations.append(int(value))
            elif key == "init": # Make the init segment available earlier
                cfg.init_seg_avail_offset = int(value)
            elif key == "tsbd":
                cfg.timeshift_buffer_depth_in_s = int(value)
            elif key == "mup": # Set the minimum update period (in s)
                cfg.minimum_update_period_in_s = int(value)
            elif key == "modulo": # Make a number of time-limited sessions every hour
                modulo_period = ModuloPeriod(int(value), now_int)
            elif key == "tfdt": # Use 32-bit tfdt (which means that AST must be more recent as well)
                cfg.tfdt32_flag = True
            elif key == "cont": # Continuous update of MPD AST and seg_nr.
                cont_update_flag = True
            elif key == "periods": # Make multiple periods
                cfg.periods_per_hour = int(value)
            elif key == "xlink": # Make periods access via xlink.
                cfg.xlink_periods_per_hour = int(value)
            elif key == "etp": # Make periods access via xlink.
                cfg.etp_periods_per_hour = int(value)
            elif key == "etpDuration": # Add a presentation duration for multiple periods
                cfg.etp_duration = int(value)
            elif key == "insertad": # Make periods access via xlink.
                cfg.insert_ad = int(value)
            elif key == "mpdcallback": # Make periods access via xlink.
                cfg.mpd_callback = int(value)
            elif key == "continuous": # Only valid when it's set to 1 and periods_per_hour is set
                if int(value) == 1:
                    cfg.cont_multiperiod = True
            elif key == "segtimeline": # Only valid when it's set to 1
                if int(value) == 1:
                    cfg.seg_timeline = True
            elif key == "baseurl": # Use multiple URLs, put all the configuration strings in multi_url
                cfg.multi_url.append(value)
            elif key == "peroff": # Set the period offset
                cfg.period_offset = int(value)
            elif key == "scte35": # Add SCTE-35 ad messages every minute
                cfg.scte35_per_minute = int(value)
            elif key == "utc": # Get hyphen-separated list of utc-timing methods and make into list
                cfg.utc_timing_methods = value.split("-")
            elif key == "snr": # Segment startNumber
                cfg.start_nr = self.interpret_start_nr(value)
            elif key == "ato": #availabilityTimeOffset
                if value == "inf":
                    cfg.availability_time_offset_in_s = -1 #signal that the value is infinite
                else:
                    try:
                        float(value)  #ignore the setting when the value is negative
                        cfg.availability_time_offset_in_s = max(float(value), 0)
                    except ValueError: #wrong setting
                        cfg.availability_time_offset_in_s = 0
            else:
                raise ConfigProcessorError("Cannot interpret option %s properly" % key)
            url_pos += 1

        cfg.update_with_filedata(url_parts, url_pos)
        vod_cfg_file = join(self.vod_cfg_dir, cfg.content_name) + ".cfg"
        vod_cfg = VodConfig()
        vod_cfg.read_config(vod_cfg_file)
        cfg.update_with_reps(vod_cfg, url_parts, url_pos)
        cfg.update_with_vodcfg(vod_cfg)

        if start_time is not None:
            if modulo_period is not None:
                raise ConfigProcessorError("Cannot have both start_time and modulo_period set!")
            cfg.process_start_time(start_time, durations, now_int)
        if cfg.tfdt32_flag:
            if cont_update_flag:
                raise ConfigProcessorError("Cannot have continuous update with tfdt_32 (similar behavior)")
            cfg.update_for_tfdt32(now_int)
        if cont_update_flag:
            cfg.update_for_cont_update(now_int)
        if modulo_period is not None:
            cfg.update_with_modulo_period(modulo_period, cfg.seg_duration)
        cfg.update_publish_time(now_int)

    #pylint: disable=no-self-use
    def interpret_start_nr(self, value):
        "startNr should be 0 or greater. -1 means that it is put to 1, but absent in MPD (default value)"
        error_msg = "startNr must be an integer >= 0. -1 means default value (=1)."
        try:
            start_nr = int(value)
        except ValueError:
            raise ConfigProcessorError(error_msg)
        if start_nr < -1:
            raise ConfigProcessorError(error_msg)
        return start_nr
