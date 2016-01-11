"""Analyze DASH content in live profile and insert cc.
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

import sys
import os
import time
import re
import struct
from ..dashlib import configprocessor

from ..dashlib import initsegmentfilter, mediasegmentfilter
from ..dashlib.mp4filter import MP4Filter
from ..dashlib.structops import uint32_to_str, str_to_uint32, uint64_to_str
from .mpdprocessor import MpdProcessor

DEFAULT_DASH_NAMESPACE = "urn:mpeg:dash:schema:mpd:2011"
MUX_TYPE_NONE = 0
MUX_TYPE_FRAGMENT = 1
MUX_TYPE_SAMPLES = 2


class CCInsertFilter(MP4Filter):
    def __init__(self, segmentFile, sccData, timeScale, tfdt):
        MP4Filter.__init__(self, segmentFile)
        self.top_level_boxes_to_parse = ["styp", "sidx", "moof", "mdat"]
        self.composite_boxes_to_parse = ["moof", "traf"]
        self.sccData = sccData
        self.timeScale = timeScale
        self.tfdt = tfdt

        self.trun_offset = 0

        self.sccMap = []

    def process_trun(self, data):
        output = data[:16]

        flags = str_to_uint32(data[8:12]) & 0xffffff
        sample_count = str_to_uint32(data[12:16])
        pos = 16
        data_offset_present = False

        if flags & 0x1: # Data offset present
            data_offset_present = True
            self.trun_offset = str_to_uint32(data[16:20])
            output += uint32_to_str(self.trun_offset)
            pos += 4
        if flags & 0x4:
            pos += 4 # First sample flags present

        sample_duration_present = flags & 0x100
        sample_size_present = flags & 0x200
        sample_flags_present = flags & 0x400
        sample_comp_time_present = flags & 0x800
        sample_time_tfdt = self.tfdt

        orig_sample_pos = 0

        for i in range(sample_count):
            duration = 0
            size = 0
            flags = 0
            comp_time = 0

            if sample_duration_present:
                duration = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_size_present:
                size = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_flags_present:
                flags = str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_comp_time_present:
                comp_time = str_to_uint32(data[pos:pos+4])
                pos += 4

            start_time = 0
            if i == 0:
                start_time = (sample_time_tfdt) / float(self.timeScale)
            else:
                start_time = (sample_time_tfdt + comp_time) / float(self.timeScale)

            end_time = (sample_time_tfdt + comp_time + duration) / float(self.timeScale)
            #start_time = (sample_time_tfdt) / float(self.timeScale)
            #end_time = (sample_time_tfdt + duration) / float(self.timeScale)
    
            #print "startTime:",start_time,"(",comp_time, ")",", endTime:",end_time

            sccSamples = self.getSCCData(start_time, end_time)
            orig_sample_pos += size 
            if len(sccSamples):
                #print " ",i, "SampleTime: " + str((sample_time_tfdt + comp_time) / float(self.timeScale)), "num samples to add: " , len(sccSamples)
                print " ",i, "SampleTime: " + str((sample_time_tfdt) / float(self.timeScale)), "num samples to add: " , len(sccSamples)
                sccGeneratedData = self.generate_data(sccSamples)
                self.sccMap.append({ 'pos':orig_sample_pos, 'scc':sccGeneratedData, 'len': len(sccGeneratedData) })
                #print size, size+len(sccGeneratedData)
                size += len(sccGeneratedData)

            if sample_duration_present:
                output += uint32_to_str(duration)
            if sample_size_present:
                output += uint32_to_str(size)
            if sample_flags_present:
                output += uint32_to_str(flags)
            if sample_comp_time_present:
                output += uint32_to_str(comp_time)

            sample_time_tfdt += duration

        #print data == output

        #print self.sccMap

        return output

    def generate_data(self, sccData):

        output = ""

        for data in sccData:
            cea608Bytes = data['cea608']
            payloadSize = (1 + 2 + 4 + 1) + (1 + 1 + (len(cea608Bytes) * 3)) + 1
            nalUnit = [ 0x66, 0x04, payloadSize, 0xb5, 0x00, 0x31, ord('G'), ord('A'), ord('9'), ord('4'), 0x03, 0xc0 + len(cea608Bytes), 0xff ]

            print len(cea608Bytes), payloadSize

            for i in cea608Bytes:
                cc_byte1 = (int(i, 16) & 0xff00) >> 8 
                cc_byte2 = (int(i, 16) & 0xff) 

                # Field 1
                #nalUnit.append(0xfc)
                # Field 2
                nalUnit.append(0xfd)

                nalUnit.append(cc_byte1)
                nalUnit.append(cc_byte2)

            nalUnit.append(0xff)

            #print nalUnit
            output += struct.pack('>I', len(nalUnit))
            nalUnitStr = "".join(chr(i) for i in nalUnit)
            output += nalUnitStr

        #print [b for b in output]

        return output

    def process_mdat(self, data):
        #print "processing mdat"
        pos = 0
        offset = self.trun_offset - (self.mdat_start - self.moof_start)

        output = data[pos:offset]

        pos = offset

        totalBytesAdded = 0

        for i in self.sccMap:
            size = int(i['pos'])
            sccData = i['scc']
            totalBytesAdded += len(sccData)
            output += data[pos:(offset+size)]
            output += sccData
            pos = (offset + size)

        output += data[pos:]

        #print "totalBytesAdded:", totalBytesAdded
        #print output == data

        #print len(data), len(output)

        return struct.pack('>I', len(output)) + output[4:]

    def getSCCData(self, start_time, end_time):
        result = []
        for i in self.sccData:
            if i['start_time'] >= start_time and i['start_time'] < end_time:
                result.append(i)
        return result


## Utility functions

def makeTimeStamp(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))

def makeDurationFromS(nrSeconds):
    return "PT%dS" % nrSeconds

class CCInserterError(Exception):
    "Error in CCInserter."


class CCInserter(object):

    def __init__(self, mpd_filepath, scc_filepath, out_path, verbose=1):
        self.mpd_filepath = mpd_filepath
        self.scc_filepath = scc_filepath
        self.out_path = out_path
        path_parts = mpd_filepath.split('/')
        #print path_parts
        if len(path_parts) >= 2:
            self.config_filename = '%s.cfg' % path_parts[-2]
        else:
            self.config_filename = 'content.cfg'
        self.base_path = os.path.split(mpd_filepath)[0]
        self.verbose = verbose
        self.as_data = {} # List of adaptation sets (one for each media)
        self.muxedRep = None
        self.muxedPaths = {}
        self.mpdSegStartNr = -1
        self.sccData = None
        self.segDuration = None
        self.firstSegmentInLoop = -1
        self.lastSegmentInLoop = -1
        self.nrSegmentsInLoop = -1
        self.mpdProcessor = MpdProcessor(self.mpd_filepath)
        self.loopTime = self.mpdProcessor.media_presentation_duration_in_s

    def analyze(self):
        self.initMedia()

        self.checkAndUpdateMediaData()

    def initMedia(self):
        "Init media by analyzing the MPD and the media files."
        for adaptation_set in self.mpdProcessor.get_adaptation_sets():
            content_type = adaptation_set.content_type
            if content_type is None:
                print "No contentType for adaptation set"
                sys.exit(1)
            if self.as_data.has_key(content_type):
                raise CCInserterError("Multiple adaptation sets for contentType " + content_type)
            as_data = {'as' : adaptation_set, 'reps' : []}
            as_data['presentationDurationInS'] = self.mpdProcessor.media_presentation_duration_in_s
            self.as_data[content_type] = as_data
            for rep in adaptation_set.representations:
                rep_data = {'representation' : rep, 'id' : rep.rep_id}
                as_data['reps'].append(rep_data)
                initPath = rep.initialization_path
                rep_data['relInitPath'] = initPath
                rep_data['absInitPath'] = os.path.join(self.base_path, initPath)
                init_filter = initsegmentfilter.InitFilter(rep_data['absInitPath'])
                init_filter.filter()
                rep_data['trackID'] = init_filter.track_id
                print "%s trackID = %d" % (content_type, rep_data['trackID'])
                rep_data['relMediaPath'] = rep.get_media_path()
                rep_data['absMediaPath'] = os.path.join(self.base_path, rep.get_media_path())

                self.getSegmentRange(rep_data)
                track_timescale = init_filter.track_timescale
                if not as_data.has_key('track_timescale'):
                    as_data['track_timescale'] = track_timescale
                elif track_timescale != as_data['track_timescale']:
                    raise CCInserterError("Timescales not consistent between %s tracks" % content_type)
                #if self.verbose:
                #    print "%s data: " % content_type
                #    for (k,v) in rep_data.items():
                #        print "  %s=%s" % (k, v)

    def getSegmentRange(self, rep_data):
        "Search the directory for the first and last segment and set firstNumber and lastNumber for this MediaType."
        rep_id = rep_data['id']
        mediaDir, mediaName = os.path.split(rep_data['absMediaPath'])
        mediaRegexp = mediaName.replace("%d", "(\d+)").replace(".", "\.")
        mediaReg = re.compile(mediaRegexp)
        files = os.listdir(mediaDir)
        numbers = []
        for f in files:
            matchObj = mediaReg.match(f)
            if matchObj:
                number = int(matchObj.groups(1)[0])
                numbers.append(number)
        numbers.sort()
        for i in range(1,len(numbers)):
            if numbers[i] != numbers[i-1] + 1:
                raise CCInserterError("%s segment missing between %d and %d" % rep_id, numbers[i], numbers[i-1])
        print "Found %s segments %d - %d" % (rep_id, numbers[0] , numbers[-1])
        rep_data['firstNumber'] = numbers[0]
        rep_data['lastNumber'] = numbers[-1]

    def getSCCData(self, start_time, end_time):
        result = []
        for i in self.sccData:
            if i['start_time'] >= start_time and i['start_time'] < end_time:
                result.append(i)
        return result

    def checkAndUpdateMediaData(self):
        """Check all segments for good values and return startTimes and total duration."""
        #lastGoodSegments = []
        segDuration = None
        print "Checking all the media segment durations for deviations."

        for content_type in self.as_data.keys():
            if content_type == "video":
                as_data = self.as_data[content_type]
                adaptation_set = as_data['as']
                print "Checking %s with timescale %d" % (content_type, as_data['track_timescale'])
                if self.segDuration is None:
                    segDuration = adaptation_set.duration
                    self.segDuration = segDuration
                else:
                    assert self.segDuration == adaptation_set.duration

                track_timescale = as_data['track_timescale']

                # Parse SCC file
                sccParser = SCCParser(self.scc_filepath, track_timescale)
                sccParser.parse()
                self.sccData = sccParser.result


                for rep_data in as_data['reps']:
                    rep_id = rep_data['id']
                    rep_data['endNr'] =  None
                    rep_data['startTick'] = None
                    rep_data['endTick'] = None
                    if self.firstSegmentInLoop >= 0:
                        assert rep_data['firstNumber'] == self.firstSegmentInLoop
                    else:
                        self.firstSegmentInLoop = rep_data['firstNumber']
                    if self.mpdSegStartNr >= 0:
                        assert adaptation_set.start_number == self.mpdSegStartNr
                    else:
                        self.mpdSegStartNr = adaptation_set.start_number
                    segTicks = self.segDuration*track_timescale
                    maxDiffInTicks = int(track_timescale*0.1) # Max 100ms
                    segNr = rep_data['firstNumber']
                    while (True):
                        segmentPath = rep_data['absMediaPath'] % segNr
                        if not os.path.exists(segmentPath):
                            if self.verbose:
                                print "\nLast good %s segment is %d, endTime=%.3fs, totalTime=%.3fs" % (
                                    rep_id, rep_data['endNr'], rep_data['endTime'],
                                    rep_data['endTime']-rep_data['startTime'])
                            break
                        #print "Parsing segment: " + segmentPath
                        msf = mediasegmentfilter.MediaSegmentFilter(segmentPath)
                        msf.filter()
                        tfdt = msf.get_tfdt_value()
                        duration = msf.get_duration()

                        start_time = tfdt / float(track_timescale)
                        end_time = start_time + (duration / float(track_timescale))
                        print "Segment " + str(segNr) + ", start:" + str(start_time) + ", end:" + str(end_time)
                        sccDataForSegment = self.getSCCData(start_time, end_time)
                        if len(sccDataForSegment):
                            #for i in sccDataForSegment:
                            #    print " ",i['start_time'], 'bytes:', len(i['cea608'])

                            # Insert data into segment
                            ccFilter = CCInsertFilter(segmentPath, sccDataForSegment, track_timescale, tfdt)
                            output = ccFilter.filter()

                            print os.path.join(self.out_path, "%d.m4s"%segNr)
                            with open(os.path.join(self.out_path, "%d.m4s"%segNr), "wb") as f:
                                f.write(output)
                                f.close()

                        if rep_data['startTick'] is None:
                            rep_data['startTick'] = tfdt
                            rep_data['startTime'] = rep_data['startTick']/float(track_timescale)
                            #print "First %s segment is %d starting at time %.3fs" % (rep_id, segNr,
                            #                                                         rep_data['startTime'])
                        # Check that there is not too much drift. We want to end with at most maxDiffInTicks
                        endTick = tfdt + duration
                        idealTicks = (segNr - rep_data['firstNumber'] + 1)*segTicks + rep_data['startTick']
                        absDiffInTicks = abs(idealTicks - endTick)
                        if absDiffInTicks < maxDiffInTicks:
                            # This is a good wrap point
                            rep_data['endTick'] = tfdt + duration
                            rep_data['endTime'] = rep_data['endTick']/float(track_timescale)
                            rep_data['endNr'] = segNr

                        segNr += 1
                        if self.verbose:
                            sys.stdout.write(".")
                    #lastGoodSegments.append(rep_data['endNr'])
        #self.lastSegmentInLoop = min(lastGoodSegments)
        #self.nrSegmentsInLoop = self.lastSegmentInLoop-self.firstSegmentInLoop+1
        #self.loopTime = self.nrSegmentsInLoop*self.segDuration
        #if self.verbose:
        #    print ""
        #print "Will loop segments %d-%d with loop time %ds" % (self.firstSegmentInLoop, self.lastSegmentInLoop, self.loopTime)

    #def write_config(self, config_file):
    #    "Write a config file for the analyzed content, that can then be used to serve it efficiently."
    #    cfg_data = {'version' : '1.0', 'first_segment_in_loop' : self.firstSegmentInLoop,
    #                'nr_segments_in_loop' : self.nrSegmentsInLoop, 'segment_duration_s' : self.segDuration}
    #    media_data = {}
    #    for content_type in ('video', 'audio'):
    #        if self.as_data.has_key(content_type):
    #            mdata = self.as_data[content_type]
    #            media_data[content_type] = {'representations' : [rep['id'] for rep in mdata['reps']],
    #                                        'timescale' : mdata['track_timescale']}
    #    cfg_data['media_data'] = media_data
    #    print cfg_data
    #    vod_cfg = configprocessor.VodConfig()
    #    vod_cfg.write_config(config_file, cfg_data)


    def processMpd(self):
        """Process the MPD and make an appropriate live version."""
        mpdData = {"availabilityStartTime" :makeTimeStamp(self.mpdAvailabilityStartTIme),
                   "timeShiftBufferDepth" : makeDurationFromS(self.timeShiftBufferDepthInS),
                   "minimumUpdatePeriod" : "PT30M"}
        if not self.muxType != MUX_TYPE_NONE:
            self.mpdProcessor.makeLiveMpd(mpdData)
        else:
            self.mpdProcessor.makeLiveMultiplexedMpd(mpdData, self.media_data)
            self.muxedRep = self.mpdProcessor.getMuxedRep()
        targetMpdNamespace = None
        if self.fixNamespace:
            targetMpdNamespace = DEFAULT_DASH_NAMESPACE
        self.mpd = self.mpdProcessor.getCleanString(True, targetMpdNamespace)

class SCCParser():
    def __init__(self, sccPath, timescale):
        self.sccPath = sccPath
        self.timescale = timescale
        self.result = []

    def parse(self):
        with open(self.sccPath, 'r') as f:
            lines = f.readlines()
            oldObject = None
            start_time = 0
            for line in lines:
                line = line.rstrip()
                if len(line) > 0 and line.find(':') > 0:
                    parts = line.split(' ')
                    start_time = self.convertTime(parts[0])
                    chunkedData = list(self.chunks(parts[1:], 31))
                    for cd in chunkedData:
                        data = { 'start_time': start_time, 'cea608':cd }
                        self.result.append(data)

    def convertTime(self, t):
        return self.transformTimeToMS(self.transformTime(t)) / 1000.0

    def transformTime(self, time):
        "Transform from hh:mm:ss:fn or pts to hh:mm:ss:ms."
        try:
            parts = time.split(":")
            frameNr = int(parts[-1])
            ms = min(int(frameNr*1000/29.97), 999)
            newtime = "%s.%03d" % (":".join(parts[:-1]), ms)
        except AttributeError: # pts time
            ss = time/90000
            ms = int((time % 90000)/90.0)
            hh = ss/3600
            mm = ss/60
            ss -= hh*3600 + mm*60
            newtime = "%02d:%02d:%02d.%03d" % (hh, mm, ss, ms)
        return newtime

    def transformTimeToMS(self, time):
        "Transform from hh:mm:ss.ms to sss.sss"
        newtime = 0
        timems = time.split(".")
        parts = timems[0].split(":")

        newtime += int(parts[0]) * 3600000
        newtime += int(parts[1]) * 60000
        newtime += int(parts[2]) * 1000
        newtime += int(timems[1])
        return newtime

    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in xrange(0, len(l), n):
            yield l[i:i+n]
                    
                    


def main():
    from optparse import OptionParser
    verbose = 0
    usage = "usage: %prog [options] mpdPath sccPath outPath"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true")

    (options, args) = parser.parse_args()
    if options.verbose:
        verbose = 1
    if len(args) != 3:
        parser.error("incorrect number of arguments")

    mpdFile = args[0]
    sccFile = args[1]
    outPath = args[2]

    ccInserter = CCInserter(mpdFile, sccFile, outPath, verbose)
    ccInserter.analyze()


if __name__ == "__main__":
    main()
