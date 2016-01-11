"""DASH MPD processor and classes for MPD elements."""

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

from xml.etree import ElementTree
import cStringIO
import re

from ..dashlib import timeformatconversions as tfc

RE_DURATION = re.compile(r"PT((?P<hours>\d+)H)?((?P<minutes>\d+)M)?((?P<seconds>\d+)S)?")
RE_NAMESPACE_TAG = re.compile(r"({.*})?(.*)")

class MpdElementError(Exception):
    "General MpdElement Error."

class MpdElement(object):
    "BaseClass for MPD elements."

    def __init__(self, node):
        self.node = node
        self.attribs = {}

    #pylint: disable=no-self-use
    def parse(self):
        "Parse the node and its children."
        raise MpdElementError("Not implemented")

    #pylint: disable=no-self-use, unused-argument
    def make_live(self, data):
        "Change attributes and values to make this MPD live. Use the data dictionary for this."
        raise MpdElementError("Not implemented")

    #pylint: disable=no-self-use, unused-variable
    def tag_and_namespace(self, full_tag):
        "Extract tag and namespace."
        match_obj = RE_NAMESPACE_TAG.match(full_tag)
        tag = match_obj.group(2)
        namespace = match_obj.group(1)
        return (tag, namespace)

    def compare_tag(self, full_tag, string):
        "Compare tag to see if it is equal."
        tag, namespace = self.tag_and_namespace(full_tag)
        return tag == string

    def check_and_add_attributes(self, node, attribs):
        "Check if node has attributes and add them to self.attribs."
        for attr in attribs:
            if node.attrib.has_key(attr):
                self.attribs[attr] = node.attrib[attr]
            else:
                if not self.attribs.has_key(attr):
                    self.attribs[attr] = None

    def set_value(self, element, key, data):
        "Set attribute key of element to value data[key], if present."
        if data.has_key(key):
            element.set(key, str(data[key]))


class Mpd(MpdElement):
    "Top level MPD element."

    def __init__(self, node):
        MpdElement.__init__(self, node)
        self.periods = []

    def parse(self):
        "Parse the node and its children."
        self.check_and_add_attributes(self.node, ('profiles', 'maxSegmentDuration', 'minBufferTime',
                                                  'type', 'mediaPresentationDuration'))
        for child in self.node.getchildren():
            if self.compare_tag(child.tag, 'Period'):
                period = Period(child)
                period.parse()
                self.periods.append(period)

    def make_live(self, data):
        "Change attributes and values to make this MPD live. Use the data dictionary for this."
        self.set_value(self.node, 'type', 'dynamic')
        for attr in ('availabilityStartTime', 'availabilityEndTime'):
            self.set_value(self.node, attr, data[attr])
        for period in self.periods:
            period.make_live(data)


class Period(MpdElement):
    "Period element in MPD."

    def __init__(self, node):
        MpdElement.__init__(self, node)
        self.adaptation_sets = []

    def parse(self):
        "Parse the node and its children."
        self.check_and_add_attributes(self.node, ('id', 'start'))
        for child in self.node.getchildren():
            if self.compare_tag(child.tag, 'AdaptationSet'):
                adaptation_set = AdaptationSet(child)
                adaptation_set.parse()
                self.adaptation_sets.append(adaptation_set)

    def make_live(self, data):
        for attr in ('start'):
            self.set_value(self.node, attr, data[attr])
        for adaptation_set in self.adaptation_sets:
            adaptation_set.make_live(data)


class AdaptationSet(MpdElement):
    "AdaptationSet element in a Period."

    def __init__(self, node):
        MpdElement.__init__(self, node)
        self.segment_template = None
        self.representations = []

    @property
    def content_type(self):
        "Get the contentType for the AdaptationSet."
        return self.attribs['contentType']

    @property
    def media_pattern(self):
        "Get the media pattern from SegmentTemplate."
        return self.attribs['media']

    @property
    def initialization_pattern(self):
        "Get the initialization pattern from SegmentTemplate."
        return self.attribs['initialization']

    @property
    def start_number(self):
        "StartNumber for segments (from SegmentTemplate)."
        return int(self.attribs['startNumber'])

    @property
    def duration(self):
        "Segment duration (in whole seconds)."
        return int(self.attribs['duration'])

    def parse(self):
        "Parse the node and its children."
        self.check_and_add_attributes(self.node, ('contentType', 'mimeType'))
        for child in self.node.getchildren():
            if self.compare_tag(child.tag, 'SegmentTemplate'):
                self.check_and_add_attributes(child, ('initialization', 'startNumber', 'media',
                                                      'duration', 'timescale'))
            elif self.compare_tag(child.tag, 'Representation'):
                rep = Representation(self, child)
                rep.parse()
                self.representations.append(rep)

    def make_live(self, data):
        for attr in ('startNr'):
            self.set_value(self.node, attr, data[attr])
        for adaptation_set in self.adaptation_sets:
            adaptation_set.make_live(data)


class Representation(MpdElement):
    "Representation element in an AdaptationSet."

    def __init__(self, adaptation_set, node):
        MpdElement.__init__(self, node)
        self.adaptation_set = adaptation_set

    @property
    def initialization_path(self):
        "The initialization path of this representation."
        return self.get_initialization_path()

    @property
    def rep_id(self):
        "Id of this representation."
        return self.attribs['id']

    def parse(self):
        "Parse the node and its children."
        self.check_and_add_attributes(self.node, ('id', 'bandwidth'))

    def get_initialization_path(self):
        "The initialization path of this representation."
        init_pattern = self.adaptation_set.initialization_pattern
        rep_id = self.attribs['id']
        bandwidth= self.attribs['bandwidth']
        init_path = init_pattern.replace("$RepresentationID$", rep_id).replace("$bandwidth$", bandwidth)
        return init_path

    def get_media_path(self, segNr="%d"):
        "Return the media path for this representation and given segNr."
        media_pattern = self.adaptation_set.media_pattern
        rep_id = self.attribs['id']
        bandwidth= self.attribs['bandwidth']
        media_path = media_pattern.replace("$RepresentationID$", rep_id).replace("$bandwidth$", bandwidth)
        media_path = media_path.replace("$Number$", str(segNr))
        return media_path


