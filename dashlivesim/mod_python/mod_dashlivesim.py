"""Make infinite live DASH stream from VoD content in live-profile format.

The content is synchronized with a wall-clock and only available according to the standard (can be overridden).

Make a VoD file look like infinite live DASH content. The timing is synchronized with wall clock.

The structure of the content is

CONTENT_ROOT:   [contentName]/[Manifest].mpd
                [contentName]/[Representation][init].mp4,
                [contentName]/[Representation][segNr].m4s,

VOD_CONF_DIR: [contentName].cfg

The corresponding links are then:
Manifest: http://[server]/[prefix]/[contentName]/[Manifest].mpd
Init: http://[server]/[prefix]/[contentName]/[Representation]/[init].mp4
Media: http://[server]/[prefix]/[contentName]/[Representation]/[liveSegNr].m4s

To control availabilityStartTime (AST) and availabilityEndTime (AET), one can add extra parts to the URL after prefix.

../[prefix]/start_ut/... will set the AST to the UNIX time ut (clipped to a multiple of duration)
../[prefix]/start_ut/dur_dt/... will set the AET as well (ut+dt)
../[prefix]/start_ut/dur_dt1/dur_dt2/ will set the AET and then update it 2*minimumUpdatePeriod before it is reached

One can also make the initialization segments available earlier than AST, by using init_ot (offset time in seconds).

More options are available in newer versions.
After [prefix], one can specify the following (mixed with the start_X and dur_X parameters:
tsbd_x - timeshiftBufferDepth = x seconds
mup_x - minimumUpdatePeriod = x seconds
init_x - initSegmentAvailabilityOffset makes the init segments available ahead of time by x seconds
all_1 - make all segments available (no timing checks)

For dynamic MPDs, one can also specify a modulo_x period in minutes.

This has the effect that the `availabilityStartTime` and the `mediaPresentationDuration`
vary in an `x`-minute periodic pattern.
The number `x` must be a divisor of 60, i.e. on of 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60.
For example, if `x=10`, the following happens (mpd = mediaPresentationDuration, mup=minimumUpdatePeriod):

    hh:00:00-hh:00:59          ast = hh:00:00 mpd = 120s mup = 30s
    hh:01:00-hh:02:59          ast = hh:00:00 mpd = 240s
    hh:03:00-hh:04:59          ast = hh:00:00 mpd = 360s
    hh:05:00-hh:08:59          ast = hh:00:00 mpd = 480s
    hh:09:00-hh:10:59          ast = hh:10:00 mpd = 120s

In other words:

    mup = 5% of the interval
    0-10% of the interval, the mpd=20% of interval
    10-30% of the interval, the mpd=40% of the interval
    30-50% of the interval, the mpd=60% of the interval
    50-90% of the interval, the mpd=80% of the interval
    90-100% of the interval, the mpd=20% of the next interval

Thus, beyond the media session getting longer and longer during the first 50% of the session,
from 80-90% of the interval, the MPD will describe an expired session, and
from 90-100% of the interval, the MPD will describe a future session.

A new option is multiple periods. These are specified using periods_n in before the content.
If n == 0, only one period is created but is offset from the AST to have a test case for that together with the
correct value of presentationTimeOffset set in the SegmentTemplate.

A related option is peroff_1 that moves the presentationTimeOffset into a SegmentBase entity on the Period level.


Init and media segments can also be multiplexed on the fly. This happens if they have a path like
X__Y/segment, in which case the two segments corresponding to X/segment and Y/segment are fetched
and multiplexed.
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

SERVER_VERSION = "1.0"

VOD_CONF_DIR = "/var/www/dash-live/vod_configs"
CONTENT_ROOT = "/var/www/dash-live/content"
SERVER_AGENT = "DASH-IF live DASH simulator %s" % SERVER_VERSION

from .dashlive_handler import dash_handler
from ..dashlib import dash_proxy

def handle_request(hostname, path_parts, args, now, req):
    "Fill in parameters and call the dash_proxy."
    return dash_proxy.handle_request(hostname, path_parts[1:], args, VOD_CONF_DIR, CONTENT_ROOT, now, req)

def handler(req):
    "This is the mod_python handler."
    return dash_handler(req, SERVER_AGENT, handle_request)

