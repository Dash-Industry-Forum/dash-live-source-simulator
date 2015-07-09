"WSGI Module for dash-live-source-simulator"

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

SERVER_VERSION = "1.1 + dev"

VOD_CONF_DIR = "/var/www/dash-live/vod_configs"
CONTENT_ROOT = "/var/www/dash-live/content"
SERVER_AGENT = "DASH-IF live DASH simulator %s" % SERVER_VERSION

import httplib
from os.path import splitext
from time import time
#pylint: disable=import-error
from dashlib import dash_proxy

# Helper for HTTP responses
#pylint: disable=dangerous-default-value
def reply(code, resp, body='', headers={}):
    "Create reply"
    status = str(code) + ' ' + httplib.responses[code]

    # Add default headers to all requests
    headers['Accept-Ranges'] = 'bytes'
    headers['Pragma'] = 'no-cache'
    headers['Cache-Control'] = 'no-cache'
    headers['Expires'] = '-1'
    headers['DASH-Live-Simulator'] = SERVER_AGENT
    headers['Access-Control-Allow-Headers'] = 'origin,range,accept-encoding,referer'
    headers['Access-Control-Allow-Methods'] = 'GET,HEAD,OPTIONS'
    headers['Access-Control-Allow-Origin'] = '*'
    headers['Access-Control-Expose-Headers'] = 'Server,range,Content-Length,Content-Range,Date'

    if body:
        headers['Content-Length'] = str(len(body))
        if not 'Content-Type' in headers:
            headers['Content-Type'] = 'text/plain'

    resp(status, headers.items())
    return [body]

#pylint: disable=too-many-branches
def application(environent, start_respose):
    "WSGI Entrypoint"
    # Setup variables
    print environent

    #pylint: disable=too-many-locals
    hostname = environent['HTTP_HOST']
    url = environent['REQUEST_URI']
    path_parts = url.split('/')
    ext = splitext(path_parts[-1])[1]
    args = None
    now = time()
    range_line = None
    if 'HTTP_RANGE' in environent:
        range_line = environent['HTTP_RANGE']

    # Print debug information
    #print hostname
    #print url
    #print path_parts
    #print ext
    #print range_line

    success = True
    mimetype = get_mime_type(ext)
    status = httplib.OK
    payload_in = None

    try:
        response = dash_proxy.handle_request(hostname, path_parts[1:], args, VOD_CONF_DIR, CONTENT_ROOT, now, None)
        if isinstance(response, basestring):
            payload_in = response
            if not payload_in:
                success = False
        else:
            if not response['ok']:
                success = False

            payload_in = response['pl']

    #pylint: disable=broad-except
    except Exception, exc:
        success = False
        print "mod_dash_handler request error: %s" % exc
        payload_in = "DASH Proxy Error: %s\n URL=%s" % (exc, url)


    if not success:
        if payload_in == "":
            print "dash_proxy error: No body!"
            payload_in = "Now found (now)"
        elif payload_in is None:
            print "dash_proxy: No content found"
            payload_in = "Not found (now)"

        status = httplib.NOT_FOUND
        mimetype = "text/plain"

    payload_out = payload_in

    # Setup response headers
    headers = {'Content-Type':mimetype}

    if status != httplib.NOT_FOUND:
        if range_line:
            payload_out, range_out = handle_byte_range(payload_in, range_line)
            if range_out != "": # OK
                headers['Content-Range'] = range_out
                status = httplib.PARTIAL_CONTENT
            else: # Bad range, drop it
                print "mod_dash_handler: Bad range %s" % (range_line)

    return reply(status, start_respose, payload_out, headers)

def get_mime_type(ext):
    "Get mime-type depending on extension."
    if ext == ".mpd":
        return "application/dash+xml"
    elif ext == ".m4s":
        return "video/iso.segment"
    elif ext == ".mp4":
        return "video/mp4"

    return "text/plain"


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

#
# Testing
#

def run_local_webserver(wrapper):
    "Local webserver function"
    host = '0.0.0.0'
    port = 8051
    print 'Waiting for reqeusts at "{0}:{1}"'.format(host, port)
    httpd = make_server(host, port, wrapper)
    httpd.serve_forever()

if __name__ == '__main__':
    from wsgiref.simple_server import make_server

    def application_wrapper(env, resp):
        "Wrapper around application, for local websever"
        # Apache strips the inital matching '/firstpathelement' before calling the handler.
        # Let's do the same thing to make the handler work with the test.
        env['PATH_INFO'] = env['PATH_INFO'].replace('/firstpathelement', '')
        return application(env, resp)

    run_local_webserver(application_wrapper)