class MpdProcessor(MpdElement):
    """Modify the mpd to become live. Whatever is input in data is set to these values."""

    def __init__(self, infile):
        self.tree = ElementTree.parse(infile)
        self.mpd_namespace = None
        self.root = self.tree.getroot()
        self.is_base_url_set = False
        self.adaptation_sets = []
        self.media_presentation_duration = None
        self.media_presentation_duration_in_s = None
        self.muxed_rep = None
        self.parse()

    def parse(self):
        "Parse and find all the adaptation sets and their representations."
        mpd = self.root
        tag, self.mpd_namespace = self.tag_and_namespace(mpd.tag)
        assert tag == "MPD"
        if mpd.attrib.has_key('mediaPresentationDuration'):
            self.media_presentation_duration = mpd.attrib['mediaPresentationDuration']
            self.media_presentation_duration_in_s = tfc.iso_duration_to_seconds(self.media_presentation_duration)
            print "Found mediaPresentationDuration = %ds" % self.media_presentation_duration_in_s
        for child in mpd:
            if self.compare_tag(child.tag, 'Period'):
                for grand_child in child:
                    if self.compare_tag(grand_child.tag, 'AdaptationSet'):
                        AS = AdaptationSet(grand_child)
                        AS.parse()
                        self.adaptation_sets.append(AS)

    def get_adaptation_sets(self):
        return self.adaptation_sets

    def getMuxedRep(self):
        return self.muxed_rep

    def getMuxedInitPath(self):
        initPath = None
        for AS in self.adaptation_sets:
            if AS.contentType == "video":
                print AS.initialization
                initPath = AS.initialization.replace("$RepresentationID$", self.muxed_rep)
        return initPath

    def getMuxedMediaPath(self):
        mediaPath = None
        for AS in self.adaptation_sets:
            if AS.contentType == "video":
                mediaPath = AS.media.replace("$RepresentationID$", self.muxed_rep).replace("$Number$", "%d")
        return mediaPath

    def process(self, mpdData = {}):
        MPD = self.root
        self.processMPD(MPD, mpdData)

    def makeLiveMpd(self, data):
        """Process the root element (MPD) and set values from data dictionary.

        Typical keys are: availabilityStartTime, timeShiftBufferDepth, minimumUpdatePeriod."""
        MPD = self.root
        MPD.set('type', "dynamic")
        for key in data.keys():
            self.setValue(MPD, key, data)
        if MPD.attrib.has_key('mediaPresentationDuration'):
            del MPD.attrib['mediaPresentationDuration']
        for child in MPD:
            if self.compare_tag(child.tag, 'Period'):
                child.set("start", "PT0S") # Set Period start to 0

    def makeLiveMultiplexedMpd(self, data, mediaData):
        self.makeLiveMpd(data)
        MPD = self.root
        audioAS = None
        videoAS = None
        period = None
        audioRep = None
        vidoeRep = None
        for child in MPD:
            if self.compare_tag(child.tag, 'Period'):
                period = child
                for grandChild in child:
                    if self.compare_tag(grandChild.tag, 'AdaptationSet'):
                        AS = AdaptationSet(grandChild)
                        AS.parse()
                        if AS.contentType == "audio":
                            audioAS = grandChild
                        elif AS.contentType == "video":
                            videoAS = grandChild

        for contentType, mData in mediaData.items():
            trackID = mData['trackID']
            cc = self.makeContentComponent(contentType, trackID)
            videoAS.insert(0, cc)

        del videoAS.attrib['contentType']
        audioRep = audioAS.find(self.mpd_namespace+"Representation")
        videoRep = videoAS.find(self.mpd_namespace+"Representation")
        videoRep.set("id", self.muxed_rep)
        try:
            audioCodec = audioRep.attrib["codecs"]
            videoCodec = videoRep.attrib["codecs"]
            combinedCodecs = "%s,%s" % (audioCodec, videoCodec)
            videoRep.set("codecs", combinedCodecs)
        except KeyError:
            print "Could not combine codecs"
        period.remove(audioAS)

    def makeContentComponent(self, contentType, trackID):
        "Create and insert a contentComponent element."
        elem = ElementTree.Element('%sContentComponent' % self.mpd_namespace)
        elem.set("id", str(trackID))
        elem.set("contentType", contentType)
        elem.tail = "\n"
        return elem

    def getCleanString(self, clean=True, targetMpdNameSpace=None):
        "Get a string of all XML cleaned (no ns0 namespace)"
        ofh = cStringIO.StringIO()
        self.tree.write(ofh, encoding="utf-8")#, default_namespace=NAMESPACE)
        value = ofh.getvalue()
        if clean:
            value =  value.replace("ns0:", "").replace("xmlns:ns0=", "xmlns=")
        if targetMpdNameSpace is not None:
            newStr = 'xmlns="%s"' % targetMpdNameSpace
            value = re.sub('xmlns="[^"]+"', newStr, value)
        xmlIntro = '<?xml version="1.0" encoding="utf-8"?>\n'
        return xmlIntro + value