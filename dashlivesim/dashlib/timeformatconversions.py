"""Helper functions for time conversions."""

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

import time
import re
RE_DURATION = re.compile(r"PT((?P<hours>\d+)H)?((?P<minutes>\d+)M)?((?P<seconds>\d+)S)?")

class TimeFormatConversionError(Exception):
    "Generic timeformatconversion error."

def iso_duration_to_seconds(duration):
    "Convert a time duration in ISO 8601 format to seconds (only integer parts)."
    match_obj = RE_DURATION.match(duration)
    if not match_obj:
        raise TimeFormatConversionError("%s does not match a duration" % duration)
    secs = 0
    if match_obj.group("hours"):
        secs += int(match_obj.group("hours"))*3600
    if match_obj.group("minutes"):
        secs += int(match_obj.group("minutes"))*60
    if match_obj.group("seconds"):
        secs += int(match_obj.group("seconds"))
    return secs

def seconds_to_iso_duration(nr_secs):
    "Make interval string in format PT... from time in seconds."
    days, rest = divmod(nr_secs, 3600*24)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    period = "P"
    if days > 0:
        period += "%dD" % days
    period += "T"
    if hours > 0:
        period += "%dH" % hours
    if minutes > 0:
        period += "%dM" % minutes
    if seconds > 0 or period == "PT":
        period += "%dS" % seconds
    return period

def make_timestamp(time_in_s):
    "Return timestamp as string."
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time_in_s))
