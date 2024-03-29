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

import re
import copy
from xml.etree import ElementTree
from io import StringIO
import time

from dashlivesim.dashlib.timeformatconversions import make_timestamp
from dashlivesim.dashlib.segtimeline import SegmentTimeLineGenerator
from dashlivesim.dashlib.dash_namespace import add_ns
from dashlivesim.dashlib import scte35

SET_BASEURL = True

UTC_TIMING_NTP_SERVER = '1.de.pool.ntp.org'
UTC_TIMING_SNTP_SERVER = 'time.kfki.hu'
UTC_TIMING_HTTP_SERVER = 'http://time.akamai.com/?iso'


def set_value_from_dict(element, key, data):
    "Set attribute key of element to value data[key], if present."
    if key in data:
        element.set(key, str(data[key]))


def set_values_from_dict(element, keys, data):
    "Set attribute key of element to value data[key] for all keys (if present)."
    for key in keys:
        if key in data:
            element.set(key, str(data[key]))


class MpdModifierError(Exception):
    "Generic MpdModifier error."
    pass


class MpdProcessor(object):
    "Process a VoD MPD. Analyze and convert it to a live (dynamic) session."
    # pylint: disable=no-self-use, too-many-locals, too-many-instance-attributes

    def __init__(self, infile, mpd_proc_cfg, cfg=None, full_url=None):
        self.tree = ElementTree.parse(infile)
        self.scte35_present = mpd_proc_cfg['scte35Present']
        self.utc_timing_methods = mpd_proc_cfg['utc_timing_methods']
        self.utc_head_url = mpd_proc_cfg['utc_head_url']
        self.continuous = mpd_proc_cfg['continuous']
        self.segtimeline = mpd_proc_cfg['segtimeline']
        self.segtimeline_nr = mpd_proc_cfg['segtimeline_nr']
        self.mpd_proc_cfg = mpd_proc_cfg
        self.cfg = cfg
        self.full_url = full_url
        self.root = self.tree.getroot()
        self.availability_start_time_in_s = None
        self.emsg_last_seg = cfg.emsg_last_seg if cfg is not None else False
        self.segtimelineloss = cfg.segtimelineloss if cfg is not None else False

    def process(self, mpd_data, period_data, ll_data={}):
        "Top-level call to process the XML."
        mpd = self.root
        self.availability_start_time_in_s = mpd_data[
            'availability_start_time_in_s']
        self.process_mpd(mpd, mpd_data)
        self.process_mpd_children(mpd, mpd_data, period_data, ll_data)

    def process_mpd(self, mpd, mpd_data):
        """Process the root element (MPD)"""
        assert mpd.tag == add_ns('MPD')
        mpd.set('type', mpd_data.get('type', 'dynamic'))
        if self.scte35_present:
            old_profiles = mpd.get('profiles')
            if not old_profiles.find(scte35.PROFILE) >= 0:
                new_profiles = old_profiles + "," + scte35.PROFILE
                mpd.set('profiles', new_profiles)
        if self.segtimelineloss:
            old_profiles = mpd.get('profiles')
            if old_profiles.find("dash-if-simple") >= 0:
                new_profiles = old_profiles.replace("dash-if-simple", "dash-if-main")
                mpd.set('profiles', new_profiles)
        if 'add_profiles' in mpd_data:
            profiles = mpd.get('profiles').split(",")
            for prof in mpd_data['add_profiles']:
                if prof not in profiles:
                    profiles.append(prof)
            mpd.set('profiles', ",".join(profiles))

        key_list = ['availabilityStartTime', 'availabilityEndTime', 'timeShiftBufferDepth',
                    'minimumUpdatePeriod', 'maxSegmentDuration',
                    'mediaPresentationDuration', 'suggestedPresentationDelay']
        if mpd_data.get('type', 'dynamic') == 'static':
            key_list.remove('minimumUpdatePeriod')
        if (mpd_data.get('type', 'dynamic') == 'static' or mpd_data.get('mediaPresentationDuration')):
            key_list.remove('timeShiftBufferDepth')
        set_values_from_dict(mpd, key_list, mpd_data)
        if 'mediaPresentationDuration' in mpd.attrib and 'mediaPresentationDuration' not in mpd_data:
            del mpd.attrib['mediaPresentationDuration']
        mpd.set('publishTime', make_timestamp(self.mpd_proc_cfg['now']))  # TODO Correlate time with change in MPD
        mpd.set('id', 'Config part of url maybe?')
        if self.segtimeline or self.segtimeline_nr:
            if 'maxSegmentDuration' in mpd.attrib:
                del mpd.attrib['maxSegmentDuration']
            if mpd_data.get('type', 'dynamic') != 'static':
                mpd.set('minimumUpdatePeriod', "PT0S")

    # pylint: disable = too-many-branches

    def process_mpd_children(self, mpd, data, period_data, ll_data):
        """Process the children of the MPD element.
        They should be in order ProgramInformation, BaseURL, Location, ServiceDescription,
        Period, UTCTiming, Metrics."""
        ato = 0
        atc = 'true'
        if 'availabilityTimeOffset' in data:
            ato = data['availabilityTimeOffset']
        if 'availabilityTimeComplete' in data:
            atc = data['availabilityTimeComplete']
        children = list(mpd)
        pos = 0
        for child in children:
            if child.tag != add_ns('ProgramInformation'):
                break
            pos += 1
        next_child = list(mpd)[pos]
        set_baseurl = SET_BASEURL
        if self.cfg and self.cfg.add_location:
            set_baseurl = False  # Cannot have both BASEURL and Location
        if next_child.tag == add_ns('BaseURL'):
            if 'BaseURL' not in data or not set_baseurl:
                self.root.remove(next_child)
            else:
                self.modify_baseurl(next_child, data['BaseURL'])
                pos += 1
        elif ('BaseURL' in data) and set_baseurl:
            if 'urls' in data and data['urls']:  # check if we have to set multiple URLs
                url_header, url_body = data['BaseURL'].split('//')
                url_parts = url_body.split('/')
                i = -1
                for part in url_parts:
                    i += 1
                    if part.find("_") < 0:  # Not a configuration
                        continue
                    cfg_parts = part.split("_", 1)
                    key, _ = cfg_parts
                    if key == "baseurl":
                        url_parts[i] = ""  # Remove all the baseurl elements
                url_parts = [p for p in url_parts if p is not None]
                for url in data['urls']:
                    url_parts.insert(-1, "baseurl_" + url)
                    self.insert_baseurl(mpd, pos, url_header + "//" + "/".join(url_parts) + "/", ato, atc)
                    del url_parts[-2]
                    pos += 1
            else:
                self.insert_baseurl(mpd, pos, data['BaseURL'], ato, atc)
                pos += 1
        if self.cfg and self.cfg.add_location and self.full_url is not None:
            loc_url = re.sub(r"/startrel_[-\d]+", "/start_%d" %
                             self.cfg.start_time, self.full_url)
            loc_url = re.sub(r"/stoprel_[-\d]+", "/stop_%d" %
                             self.cfg.stop_time, loc_url)
            self.insert_location(mpd, pos, loc_url)
            pos += 1

        if ll_data:
            self.insert_service_description(mpd, pos)
            pos += 1

        children = list(mpd)
        for ch_nr in range(pos, len(children)):
            if children[ch_nr].tag == add_ns("Period"):
                period = list(mpd)[pos]
                pos = ch_nr
                break
        else:
            raise MpdModifierError("No period found.")
        for i in range(1, len(period_data)):
            new_period = copy.deepcopy(period)
            mpd.insert(pos+i, new_period)
        self.insert_utc_timings(mpd, pos+len(period_data))
        self.update_periods(mpd, period_data, data['periodOffset'] >= 0, ll_data)

    def insert_baseurl(self, mpd, pos, new_baseurl, new_ato, new_atc):
        "Create and insert a new <BaseURL> element."
        baseurl_elem = ElementTree.Element(add_ns('BaseURL'))
        baseurl_elem.text = new_baseurl
        baseurl_elem.tail = "\n"
        if float(new_ato) == -1:
            self.insert_ato(baseurl_elem, 'INF')
        elif float(new_ato) > 0:  # don't add this attribute when the value is 0
            self.insert_ato(baseurl_elem, new_ato)
        if new_atc in ('False', 'false', '0'):
            baseurl_elem.set('availabilityTimeComplete', new_atc)
        mpd.insert(pos, baseurl_elem)

    def modify_baseurl(self, baseurl_elem, new_baseurl):
        "Modify the text of an existing BaseURL"
        baseurl_elem.text = new_baseurl

    def insert_ato(self, baseurl_elem, new_ato):
        "Add availabilityTimeOffset to BaseURL element"
        baseurl_elem.set('availabilityTimeOffset', new_ato)

    def insert_location(self, mpd, pos, location_url):
        location_elem = ElementTree.Element(add_ns('Location'))
        location_elem.text = location_url
        location_elem.tail = "\n"
        mpd.insert(pos, location_elem)

    def insert_service_description(self, mpd, pos):
        sd_elem = ElementTree.Element(add_ns('ServiceDescription'))
        sd_elem.set("id", "0")
        sd_elem.text = "\n"
        lat_elem = ElementTree.Element(add_ns('Latency'))
        lat_elem.set("min", "2000")
        lat_elem.set("max", "6000")
        lat_elem.set("target", "4000")
        lat_elem.set("referenceId", "0")
        lat_elem.tail = "\n"
        sd_elem.insert(0, lat_elem)
        pr_elem = ElementTree.Element(add_ns('PlaybackRate'))
        pr_elem.set("min", "0.96")
        pr_elem.set("max", "1.04")
        pr_elem.tail = "\n"
        sd_elem.insert(1, pr_elem)
        sd_elem.tail = "\n"
        mpd.insert(pos, sd_elem)

    def insert_producer_reference(self, ad_set, pos):
        prt_elem = ElementTree.Element(add_ns('ProducerReferenceTime'))
        prt_elem.set("id", "0")
        prt_elem.set("type", "encoder")
        prt_elem.set("wallClockTime", "1970-01-01T00:00:00")
        prt_elem.set("presentationTime", "0")
        utc_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:http-iso:2014',
                                               UTC_TIMING_HTTP_SERVER)
        prt_elem.insert(0, utc_elem)
        prt_elem.text = "\n"
        prt_elem.tail = "\n"
        ad_set.insert(pos, prt_elem)

    def update_periods(self, mpd, period_data, offset_at_period_level, ll_data):
        "Update periods to provide appropriate values."
        # pylint: disable = too-many-statements

        def set_attribs(elem, keys, data):
            "Set element attributes from data."
            for key in keys:
                if key in data:
                    if key == "presentationTimeOffset" and str(data[key]) == "0":  # Remove default value
                        if key in elem:
                            del elem[key]
                        continue
                    elem.set(key, str(data[key]))

        def remove_attribs(elem, keys):
            "Remove attributes from elem."
            for key in keys:
                if key in elem.attrib:
                    del elem.attrib[key]

        def insert_segmentbase(period, presentation_time_offset):
            "Insert SegmentBase element."
            segmentbase_elem = ElementTree.Element(add_ns('SegmentBase'))
            if presentation_time_offset != 0:
                segmentbase_elem.set('presentationTimeOffset', str(presentation_time_offset))
            period.insert(0, segmentbase_elem)

        def create_inband_scte35stream_elem():
            "Create an InbandEventStream element for SCTE-35."
            return self.create_descriptor_elem("InbandEventStream", scte35.SCHEME_ID_URI, value=str(scte35.PID))

        def create_inband_stream_elem():
            """Create an InbandEventStream element for signalling emsg in Rep when encoder fails to generate new segments

            IOP 4.11.4.3 scenario."""
            return self.create_descriptor_elem("InbandEventStream", "urn:mpeg:dash:event:2012", value=str(1))

        def create_inline_mpdcallback_elem(BaseURLSegmented):
            "Create an EventStream element for MPD Callback."
            return self.create_descriptor_elem("EventStream", "urn:mpeg:dash:event:callback:2015", value=str(1),
                                               elem_id=None, messageData=BaseURLSegmented)
        if self.segtimeline or self.segtimeline_nr:
            segtimeline_generators = {}
            for content_type in ('video', 'audio'):
                segtimeline_generators[content_type] = SegmentTimeLineGenerator(self.cfg.media_data[content_type],
                                                                                self.cfg)
        periods = mpd.findall(add_ns('Period'))
        BaseURL = mpd.findall(add_ns('BaseURL'))
        if len(BaseURL) > 0:
            BaseURLParts = BaseURL[0].text.split('/')
            if len(BaseURLParts) > 3:
                BaseURLSegmented = BaseURLParts[0] + '//' + BaseURLParts[2] + '/' + BaseURLParts[3] + '/mpdcallback/'
        # From the Base URL
        last_period_id = '-1'
        for (period, pdata) in zip(periods, period_data):
            set_attribs(period, ('id', 'start'), pdata)
            if 'etpDuration' in pdata:
                period.set('duration', "PT%dS" % pdata['etpDuration'])
            if 'periodDuration' in pdata:
                period.set('duration', pdata['periodDuration'])
            segmenttemplate_attribs = ['startNumber']
            pto = pdata['presentationTimeOffset']
            if pto:
                if offset_at_period_level:
                    insert_segmentbase(period, pto)
                else:
                    segmenttemplate_attribs.append('presentationTimeOffset')
            if 'mpdCallback' in pdata:
                # Add the mpdCallback element only if the flag is raised.
                mpdcallback_elem = create_inline_mpdcallback_elem(BaseURLSegmented)
                period.insert(0, mpdcallback_elem)
            adaptation_sets = period.findall(add_ns('AdaptationSet'))
            for ad_set in adaptation_sets:
                ad_pos = 0
                content_type = ad_set.get('contentType')
                if self.emsg_last_seg:
                    inband_event_elem = create_inband_stream_elem()
                    ad_set.insert(0, inband_event_elem)
                if content_type == 'video' and self.scte35_present:
                    scte35_elem = create_inband_scte35stream_elem()
                    ad_set.insert(0, scte35_elem)
                    ad_pos += 1
                if self.continuous and last_period_id != '-1':
                    supplementalprop_elem = self.create_descriptor_elem("SupplementalProperty",
                                                                        "urn:mpeg:dash:period_continuity:2014",
                                                                        last_period_id)
                    ad_set.insert(ad_pos, supplementalprop_elem)
                if ll_data:
                    self.insert_producer_reference(ad_set, ad_pos)
                seg_templates = ad_set.findall(add_ns('SegmentTemplate'))
                for seg_template in seg_templates:
                    set_attribs(seg_template, segmenttemplate_attribs, pdata)
                    if ll_data:
                        set_attribs(seg_template,
                                    ('availabilityTimeOffset', 'availabilityTimeComplete'),
                                    ll_data)
                    if pdata.get('startNumber') == '-1':  # Default to 1
                        remove_attribs(seg_template, ['startNumber'])

                    if self.segtimeline or self.segtimeline_nr:
                        # add SegmentTimeline block in SegmentTemplate with timescale and window.
                        segtime_gen = segtimeline_generators[content_type]
                        now = self.mpd_proc_cfg['now']
                        tsbd = self.cfg.timeshift_buffer_depth_in_s
                        ast = self.cfg.availability_start_time_in_s
                        start_time = max(ast + pdata['start_s'], now - tsbd)
                        if 'period_duration_s' in pdata:
                            end_time = min(ast + pdata['start_s'] + pdata['period_duration_s'], now)
                        else:
                            end_time = now
                        start_time -= self.cfg.availability_start_time_in_s
                        end_time -= self.cfg.availability_start_time_in_s
                        use_closest = False
                        if self.cfg.stop_time and self.cfg.timeoffset == 0:
                            start_time = self.cfg.start_time
                            end_time = min(now, self.cfg.stop_time)
                            use_closest = True
                        seg_timeline = segtime_gen.create_segtimeline(
                            start_time, end_time, use_closest)
                        remove_attribs(seg_template, ['duration'])
                        seg_template.set('timescale', str(self.cfg.media_data[content_type]['timescale']))
                        if pto != "0" and not offset_at_period_level:
                            # rescale presentationTimeOffset based on the local timescale
                            seg_template.set('presentationTimeOffset',
                                             str(int(pto) * int(self.cfg.media_data[content_type]['timescale'])))
                        media_template = seg_template.attrib['media']
                        if self.segtimeline:
                            media_template = media_template.replace('$Number$', 't$Time$')
                            remove_attribs(seg_template, ['startNumber'])
                        elif self.segtimeline_nr:
                            # Set number to the first number listed
                            set_attribs(seg_template,
                                        ('startNumber',),
                                        {'startNumber': segtime_gen.start_number})
                        seg_template.set('media', media_template)
                        seg_template.text = "\n"
                        seg_template.insert(0, seg_timeline)
            last_period_id = pdata.get('id')

    def create_descriptor_elem(self, name, scheme_id_uri, value=None, elem_id=None, messageData=None):
        "Create an element of DescriptorType."
        elem = ElementTree.Element(add_ns(name))
        elem.set("schemeIdUri", scheme_id_uri)
        if value:
            elem.set("value", value)
        if elem_id:
            elem.set("id", elem_id)
        if name == "EventStream" and messageData:
            eventElem = ElementTree.Element(add_ns("Event"))
            eventElem.set("messageData", messageData)
            elem.append(eventElem)
        elem.tail = "\n"
        return elem

    def insert_utc_timings(self, mpd, start_pos):
        """Insert UTCTiming elements right after program information in order given by self.utc_timing_methods.

        The version of DASH should also be updated, but that is not done yet."""

        pos = start_pos
        for utc_method in self.utc_timing_methods:
            if utc_method == "direct":
                direct_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()))
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:direct:2014', direct_time)
            elif utc_method == "head":
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:http-head:2014',
                                                        self.utc_head_url)
            elif utc_method == "ntp":
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:ntp:2014',
                                                        UTC_TIMING_NTP_SERVER)
            elif utc_method == "sntp":
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:sntp:2014',
                                                        UTC_TIMING_SNTP_SERVER)
            elif utc_method == "httpxsdate":
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:http-xsdate:2014',
                                                        UTC_TIMING_HTTP_SERVER)
            elif utc_method == "httpiso":
                time_elem = self.create_descriptor_elem('UTCTiming', 'urn:mpeg:dash:utc:http-iso:2014',
                                                        UTC_TIMING_HTTP_SERVER)
            else:  # Unknown or un-implemented UTCTiming method
                raise MpdModifierError("Unknown UTCTiming method: %s" % utc_method)
            mpd.insert(pos, time_elem)
            pos += 1
        return pos

    def get_full_xml(self, clean=True):
        "Get a string of all XML cleaned (no ns0 namespace)"
        ofh = StringIO()
        self.tree.write(ofh, encoding="unicode")
        value = ofh.getvalue()
        if clean:
            value = value.replace("ns0:", "").replace("xmlns:ns0=", "xmlns=")
        xml_intro = '<?xml version="1.0" encoding="utf-8"?>\n'
        return xml_intro + value
