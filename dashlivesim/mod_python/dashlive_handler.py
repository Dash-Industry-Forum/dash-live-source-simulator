"""Handler of DASH request for mod_dash_proxy and mod_base_proxy.
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

HTTP_PARTIAL_CONTENT = 206

from os.path import splitext
from time import time
import traceback

try:
    from mod_python import apache
    import cgi
except ImportError:
    pass

MAX_SESSION_LENGTH = 3600  # If non-zero,  limit sessions via redirect

def respond(req, status, headers, body, server_agent):
    req.status = status
    if headers:
        for k,v in headers.items():
            req.headers_out[k] = v
    set_out_headers(req, server_agent)
    req.headers_out['Content-Length'] = "%d" % len(body)
    req.write(body)
    return apache.OK


#pylint: disable=too-many-branches
def dash_handler(req, server_agent, request_handler):
    "This is the mod_python handler."

    url = req.parsed_uri[apache.URI_PATH]
    path_parts = url.split("/")
    ext = splitext(path_parts[-1])[1]
    set_mime_type(req, ext)

    range_line = req.headers_in.get('range')

    now = time()

    if MAX_SESSION_LENGTH:  # Redirect and do limit sessions in time
        # Check if there is a sts_xxx parameter.
        start_time = None
        for part in path_parts:
            if part.startswith('sts_'):
                try:
                    start_time = int(part[4:])
                except:
                    pass

        if ext == ".mpd" and start_time is None:
            new_url = 'https://' if req.is_https() else 'http://'
            start_part = "sts_%d" % int(now)
            path_parts = path_parts[:2] + [start_part] + path_parts[2:]
            new_url += req.hostname + '/'.join(path_parts)
            if req.args:
                new_url += '?' + req.args
            return respond(req, apache.HTTP_MOVED_TEMPORARILY,
                           {'Location': new_url}, "", server_agent)
        elif start_time is None:
            return respond(req, apache.HTTP_NOT_FOUND, {},
                           'No start_time in non-manifest request',
                           server_agent)
        else:
            if now > start_time + MAX_SESSION_LENGTH:
                return respond(req, apache.HTTP_GONE, {},
                               "Maximum session length %ds passed" %
                                MAX_SESSION_LENGTH, server_agent)
            elif start_time > now + 5:  # Give some margin
                return respond(req, apache.HTTP_FORBIDDEN, {},
                               'start_time is in future', server_agent)

    success = True
    if req.args:
        args = cgi.parse_qs(req.args)
        req.log_error("mod_dash_handler: %s" % args.__str__())
    else:
        args = {}
    try:
        response = request_handler(req.hostname, path_parts, args, now, req)
        if isinstance(response, basestring):
            payload_in = response
            if not payload_in:
                success = False
        else:
            if not response["ok"]:
                success = False
            payload_in = response["pl"]
    #pylint: disable=broad-except
    except Exception, exc:
        success = False
        req.log_error("mod_dash_handler request error: %s" % exc)
        payload_in = "DASH Proxy Error: %s\n URL=%s" % (exc, url)
        req.content_type = "text/plain"
        req.status = apache.HTTP_NOT_FOUND
        traceback.print_exc()

    set_out_headers(req, server_agent)

    if not success:
        if payload_in == "":
            req.log_error("dash_proxy error: No body!")
            payload_in = "Not found (now)"
        elif payload_in is None:
            req.log_error("dash_proxy: No content found")
            payload_in = "Not found (now)"
        req.status = apache.HTTP_NOT_FOUND
        req.content_type = "text/plain"

    payload_out = payload_in

    if req.status != apache.HTTP_NOT_FOUND:
        if range_line:
            payload_out, range_out = handle_byte_range(payload_in, range_line)
            if range_out != "": # OK
                req.headers_out['Content-Range'] = range_out
                req.status = HTTP_PARTIAL_CONTENT
            else: # Bad range, drop it.
                req.log_error("mod_dash_handler: Bad range %s" % (range_line))

    req.headers_out['Content-Length'] = "%d" % len(payload_out)
    req.write(payload_out)
    return apache.OK

def set_mime_type(req, ext):
    "Set mime-type depending on extension."
    req.content_type = "text/plain"
    if ext == ".mpd":
        req.content_type = "application/dash+xml"
    elif ext == ".m4s":
        req.content_type = "video/iso.segment"
    elif ext == ".mp4":
        req.content_type = "video/mp4"

def set_out_headers(req, server_agent):
    "Set the response headers."
    req.headers_out['Accept-Ranges'] = 'bytes'
    req.headers_out['Pragma'] = 'no-cache'
    req.headers_out['Cache-Control'] = 'no-cache'
    req.headers_out['Expires'] = '-1'
    req.headers_out['DASH-Live-Simulator'] = server_agent
    req.headers_out['Access-Control-Allow-Headers'] = 'origin,range,accept-encoding,referer'
    req.headers_out['Access-Control-Allow-Methods'] = 'GET,HEAD,OPTIONS'
    req.headers_out['Access-Control-Allow-Origin'] = '*'
    req.headers_out['Access-Control-Expose-Headers'] = 'Server,range,Content-Length,Content-Range,Date'

def handle_byte_range(payload, range_line):
    """Handle byte range and return data and range-header value.

    If range is strange, return empty string."""
    range_parts = range_line.split("=")[-1]
    ranges = range_parts.split(",")
    if len(ranges) > 1:
        return (payload, None)
    length = len(payload)
    range_interval = ranges[0]
    range_start, range_end = range_interval.split("-")
    bad_range = False
    if range_start == "" and range_end != "":
        # This is the rangeStart lasts bytes
        range_start = length - int(range_end)
        range_end = length -1
    elif range_start != "":
        range_start = int(range_start)
        if range_end != "":
            range_end = min(int(range_end), length-1)
        else:
            range_end = length-1
    else:
        bad_range = True
    if range_end < range_start:
        bad_range = True
    if bad_range:
        return (payload, "")
    ranged_payload = payload[range_start: range_end+1]
    range_response = "bytes %d-%d/%d" % (range_start, range_end, len(payload))
    return (ranged_payload, range_response)
