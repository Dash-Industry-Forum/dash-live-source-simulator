"""ModuloPeriod for dynamic MPD DASH service.

The phases depends on now wrt to modulo minutes

    mup = 5% of the interval
    0-10% of the interval, the mpd=20% of interval
    10-30% of the interval, the mpd=40% of the interval
    30-50% of the interval, the mpd=60% of the interval
    50-90% of the interval, the mpd=80% of the interval
    90-100% of the interval, the mpd=20% of the next interval

    In the interval 80%-100%, no segments are available.
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

def quantize(number, step):
    "Quantize number to a multiple of step."
    return (int(number)//step)*step

class ModuloPeriod(object):
    "Provide the timing data needed for the MPD which has periods of available data."

    def __init__(self, modulo_minutes, now):
        self.mod_secs = 60*modulo_minutes
        self.now = now
        self.percent = self.calc_percent()
        self._availability_start_time = self.calc_availability_start_time()
        self._minimum_update_period = self.mod_secs/20
        self.publish_time = None
        self._media_presentation_duration = self.calc_media_pres_dur()
        self._availability_end_time = (self._availability_start_time
                                       + self._media_presentation_duration
                                       +self._minimum_update_period)

    @property
    def availability_start_time(self):
        "Get the AvailabilityStartTime for the MPD."
        return self._availability_start_time

    @property
    def minimum_update_period(self):
        "Get the MinimumUpdatePeriod for the MPD."
        return self._minimum_update_period

    @property
    def media_presentation_duration(self):
        "Get the MediaPresentationDuration for the MPD."
        return self._media_presentation_duration

    @property
    def availability_end_time(self):
        "Get the AvailabilityEndTime for the MPD."
        return self._availability_end_time

    def calc_percent(self):
        "Return the percent in the current period."
        seconds = self.now%self.mod_secs
        return (seconds*100)/self.mod_secs

    def calc_availability_start_time(self):
        "Get the availability startTime for this or coming period."
        period_start = quantize(self.now, self.mod_secs)
        if self.percent >= 90:
            period_start += self.mod_secs # Next period
        return period_start

    def calc_media_pres_dur(self):
        "Calculate the media presentation duration."
        ast = self._availability_start_time
        if self.percent < 10:
            mpd = 2*self.mod_secs/10
            pub_time = ast - self.mod_secs/10
        elif self.percent < 30:
            mpd = 4*self.mod_secs/10
            pub_time = ast + self.mod_secs/10
        elif self.percent < 50:
            mpd = 6*self.mod_secs/10
            pub_time = ast + self.mod_secs*3/10
        elif self.percent < 90:
            mpd = 8*self.mod_secs/10
            pub_time = ast + self.mod_secs*7/10
        else:
            mpd = 2*self.mod_secs/10 # This is in the next period
            pub_time = ast - self.mod_secs/10
        self.publish_time = pub_time
        return mpd

    def get_start_number(self, segment_duration):
        "Get startnumber assuming that segment number 0 is at epoch start."
        return self.availability_start_time/segment_duration

    def compare_with_last_segment(self, segment_number, segment_duration):
        """Return -1 if before last, 0 at last, and +1 after last.

        Set lmsg if the return value is 0."""
        segment_end_time = (segment_number+1)*segment_duration
        presentation_end_time = self.availability_start_time + self._media_presentation_duration
        return (segment_end_time - presentation_end_time)/segment_duration

    def calc_last_segment_number(self, segment_duration):
        "Calculate the last segmentNumber given segmentDuration and mediaPresentationDuration."
        presentation_end_time = self.availability_start_time + self._media_presentation_duration
        last_segment_number = presentation_end_time/segment_duration - 1
        return last_segment_number
