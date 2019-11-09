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
import cStringIO
import time

from timeformatconversions import make_timestamp
import scte35
from segtimeline import SegmentTimeLineGenerator
from dash_namespace import add_ns, add_patch_ns
import patch_ops

SET_BASEURL = True

UTC_TIMING_NTP_SERVER = '1.de.pool.ntp.org'
UTC_TIMING_SNTP_SERVER = 'time.kfki.hu'
UTC_TIMING_HTTP_SERVER = 'http://time.akamai.com/?iso'


def set_value_from_dict(element, key, data):
    "Set attribute key of element to value data[key], if present."
    if data.has_key(key):
        element.set(key, str(data[key]))

def set_values_from_dict(element, keys, data):
    "Set attribute key of element to value data[key] for all keys (if present)."
    for key in keys:
        if data.has_key(key):
            element.set(key, str(data[key]))

def find_template_period(mpd, pos=0):
    children = mpd.getchildren()
    for ch_nr in range(pos, len(children)):
        if children[ch_nr].tag == add_ns("Period"):
            return (mpd.getchildren()[ch_nr], ch_nr)

    raise MpdModifierError("No period found.")

class MpdModifierError(Exception):
    "Generic MpdModifier error."
    pass


class MpdProcessor(object):
    "Process a VoD MPD. Analyze and convert it to a live (dynamic) session."
    #pylint: disable=no-self-use, too-many-locals, too-many-instance-attributes

    def __init__(self, infile, mpd_proc_cfg, cfg=None, full_url=None):
        self.tree = ElementTree.parse(infile)
        self.scte35_present = mpd_proc_cfg['scte35Present']
        self.utc_timing_methods = mpd_proc_cfg['utc_timing_methods']
        self.utc_head_url = mpd_proc_cfg['utc_head_url']
        self.continuous = mpd_proc_cfg['continuous']
        self.segtimeline = mpd_proc_cfg['segtimeline']
        self.segtimeline_nr = mpd_proc_cfg['segtimeline_nr']
        self.patching = mpd_proc_cfg['patching']
        self.patch_base = mpd_proc_cfg['patch_base']
        self.mpd_proc_cfg = mpd_proc_cfg
        self.cfg = cfg
        self.full_url = full_url
        self.root = self.tree.getroot()
        self.availability_start_time_in_s = None
        self.emsg_last_seg=cfg.emsg_last_seg if cfg is not None else False
        self.segtimelineloss=cfg.segtimelineloss if cfg is not None else False

    def process(self, mpd_data, period_data):
        "Top-level call to process the XML."
        mpd = self.root
        self.availability_start_time_in_s = mpd_data[
            'availability_start_time_in_s']

        if self.patching:
            # when patching we avoid announcing future periods, filter them out
            period_data = list(filter(lambda pdata: pdata['presentationTimeOffset'] <= self.mpd_proc_cfg['now'], period_data))

        if self.patch_base == -1:
            # generate full manifest if patch base absent
            self.process_mpd(mpd, mpd_data)
            self.process_mpd_children(mpd, mpd_data, period_data)
        else:
            # replace existing manifest with patch
            patch = ElementTree.Element(add_patch_ns('Patch'))
            self.tree = ElementTree.ElementTree(patch)
            self.root = self.tree.getroot()
            self.process_patch(patch, mpd, mpd_data, period_data)

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
                new_profiles=old_profiles.replace("dash-if-simple","dash-if-main")
                mpd.set('profiles', new_profiles)
        key_list = ['availabilityStartTime', 'availabilityEndTime', 'timeShiftBufferDepth',
                    'minimumUpdatePeriod', 'maxSegmentDuration',
                    'mediaPresentationDuration', 'suggestedPresentationDelay']
        if mpd_data.get('type', 'dynamic') == 'static':
            key_list.remove('minimumUpdatePeriod')
        if (mpd_data.get('type', 'dynamic') == 'static' or
                    mpd_data.get('mediaPresentationDuration')):
            key_list.remove('timeShiftBufferDepth')
        set_values_from_dict(mpd, key_list, mpd_data)
        if mpd.attrib.has_key('mediaPresentationDuration') and not mpd_data.has_key('mediaPresentationDuration'):
            del mpd.attrib['mediaPresentationDuration']
        mpd.set('publishTime', make_timestamp(self.mpd_proc_cfg['now'])) #TODO Correlate time with change in MPD
        mpd.set('id', 'Config part of url maybe?')
        if self.segtimeline or self.segtimeline_nr:
            if mpd.attrib.has_key('maxSegmentDuration'):
                del mpd.attrib['maxSegmentDuration']
            if mpd_data.get('type', 'dynamic') != 'static':
                mpd.set('minimumUpdatePeriod', "PT0S")

    #pylint: disable = too-many-branches
    def process_mpd_children(self, mpd, data, period_data):
        """Process the children of the MPD element.
        They should be in order ProgramInformation, BaseURL, Location, Period, UTCTiming, Metrics."""
        ato = 0
        if data.has_key('availabilityTimeOffset'):
            ato = data['availabilityTimeOffset']
        children = mpd.getchildren()
        pos = 0
        for child in children:
            if child.tag != add_ns('ProgramInformation'):
                break
            pos += 1
        next_child = mpd.getchildren()[pos]
        set_baseurl = SET_BASEURL
        if self.cfg and self.cfg.add_location:
            set_baseurl = False  # Cannot have both BASEURL and Location
        if next_child.tag == add_ns('BaseURL'):
            if not data.has_key('BaseURL') or not set_baseurl:
                self.root.remove(next_child)
            else:
                self.modify_baseurl(next_child, data['BaseURL'])
                pos += 1
        elif data.has_key('BaseURL') and set_baseurl:
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
                    self.insert_baseurl(mpd, pos, url_header + "//" + "/".join(url_parts) + "/", ato)
                    del url_parts[-2]
                    pos += 1
            else:
                self.insert_baseurl(mpd, pos, data['BaseURL'], ato)
                pos += 1
        if self.cfg and self.cfg.add_location and self.full_url is not None:
            loc_url = re.sub(r"/startrel_[-\d]+", "/start_%d" %
                             self.cfg.start_time, self.full_url)
            loc_url = re.sub(r"/stoprel_[-\d]+", "/stop_%d" %
                             self.cfg.stop_time, loc_url)
            self.insert_location(mpd, pos, loc_url)
            pos += 1

        if self.patching:
            # replace the original patching key with the in-memory manifest publish time
            patch_url = re.sub(r"/patching_[-\d]+", "/patch_%d" % 
                               self.mpd_proc_cfg['now'], self.full_url)
            # also change the extension type to be patch instead of mpd
            patch_url = re.sub(r"\.mpd$", ".patch", patch_url)
            self.insert_patch_location(mpd, pos, patch_url)
            pos += 1

        (period, pos) = find_template_period(mpd, pos)

        for i in range(1, len(period_data)):
            new_period = copy.deepcopy(period)
            mpd.insert(pos+i, new_period)
        self.insert_utc_timings(mpd, pos+len(period_data))

        periods = mpd.findall(add_ns('Period'))
        last_period_id = '-1'
        segtimeline_generators = self.create_timeline_generators()
        for (period, pdata) in zip(periods, period_data):
            self.update_period(mpd, period, pdata, last_period_id, data['periodOffset'] >= 0, segtimeline_generators)
            last_period_id = pdata.get('id')

    def process_patch(self, patch, mpd, mpd_data, period_data):
        """Process the root element (Patch)"""
        patch.set('mpdId', mpd.get('id', 'Config part of url maybe?'))
        patch.set('publishTime', make_timestamp(self.mpd_proc_cfg['now']))
        patch.set('originalPublishTime', make_timestamp(self.patch_base))

        # Insert publish time update node
        publish_replace = patch_ops.insert_replace_op(patch, '/MPD/@publishTime')
        publish_replace.text = make_timestamp(self.mpd_proc_cfg['now'])

        # Insert patch location update node
        patch_location = re.sub(r"/patch_[-\d]+", "/patch_%d" % 
                                self.mpd_proc_cfg['now'], self.full_url)
        patch_replace = patch_ops.insert_replace_op(patch, '/MPD/PatchLocation[0]')
        self.insert_patch_location(patch_replace, 0, patch_location)

        # For this simulator we assume patches will not be announcing new high level structures
        # it is completely possible for them to do that, but this simulator only needs basic
        # timeline extension ability
        
        # Find the base period
        (original_period, _) = find_template_period(mpd)

        # Go through periods defined for update:
        # - Periods before the patch base that have new segments have the segments patched in
        # - Periods after the patch base are completely added

        segtimeline_generators = self.create_timeline_generators()
        last_period_id = '-1'
        for pdata in period_data:
            if pdata.get('presentationTimeOffset') > self.patch_base:
                # Period is new with this patch, clone original, setup like normal
                period = copy.deepcopy(original_period)
                self.update_period(mpd, period, pdata, last_period_id, mpd_data['periodOffset'] >= 0, segtimeline_generators)

                # create the actual insertion operation
                period_add = patch_ops.insert_add_op(patch, '/MPD', 'append')
                period_add.append(period)

            elif segtimeline_generators:
                # Period already exists in memory and we use segment timeline
                # We therefore have to generate extensions to the inmemory timeline
                # Note only one previous period should ever be added to, not gating on that explicitly here
                adaptation_sets = original_period.findall(add_ns('AdaptationSet'))
                for ad_set in adaptation_sets:
                    content_type = ad_set.get('contentType')
                    segtime_gen = segtimeline_generators[content_type]
                    seg_templates = ad_set.findall(add_ns('SegmentTemplate'))
                    for seg_template in seg_templates:
                        (start_time, end_time, use_closest) = self.compute_period_times(pdata)
                        start_time = self.patch_base # always force start to patch base for consistency
                        seg_timeline = segtime_gen.create_segtimeline(
                                            start_time, end_time, use_closest)
                        
                        # only append if there are children
                        s_elems = seg_timeline.getchildren()
                        if len(s_elems) > 0:
                            timeline_location = "/MPD/Period[@id='%s']/AdaptationSet[@id='%s']/SegmentTemplate/SegmentTimeline" % (pdata.get('id'), ad_set.get('id'))
                            timeline_add = patch_ops.insert_add_op(patch, timeline_location, 'append')
                            timeline_add.extend(s_elems)

            last_period_id = pdata.get('id')

    def insert_baseurl(self, mpd, pos, new_baseurl, new_ato):
        "Create and insert a new <BaseURL> element."
        baseurl_elem = ElementTree.Element(add_ns('BaseURL'))
        baseurl_elem.text = new_baseurl
        baseurl_elem.tail = "\n"
        if float(new_ato) == -1:
            self.insert_ato(baseurl_elem, 'INF')
        elif float(new_ato) > 0:  # don't add this attribute when the value is 0
            self.insert_ato(baseurl_elem, new_ato)
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

    def insert_patch_location(self, mpd, pos, patch_location_url):
        patch_location_elem = ElementTree.Element(add_ns('PatchLocation'))
        patch_location_elem.text = patch_location_url
        patch_location_elem.tail = "\n"
        patch_location_elem.set('ttl', str(60)) # todo config patch validity duration
        mpd.insert(pos, patch_location_elem)

    #pylint: disable = too-many-statements
    def update_period(self, mpd, period, pdata, last_period_id, offset_at_period_level=False, segtimeline_generators=None):
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

        def create_inband_stream_elem():
            "Create an InbandEventStream element for signalling emsg in Rep when encoder fails to generate new segments, IOP 4.11.4.3 scenario."
            return self.create_descriptor_elem("InbandEventStream", "urn:mpeg:dash:event:2012", value=str(1))
        
        def create_inline_mpdcallback_elem(BaseURLSegmented):
            "Create an EventStream element for MPD Callback."
            return self.create_descriptor_elem("EventStream", "urn:mpeg:dash:event:callback:2015", value=str(1),
                                               elem_id=None, messageData=BaseURLSegmented)
        BaseURL = mpd.findall(add_ns('BaseURL'))
        if len(BaseURL) > 0:
            BaseURLParts = BaseURL[0].text.split('/')
            if len(BaseURLParts) > 3:
                BaseURLSegmented = BaseURLParts[0] + '//' + BaseURLParts[2] + '/' + BaseURLParts[3] + '/mpdcallback/'

        set_attribs(period, ('id', 'start'), pdata)
        if pdata.has_key('etpDuration'):
            period.set('duration', "PT%dS" % pdata['etpDuration'])
        if pdata.has_key('periodDuration'):
            period.set('duration', pdata['periodDuration'])
        segmenttemplate_attribs = ['startNumber']
        pto = pdata['presentationTimeOffset']
        if pto:
            if offset_at_period_level:
                insert_segmentbase(period, pto)
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
            if self.emsg_last_seg:
                inband_event_elem = create_inband_stream_elem()
                ad_set.insert(0, inband_event_elem)
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

                if (self.segtimeline or self.segtimeline_nr) and segtimeline_generators:
                    # add SegmentTimeline block in SegmentTemplate with timescale and window.
                    segtime_gen = segtimeline_generators[content_type]
                    (start_time, end_time, use_closest) = self.compute_period_times(pdata)
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

    def compute_period_times(self, pdata):
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
        use_closest = False
        if self.cfg.stop_time and self.cfg.timeoffset == 0:
            start_time = self.cfg.start_time
            end_time = min(now, self.cfg.stop_time)
            use_closest = True

        return (start_time, end_time, use_closest)

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

    def create_timeline_generators(self):
        segtimeline_generators = None
        if self.segtimeline or self.segtimeline_nr:
            segtimeline_generators = {}
            for content_type in ('video', 'audio'):
                segtimeline_generators[content_type] = SegmentTimeLineGenerator(self.cfg.media_data[content_type],
                                                                                self.cfg)
        return segtimeline_generators

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
