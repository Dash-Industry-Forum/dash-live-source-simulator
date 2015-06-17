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

from .timeformatconversions import make_timestamp
from dashlivesim.dashlib import scte35

SET_BASEURL = True
DASH_NAMESPACE = "{urn:mpeg:dash:schema:mpd:2011}"

RE_NAMESPACE_TAG = re.compile(r"({.*})?(.*)")


def process_manifest(filename, in_data, now, utc_timing_methods, utc_head_url):
    "Process the manifest and provide a changed one."
    new_data = {'publishTime' : '%s' % make_timestamp(in_data['publishTime']),
                'availabilityStartTime' : '%s' % make_timestamp(in_data['availability_start_time_in_s']),
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
    mpd_proc = MpdProcessor(filename, in_data['scte35Present'], utc_timing_methods, utc_head_url)
    if in_data['periodsPerHour'] < 0: # Default case.
        period_data = generate_default_period_data(in_data, new_data)
    else:
        period_data = generate_multiperiod_data(in_data, new_data, now)
    mpd_proc.process(new_data, period_data)
    return mpd_proc.get_full_xml()

def generate_default_period_data(in_data, new_data):
    "Generate period data for a single period starting at the same time as the session (start = PT0S)."
    start = 0
    seg_dur = in_data['segDuration']
    start_number = in_data['startNumber'] + start/seg_dur
    data = {'id' : "p0", 'start' : 'PT%dS' % start, 'duration' : seg_dur,
            'presentationTimeOffset' : "%d" % new_data['presentationTimeOffset'],
            'startNumber' : str(start_number)}
    return [data]

def generate_multiperiod_data(in_data, new_data, now):
    "Generate an array of period data depending on current time (now). 0 gives one period with start offset."
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
    else: # nrPeriodsPerHour == 0, make one old period but starting 1000h after epoch
        start = 3600*1000
        data = {'id' : "p0", 'start' : 'PT%dS' % start, 'startNumber' : "%d" % (start/seg_dur),
                'duration' : seg_dur, 'presentationTimeOffset' : "%d" % start}
        period_data.append(data)
    return period_data


class MpdProcessorError(Exception):
    "Generic MpdProcessor error."
    pass


class MpdProcessor(object):
    "Process a VoD MPD. Analyzer and convert it to a live (dynamic) session."
    # pylint: disable=no-self-use, too-many-locals

    def __init__(self, infile, scte35_present, utc_timing_methods, utc_head_url=""):
        self.tree = ElementTree.parse(infile)
        self.scte35_present = scte35_present
        self.utc_timing_methods = utc_timing_methods
        self.utc_head_url = utc_head_url
        self.root = self.tree.getroot()

    def process(self, data, period_data):
        "Top-level call to process the XML."
        mpd = self.root
        self.process_mpd(mpd, data)
        self.process_mpd_children(mpd, data, period_data)

    def process_mpd(self, mpd, data):
        """Process the root element (MPD)"""
        assert mpd.tag == self.add_ns('MPD')
        mpd.set('type', "dynamic")
        if self.scte35_present:
            old_profiles = mpd.get('profiles')
            if not old_profiles.find(scte35.PROFILE) >= 0:
                new_profiles = old_profiles + "," + scte35.PROFILE
                mpd.set('profiles', new_profiles)
        key_list = ['availabilityStartTime', 'availabilityEndTime', 'timeShiftBufferDepth',
                    'minimumUpdatePeriod', 'maxSegmentDuration', 'mediaPresentationDuration']
        self.set_attribs_from_dict(mpd, key_list, data)
        if mpd.attrib.has_key('mediaPresentationDuration') and not data.has_key('mediaPresentationDuration'):
            del mpd.attrib['mediaPresentationDuration']

    def process_mpd_children(self, mpd, data, period_data):
        """Process the children of the MPD element.

        They should be in order ProgramInformation, UTCTiming, BaseURL, Location, Period, Metrics."""
        pos = 0
        for child in mpd:
            if not self.compare_tag(child.tag, 'ProgramInformation'):
                break
            pos += 1
        pos = self.insert_utc_timings(mpd, pos)
        next_child = mpd[pos]
        if self.compare_tag(next_child.tag, 'BaseURL'):
            if not data.has_key('BaseURL') or not SET_BASEURL:
                self.root.remove(next_child)
            else:
                self.modify_baseurl(next_child, data['BaseURL'])
                pos += 1
        elif data.has_key('BaseURL') and SET_BASEURL:
            self.insert_baseurl(mpd, pos, data['BaseURL'])
            pos += 1
        assert self.compare_tag(mpd[pos].tag, 'Period')
        self.update_periods(mpd, pos, period_data, data['periodOffset'] >= 0)

    def add_ns(self, element):
        "Add DASH namespace to element or to path."
        parts = element.split('/')
        return "/".join([DASH_NAMESPACE + e for e in parts])

    def tag_and_namespace(self, full_tag):
        "Extract tag and namespace."
        match_obj = RE_NAMESPACE_TAG.match(full_tag)
        tag = match_obj.group(2)
        namespace = match_obj.group(1)
        return (tag, namespace)

    def compare_tag(self, full_tag, string):
        "Compare tag to see if it is equal."
        tag, namespace = self.tag_and_namespace(full_tag)
        assert namespace == DASH_NAMESPACE
        return tag == string

    def set_attrib_from_dict(self, element, key, data):
        "Set attribute key of element to value data[key], if present."
        if data.has_key(key):
            element.set(key, str(data[key]))

    def set_attribs_from_dict(self, element, keys, data):
        "Set attribute key of element to value data[key] for all keys (if present)."
        for key in keys:
            if data.has_key(key):

                if ((key == "presentationTimeOffset" and str(data[key]) == "0") or
                        (key == 'startNumber' and data[key] == "-1")):
                    # Remove attribute if default. For startNumber the default is 1, but we use -1 to signal this.
                    if key in element.attrib:
                        del element.attrib[key]
                    continue
                element.set(key, str(data[key]))

    def remove_attribs(self, element, keys):
        "Remove attributes from element."
        for key in keys:
            if key in element.attrib:
                del element.attrib[key]

    def insert_baseurl(self, element, pos, new_baseurl):
        "Create and insert a new <BaseURL> element."
        baseurl_elem = ElementTree.Element(self.add_ns('BaseURL'))
        baseurl_elem.text = new_baseurl
        baseurl_elem.tail = "\n"
        element.insert(pos, baseurl_elem)

    def modify_baseurl(self, baseurl_elem, new_baseurl):
        "Modify the text of an existing BaseURL"
        baseurl_elem.text = new_baseurl

    def insert_segmentbase(self, period, presentation_time_offset):
        "Insert SegmentBase element."
        segmentbase_elem = ElementTree.Element(self.add_ns('SegmentBase'))
        if presentation_time_offset != 0:
            segmentbase_elem.set('presentation_time_offset', str(presentation_time_offset))
        period.insert(0, segmentbase_elem)

    def create_inband_scte35stream_elem(self):
        "Create an InbandEventStream element for SCTE-35."
        return self.create_descriptor_element("InbandEventStream", scte35.SCHEME_ID_URI)

    def create_descriptor_element(self, name, scheme_id_uri, value=None, elem_id=None):
        "Create an element of DescriptorType."
        element = ElementTree.Element(self.add_ns(name))
        element.set("schemeIdUri", scheme_id_uri)
        if value:
            element.set("value", value)
        if elem_id:
            element.set("id", elem_id)
        element.tail = "\n"
        return element

    def update_periods(self, mpd, the_period_pos, period_data, offset_at_period_level=False):
        "Update periods to provide appropriate values."

        periods = mpd.findall(self.add_ns('Period'))
        assert len(periods) == 1

        period = mpd[the_period_pos]
        for i in range(1, len(period_data)):
            new_period = copy.deepcopy(period)
            mpd.insert(the_period_pos+i, new_period)

        periods = mpd.findall(self.add_ns('Period'))
        for (period, pdata) in zip(periods, period_data):
            self.set_attribs_from_dict(period, ('id', 'start'), pdata)
            segment_template_attribs = ['startNumber']
            pto = pdata['presentationTimeOffset']
            if pto:
                if offset_at_period_level:
                    self.insert_segmentbase(period, pdata['presentationTimeOffset'])
                else:
                    segment_template_attribs.append('presentationTimeOffset')
            adaptation_sets = period.findall(self.add_ns('AdaptationSet'))
            for ad_set in adaptation_sets:
                content_type = ad_set.get('contentType')
                if content_type == 'video' and self.scte35_present:
                    scte35_elem = self.create_inband_scte35stream_elem()
                    ad_set.insert(0, scte35_elem)
                seg_templates = ad_set.findall(self.add_ns('SegmentTemplate'))
                for seg_template in seg_templates:
                    self.set_attribs_from_dict(seg_template, segment_template_attribs, pdata)

    def insert_utc_timings(self, mpd, start_pos):
        """Insert UTCTiming elements right after program information in order given by self.utc_timing_methods.

        The version of DASH should also be updated, but that is not done yet."""

        pos = start_pos
        for utc_method in self.utc_timing_methods:
            if utc_method == "direct":
                direct_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()))
                time_elem = self.create_descriptor_element('UTCTiming', 'urn:mpeg:dash:utc:direct:2014', direct_time)
            elif utc_method == "head":
                time_elem = self.create_descriptor_element('UTCTiming', 'urn:mpeg:dash:utc:http-head:2014',
                                                           self.utc_head_url)
            else: #Unknown or un-implemented UTCTiming method
                raise MpdProcessorError("Unknown UTCTiming method: %s" % utc_method)
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
