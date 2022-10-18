"""Analyze DASH content in live profile and extract parameters for VoD-config file for live source simulator.
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
from struct import pack
from dashlivesim.dashlib import configprocessor
from dashlivesim.dashlib import initsegmentfilter, mediasegmentfilter
from dashlivesim.vodanalyzer.mpdprocessor import MpdProcessor

DEFAULT_DASH_NAMESPACE = "urn:mpeg:dash:schema:mpd:2011"
MUX_TYPE_NONE = 0
MUX_TYPE_FRAGMENT = 1
MUX_TYPE_SAMPLES = 2

## Utility functions


def makeTimeStamp(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def makeDurationFromS(nrSeconds):
    return "PT%dS" % nrSeconds


class DashAnalyzerError(Exception):
    """Error in DashAnalyzer."""


class DashAnalyzer(object):

    def __init__(self, mpd_filepath, verbose=1):
        self.mpd_filepath = mpd_filepath
        path_parts = mpd_filepath.split('/')
        self.base_name = 'content'
        if len(path_parts) >= 2:
            self.base_name = path_parts[-2]
        self.config_filename = self.base_name + ".cfg"
        self.base_path = os.path.split(mpd_filepath)[0]
        self.verbose = verbose
        self.as_data = {} # List of adaptation sets (one for each media)
        self.muxedRep = None
        self.muxedPaths = {}
        self.mpdSegStartNr = -1
        self.segDuration = None
        self.firstSegmentInLoop = -1
        self.lastSegmentInLoop = -1
        self.nrSegmentsInLoop = -1
        self.mpdProcessor = MpdProcessor(self.mpd_filepath)
        self.loopTime = self.mpdProcessor.media_presentation_duration_in_s

    def analyze(self):
        self.initMedia()
        self.checkAndUpdateMediaData()
        self.write_config(self.config_filename)

    def initMedia(self):
        "Init media by analyzing the MPD and the media files."
        for adaptation_set in self.mpdProcessor.get_adaptation_sets():
            content_type = adaptation_set.content_type
            if content_type is None:
                print("No contentType for adaptation set")
                sys.exit(1)
            if content_type in self.as_data:
                raise DashAnalyzerError("Multiple adaptation sets for contentType " + content_type)
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
                print("%s trackID = %d" % (content_type, rep_data['trackID']))
                rep_data['relMediaPath'] = rep.get_media_path()
                rep_data['absMediaPath'] = os.path.join(self.base_path, rep.get_media_path())
                rep_data['default_sample_duration'] = \
                    init_filter.default_sample_duration

                self.getSegmentRange(rep_data)
                track_timescale = init_filter.track_timescale
                if 'track_timescale' not in as_data:
                    as_data['track_timescale'] = track_timescale
                elif track_timescale != as_data['track_timescale']:
                    raise DashAnalyzerError("Timescales not consistent between %s tracks" % content_type)
                if self.verbose:
                    print("%s data: " % content_type)
                    for (k, v) in rep_data.items():
                        print("  %s=%s" % (k, v))

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
        for i in range(1, len(numbers)):
            if numbers[i] != numbers[i-1] + 1:
                raise DashAnalyzerError("%s segment missing between %d and %d" % (rep_id, numbers[i-1], numbers[i]))
        print("Found %s segments %d - %d" % (rep_id, numbers[0], numbers[-1]))
        rep_data['firstNumber'] = numbers[0]
        rep_data['lastNumber'] = numbers[-1]

    def checkAndUpdateMediaData(self):
        """Check all segments for good values and return startTimes and total duration."""
        lastGoodSegments = []

        print("Checking all the media segment durations for deviations.")

        def writeSegTiming(ofh, firstSegmentInRepeat, firstStartTimeInRepeat, duration, repeatCount):
            data = pack(configprocessor.SEGTIMEFORMAT, firstSegmentInRepeat, repeatCount,
                        firstStartTimeInRepeat, duration)
            ofh.write(data)

        for content_type in self.as_data.keys():
            as_data = self.as_data[content_type]
            as_data['datFile'] = "%s_%s.dat" % (self.base_name, content_type)
            adaptation_set = as_data['as']
            print("Checking %s with timescale %d" % (content_type, as_data['track_timescale']))
            if self.segDuration is None:
                self.segDuration = adaptation_set.duration
            else:
                assert self.segDuration == adaptation_set.duration

            track_timescale = as_data['track_timescale']

            with open(as_data['datFile'], "wb") as ofh:
                for (rep_nr, rep_data) in enumerate(as_data['reps']):
                    rep_id = rep_data['id']
                    rep_data['endNr'] = None
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
                    repeatCount = -1
                    firstSegmentInRepeat = -1
                    firstStartTimeInRepeat = -1
                    lastDuration = 0
                    while (True):
                        segmentPath = rep_data['absMediaPath'] % segNr
                        if not os.path.exists(segmentPath):
                            if self.verbose:
                                print("\nLast good %s segment is %d, endTime=%.3fs, totalTime=%.3fs" % (
                                      rep_id, rep_data['endNr'], rep_data['endTime'],
                                      rep_data['endTime']-rep_data['startTime']))
                            break
                        msf = mediasegmentfilter.MediaSegmentFilter(
                            segmentPath, default_sample_duration = rep_data[
                                'default_sample_duration'])
                        msf.filter()
                        tfdt = msf.get_tfdt_value()
                        duration = msf.get_duration()
                        print("{0} {1:8d} {2}  {3}".format(content_type, segNr, tfdt, duration))
                        if duration == lastDuration:
                            repeatCount += 1
                        else:
                            if lastDuration != 0 and rep_nr == 0:
                                writeSegTiming(ofh, firstSegmentInRepeat,
                                               firstStartTimeInRepeat,
                                               lastDuration, repeatCount)
                            repeatCount = 0
                            lastDuration = duration
                            firstSegmentInRepeat = segNr
                            firstStartTimeInRepeat = tfdt
                        if rep_data['startTick'] is None:
                            rep_data['startTick'] = tfdt
                            rep_data['startTime'] = rep_data['startTick']/float(track_timescale)
                            print("First %s segment is %d starting at time %.3fs" % (rep_id, segNr,
                                                                                     rep_data['startTime']))
                        # Check that there is not too much drift. We want to end with at most maxDiffInTicks
                        endTick = tfdt + duration
                        idealTicks = (segNr - rep_data['firstNumber'] + 1)*segTicks + rep_data['startTick']
                        absDiffInTicks = abs(idealTicks - endTick)
                        if absDiffInTicks < maxDiffInTicks:
                            # This is a good wrap point
                            rep_data['endTick'] = tfdt + duration
                            rep_data['endTime'] = rep_data['endTick']/float(track_timescale)
                            rep_data['endNr'] = segNr
                        else:
                            raise DashAnalyzerError("Too much drift in the duration of the segments")
                        segNr += 1
                        if self.verbose:
                            sys.stdout.write(".")
                    if rep_nr == 0:
                        writeSegTiming(ofh, firstSegmentInRepeat, firstStartTimeInRepeat, duration, repeatCount)
                        lastGoodSegments.append(rep_data['endNr'])
                        as_data['totalTicks'] = rep_data['endTick'] - rep_data['startTick']
        self.lastSegmentInLoop = min(lastGoodSegments)
        self.nrSegmentsInLoop = self.lastSegmentInLoop-self.firstSegmentInLoop+1
        self.loopTime = self.nrSegmentsInLoop*self.segDuration
        if self.verbose:
            print("")
        print("Will loop segments %d-%d with loop time %ds" % (self.firstSegmentInLoop, self.lastSegmentInLoop,
                                                               self.loopTime))

    def write_config(self, config_file):
        """Write a config file for the analyzed content, that can then be used to serve it efficiently."""
        cfg_data = {'version' : '1.1', 'first_segment_in_loop' : self.firstSegmentInLoop,
                    'nr_segments_in_loop' : self.nrSegmentsInLoop, 'segment_duration_s' : self.segDuration}
        media_data = {}
        for content_type in ('video', 'audio'):
            if content_type in self.as_data:
                mdata = self.as_data[content_type]
                media_data[content_type] = {'representations' : [rep['id'] for rep in mdata['reps']],
                                            'timescale' : mdata['track_timescale'],
                                            'totalDuration' : mdata['totalTicks'],
                                            'datFile' : mdata['datFile']}
        cfg_data['media_data'] = media_data
        vod_cfg = configprocessor.VodConfig()
        vod_cfg.write_config(config_file, cfg_data)

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


def main():
    from optparse import OptionParser
    verbose = 0
    usage = "usage: %prog [options] mpdPath"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true")

    (options, args) = parser.parse_args()
    if options.verbose:
        verbose = 1
    if len(args) != 1:
        parser.error("incorrect number of arguments")
    mpdFile = args[0]
    dashAnalyzer = DashAnalyzer(mpdFile, verbose)
    dashAnalyzer.analyze()


if __name__ == "__main__":
    main()
