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

from timeformatconversions import make_timestamp
import scte35
from segtimeline import SegmentTimeLineGenerator
from dash_namespace import add_ns

SET_BASEURL = True

UTC_TIMING_NTP_SERVER = '1.de.pool.ntp.org'
UTC_TIMING_SNTP_SERVER = 'time.kfki.hu'



def set_value_from_dict(element, key, data):
    "Set attribute key of element to value data[key], if present."
    if data.has_key(key):
        element.set(key, str(data[key]))

def set_values_from_dict(element, keys, data):
    "Set attribute key of element to value data[key] for all keys (if present)."
    for key in keys:
        if data.has_key(key):
            element.set(key, str(data[key]))


class MpdModifierError(Exception):
    "Generic MpdModifier error."
    pass


class MpdProcessor(object):
    "Process a VoD MPD. Analyze and convert it to a live (dynamic) session."
    #pylint: disable=no-self-use, too-many-locals, too-many-instance-attributes

    def __init__(self, infile, mpd_proc_cfg, cfg=None):
        self.tree = ElementTree.parse(infile)
        self.scte35_present = mpd_proc_cfg['scte35Present']
        self.utc_timing_methods = mpd_proc_cfg['utc_timing_methods']
        self.utc_head_url = mpd_proc_cfg['utc_head_url']
        self.continuous = mpd_proc_cfg['continuous']
        self.segtimeline = mpd_proc_cfg['segtimeline']
        self.mpd_proc_cfg = mpd_proc_cfg
        self.cfg = cfg
        self.root = self.tree.getroot()
        self.availability_start_time_in_s = None

    def process(self, data, period_data):
        "Top-level call to process the XML."
        mpd = self.root
        self.availability_start_time_in_s = data['availability_start_time_in_s']
        self.process_mpd(mpd, data)
        self.process_mpd_children(mpd, data, period_data)

    def process_mpd(self, mpd, data):
        """Process the root element (MPD)"""
        assert mpd.tag == add_ns('MPD')
        mpd.set('type', "dynamic")
        if self.scte35_present:
            old_profiles = mpd.get('profiles')
            if not old_profiles.find(scte35.PROFILE) >= 0:
                new_profiles = old_profiles + "," + scte35.PROFILE
                mpd.set('profiles', new_profiles)
        key_list = ['availabilityStartTime', 'availabilityEndTime', 'timeShiftBufferDepth',
                    'minimumUpdatePeriod', 'maxSegmentDuration', 'mediaPresentationDuration']
        set_values_from_dict(mpd, key_list, data)
        if mpd.attrib.has_key('mediaPresentationDuration') and not data.has_key('mediaPresentationDuration'):
            del mpd.attrib['mediaPresentationDuration']
        mpd.set('publishTime', make_timestamp(self.mpd_proc_cfg['now'])) #TODO Correlate time with change in MPD
        mpd.set('id', 'Config part of url maybe?')
        if self.segtimeline:
            if mpd.attrib.has_key('maxSegmentDuration'):
                del mpd.attrib['maxSegmentDuration']
            mpd.set('minimumUpdatePeriod', "PT0S")


    #pylint: disable = too-many-branches
    def process_mpd_children(self, mpd, data, period_data):
        """Process the children of the MPD element.
        They should be in order ProgramInformation, BaseURL, Location, Period, UTCTiming, Metrics."""
        ato = 0
        atc = 'true'
        if data.has_key('availabilityTimeOffset'):
            ato = data['availabilityTimeOffset']
        if data.has_key('availabilityTimeComplete'):
            atc = data['availabilityTimeComplete']
        children = mpd.getchildren()
        pos = 0
        for child in children:
            if child.tag != add_ns('ProgramInformation'):
                break
            pos += 1
        next_child = mpd.getchildren()[pos]
        if next_child.tag == add_ns('BaseURL'):
            if not data.has_key('BaseURL') or not SET_BASEURL:
                self.root.remove(next_child)
            else:
                self.modify_baseurl(next_child, data['BaseURL'])
                pos += 1
        elif data.has_key('BaseURL') and SET_BASEURL:
            if data.has_key('urls') and data['urls']: # check if we have to set multiple URLs
                url_header, url_body = data['BaseURL'].split('//')
                url_parts = url_body.split('/')
                i = -1
                for part in url_parts:
                    i += 1
                    if part.find("_") < 0: #Not a configuration
                        continue
                    cfg_parts = part.split("_", 1)
                    key, _ = cfg_parts
                    if key == "baseurl":
                        url_parts[i] = "" #Remove all the baseurl elements
                url_parts = filter(None, url_parts)
                for url in data['urls']:
                    url_parts.insert(-1, "baseurl_" + url)
                    self.insert_baseurl(mpd, pos, url_header + "//" + "/".join(url_parts) + "/", ato, atc)
                    del url_parts[-2]
                    pos += 1
            else:
                self.insert_baseurl(mpd, pos, data['BaseURL'], ato, atc)
                pos += 1
        children = mpd.getchildren()
        for ch_nr in range(pos, len(children)):
            if children[ch_nr].tag == add_ns("Period"):
                period = mpd.getchildren()[pos]
                pos = ch_nr
                break
        else:
            raise MpdModifierError("No period found.")
        for i in range(1, len(period_data)):
            new_period = copy.deepcopy(period)
            mpd.insert(pos+i, new_period)
        self.insert_utc_timings(mpd, pos+len(period_data))
        self.update_periods(mpd, period_data, data['periodOffset'] >= 0)

    def insert_baseurl(self, mpd, pos, new_baseurl, new_ato, new_atc):
        "Create and insert a new <BaseURL> element."
        baseurl_elem = ElementTree.Element(add_ns('BaseURL'))
        baseurl_elem.text = new_baseurl
        baseurl_elem.tail = "\n"
        if float(new_ato) == -1:
            self.insert_ato(baseurl_elem, 'INF')
        elif float(new_ato) > 0:  # don't add this attribute when the value is 0
            self.insert_ato(baseurl_elem, new_ato)
        if new_atc in ['False', 'false', '0']:
            baseurl_elem.set('availabilityTimeComplete', new_atc)
        mpd.insert(pos, baseurl_elem)

    def modify_baseurl(self, baseurl_elem, new_baseurl):
        "Modify the text of an existing BaseURL"
        baseurl_elem.text = new_baseurl

    def insert_ato(self, baseurl_elem, new_ato):
        "Add availabilityTimeOffset to BaseURL element"
        baseurl_elem.set('availabilityTimeOffset', new_ato)

    #pylint: disable = too-many-statements
    def update_periods(self, mpd, period_data, offset_at_period_level=False):
        "Update periods to provide appropriate values."

        def set_attribs(elem, keys, data):
            "Set element attributes from data."
            for key in keys:
                if data.has_key(key):
                    if key == "presentationTimeOffset" and str(data[key]) == "0": # Remove default value
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

        def create_inline_mpdcallback_elem(BaseURLSegmented):
            "Create an EventStream element for MPD Callback."
            return self.create_descriptor_elem("EventStream", "urn:mpeg:dash:event:callback:2015", value=str(1),
                                               elem_id=None, messageData=BaseURLSegmented)
        if self.segtimeline:
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
            if pdata.has_key('etpDuration'):
                period.set('duration', "PT%dS" % pdata['etpDuration'])
            if pdata.has_key('periodDuration'):
                period.set('duration', pdata['periodDuration'])
            segmenttemplate_attribs = ['startNumber']
            pto = pdata['presentationTimeOffset']
            if pto:
                if offset_at_period_level:
                    insert_segmentbase(period, pdata['presentationTimeOffset'])
                else:
                    segmenttemplate_attribs.append('presentationTimeOffset')
            if pdata.has_key('mpdCallback'):
                # Add the mpdCallback element only if the flag is raised.
                mpdcallback_elem = create_inline_mpdcallback_elem(BaseURLSegmented)
                period.insert(0, mpdcallback_elem)
            adaptation_sets = period.findall(add_ns('AdaptationSet'))
            for ad_set in adaptation_sets:
                ad_pos = 0
                content_type = ad_set.get('contentType')
                if content_type == 'video' and self.scte35_present:
                    scte35_elem = create_inband_scte35stream_elem()
                    ad_set.insert(0, scte35_elem)
                    ad_pos += 1
                if self.continuous and last_period_id != '-1':
                    supplementalprop_elem = self.create_descriptor_elem("SupplementalProperty", \
                    "urn:mpeg:dash:period_continuity:2014", last_period_id)
                    ad_set.insert(ad_pos, supplementalprop_elem)
                seg_templates = ad_set.findall(add_ns('SegmentTemplate'))
                for seg_template in seg_templates:
                    set_attribs(seg_template, segmenttemplate_attribs, pdata)
                    if pdata.get('startNumber') == '-1' or self.segtimeline: # Default to 1
                        remove_attribs(seg_template, ['startNumber'])

                    if self.segtimeline:
                        # add SegmentTimeline block in SegmentTemplate with timescale and window.
                        now = self.mpd_proc_cfg['now']
                        tsbd = self.cfg.timeshift_buffer_depth_in_s
                        ast = self.cfg.availability_start_time_in_s
                        start_time = max(ast + pdata['start_s'], now - tsbd)
                        if pdata.has_key('period_duration_s'):
                            end_time = min(ast + pdata['start_s'] + pdata['period_duration_s'], now)
                        else:
                            end_time = now
                        start_time -= self.cfg.availability_start_time_in_s
                        end_time -= self.cfg.availability_start_time_in_s
                        seg_timeline = segtimeline_generators[content_type].create_segtimeline(start_time, end_time)
                        remove_attribs(seg_template, ['duration'])
                        remove_attribs(seg_template, ['startNumber'])
                        seg_template.set('timescale', str(self.cfg.media_data[content_type]['timescale']))
                        media_template = seg_template.attrib['media']
                        media_template = media_template.replace('$Number$', 't$Time$')
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
        if messageData:
            elem.set("messageData", messageData)
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
            else: #Unknown or un-implemented UTCTiming method
                raise MpdModifierError("Unknown UTCTiming method: %s" % utc_method)
            mpd.insert(pos, time_elem)
            pos += 1
        return pos

    def get_full_xml(self, clean=True):
        "Get a string of all XML cleaned (no ns0 namespace)"
        ofh = cStringIO.StringIO()
        self.tree.write(ofh, encoding="utf-8")#, default_namespace=NAMESPACE)
        value = ofh.getvalue()
        if clean:
            value = value.replace("ns0:", "").replace("xmlns:ns0=", "xmlns=")
        xml_intro = '<?xml version="1.0" encoding="utf-8"?>\n'
        return xml_intro + value
