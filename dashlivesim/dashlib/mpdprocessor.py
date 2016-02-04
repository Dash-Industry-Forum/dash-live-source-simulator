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
import bisect
from xml.etree import ElementTree
import cStringIO
import time
import re
import os
from struct import unpack
from .configprocessor import SEGTIMEFORMAT, SegTimeEntry
from .timeformatconversions import make_timestamp

from . import scte35

SET_BASEURL = True
DASH_NAMESPACE = "{urn:mpeg:dash:schema:mpd:2011}"

RE_NAMESPACE_TAG = re.compile(r"({.*})?(.*)")

def add_ns(element):
    "Add DASH namespace to element or to path."
    parts = element.split('/')
    return "/".join([DASH_NAMESPACE + e for e in parts])

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
    "Process a VoD MPD. Analyzer and convert it to a live (dynamic) session."
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

    def process(self, data, period_data):
        "Top-level call to process the XML."
        mpd = self.root
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

        They should be in order ProgramInformation, UTCTiming, BaseURL, Location, Period, Metrics."""
        children = mpd.getchildren()
        pos = 0
        for child in children:
            if child.tag != add_ns('ProgramInformation'):
                break
            pos += 1
        pos = self.insert_utc_timings(mpd, pos)
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
                    self.insert_baseurl(mpd, pos, url_header + "//" + "/".join(url_parts) + "/")
                    del url_parts[-2]
                    pos += 1
            else:
                self.insert_baseurl(mpd, pos, data['BaseURL'])
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
        self.update_periods(mpd, period_data, data['periodOffset'] >= 0)

    def insert_baseurl(self, mpd, pos, new_baseurl):
        "Create and insert a new <BaseURL> element."
        baseurl_elem = ElementTree.Element(add_ns('BaseURL'))
        baseurl_elem.text = new_baseurl
        baseurl_elem.tail = "\n"
        mpd.insert(pos, baseurl_elem)

    def modify_baseurl(self, baseurl_elem, new_baseurl):
        "Modify the text of an existing BaseURL"
        baseurl_elem.text = new_baseurl

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
                segmentbase_elem.set('presentation_time_offset', str(presentation_time_offset))
            period.insert(0, segmentbase_elem)

        def create_inband_scte35stream_elem():
            "Create an InbandEventStream element for SCTE-35."
            return self.create_descriptor_elem("InbandEventStream", scte35.SCHEME_ID_URI, value=str(scte35.PID))

        def create_segment_timeline(seg_template, content_type, pos):
            "Create and insert a new <SegmentTimeline> element and S entries for interval [now-tsbd, now]."
            media_data = self.cfg.media_data[content_type]
            remove_attribs(seg_template, ['duration'])
            remove_attribs(seg_template, ['startNumber'])
            timescale = media_data['timescale']
            seg_template.set('timescale', str(timescale))
            media_template = seg_template.attrib['media']
            media_template = media_template.replace('$Number$', 't$Time$')
            seg_template.set('media', media_template)
            seg_timeline = ElementTree.Element(add_ns('SegmentTimeline'))
            seg_timeline.text = "\n"
            seg_timeline.tail = "\n"
            seg_template.insert(pos, seg_timeline)
            now = self.mpd_proc_cfg['now']
            tsbd = self.cfg.timeshift_buffer_depth_in_s

            #Interval start = max(now-timeshift_buffer_depth_in_s, period_start)
            #Interval end = min(now, period_end)

            start = (now - tsbd)*timescale
            end = now*timescale

            wrap_duration = 3600*timescale
            wrap_offset = 0*timescale #AST

            # The start segment is the latest one that starts before or at start
            # The end segment is the latest one that ends before now.

            dat_file = media_data['dat_file']
            dat_file_path = os.path.join(self.cfg.vod_cfg_dir, dat_file)
            segtimedata = [] # Tuples corresponding to SegTimeEntry
            with open(dat_file_path, "rb") as ifh:
                data = ifh.read(12)
                while data:
                    ste = SegTimeEntry(*unpack(SEGTIMEFORMAT, data))
                    segtimedata.append(ste)
                    data = ifh.read(12)

            interval_starts = [std[2] for std in segtimedata]

            def get_seg_starttime(nr_wraps, seg_data, repeats):
                "Get the segment starttime given repeats."
                return wrap_offset + nr_wraps*wrap_duration + seg_data.start_time + repeats*seg_data.duration

            def find_latest_starting_before(act_time):
                "Fint the latest segment starting before act_time."
                nr_wraps = (act_time - wrap_offset) // wrap_duration
                if nr_wraps < 0:
                    return (None, None, None)# This is before AST
                wrap_start_time = wrap_offset + nr_wraps * wrap_duration
                rel_time = act_time - wrap_start_time
                index = bisect.bisect(interval_starts, rel_time) - 1
                seg_data = segtimedata[index]
                repeats = 0
                accumulated_end_time = seg_data.start_time + seg_data.duration
                while accumulated_end_time < rel_time:
                    accumulated_end_time += seg_data.duration
                    repeats += 1
                return (index, repeats, nr_wraps)

            def find_repeats_ending_before(act_time, index, nr_wraps):
                "Find the repeats given values of act_time, index, nr_wrapts."
                wrap_start_time = wrap_offset + nr_wraps * wrap_duration
                seg_data = segtimedata[index]
                rel_time = act_time - wrap_start_time
                repeats = 0
                accumulated_end_time = seg_data.start_time + seg_data.duration
                while True:
                    accumulated_end_time += seg_data.duration
                    if accumulated_end_time > rel_time:
                        break
                    repeats += 1
                    if repeats > seg_data.repeats:
                        print "Inconsistent table of segment durations. repeats = %d" % repeats
                        return
                return repeats

            (end_index, end_repeats, end_wraps) = find_latest_starting_before(end)
            if end_index is None:
                return
            if end_repeats > 0:
                end_repeats -= 1  # Just move one segment back in the repeat
            elif end_index > 0:
                end_index -= 1
                end_repeats = find_repeats_ending_before(end, end_index, end_wraps)
            else:
                end_wraps -= 1
                if end_wraps < 0:
                    return
                end_index = len(segtimedata) - 1
                end_repeats = find_repeats_ending_before(end, end_index, end_wraps)

            (start_index, start_repeats, start_wraps) = find_latest_starting_before(start)

            def generate_s_elem(start_time, duration, repeat):
                "Generate the S elements for the SegmentTimeline."
                s_elem = ElementTree.Element(add_ns('S'))
                if start_time is not None:
                    s_elem.set("t", str(start_time))
                s_elem.set("d", str(duration))
                if repeat > 0:
                    s_elem.set('r', str(repeat))
                s_elem.tail = "\n"
                seg_template.insert = seg_timeline.insert(0, s_elem)

            repeat_index = end_index
            nr_wraps = end_wraps
            while repeat_index != start_index or nr_wraps != start_wraps:
                seg_data = segtimedata[repeat_index]
                if repeat_index == end_index:
                    generate_s_elem(None, seg_data.duration, end_repeats)
                else:
                    generate_s_elem(None, seg_data.duration, seg_data.repeats)
                repeat_index -= 1
                if repeat_index < 0:
                    nr_wraps -= 1
                    repeat_index = len(segtimedata) - 1
                end_repeats = segtimedata[repeat_index].repeats
            # Now at first entry corresponding to start_index and start_wraps
            seg_data = segtimedata[start_index]
            generate_s_elem(get_seg_starttime(nr_wraps, seg_data, start_repeats), seg_data.duration,
                            end_repeats - start_repeats)

        periods = mpd.findall(add_ns('Period'))
        last_period_id = '-1'
        for (period, pdata) in zip(periods, period_data):
            set_attribs(period, ('id', 'start'), pdata)
            if pdata.has_key('etpDuration'):
                period.set('duration', "PT%dS" % pdata['etpDuration'])
            segmenttemplate_attribs = ['startNumber']
            pto = pdata['presentationTimeOffset']
            if pto:
                if offset_at_period_level:
                    insert_segmentbase(period, pdata['presentationTimeOffset'])
                else:
                    segmenttemplate_attribs.append('presentationTimeOffset')
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
                    if pdata.get('startNumber') == '-1': # Default to 1
                        remove_attribs(seg_template, ['startNumber'])

                    if self.segtimeline:
                        # add SegmentTimeline block in SegmentTemplate with timescale and window.
                        create_segment_timeline(seg_template, content_type, 0)
            last_period_id = pdata.get('id')

    def create_descriptor_elem(self, name, scheme_id_uri, value=None, elem_id=None):
        "Create an element of DescriptorType."
        elem = ElementTree.Element(add_ns(name))
        elem.set("schemeIdUri", scheme_id_uri)
        if value:
            elem.set("value", value)
        if elem_id:
            elem.set("id", elem_id)
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
