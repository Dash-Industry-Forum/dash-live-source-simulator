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

# Note that VOD_CONF_DIR and CONTENT_ROOT directories must be set in environment
# For Apache mod_wsgi, this is done using setEnv

import traceback
from os.path import splitext
from urllib.parse import urlparse, parse_qs
from time import time, sleep

from dashlivesim.dashlib import dash_proxy, sessionid, mpd_proxy
from dashlivesim.dashlib.dash_proxy import ChunkedSegment
from dashlivesim import SERVER_AGENT

MAX_SESSION_LENGTH = 3600  # If non-zero,  limit sessions via redirect

# Helper for HTTP responses
# pylint: disable=dangerous-default-value

status_string = {
    200: 'OK',
    206: 'Partial Content',
    302: 'Found',
    404: 'Not Found',
    410: 'Gone'
    }


def start_reply(status_code, response, length=-1, headers={}):
    "Start reply by writing headers reply."
    status = "%d %s" % (status_code, status_string[status_code])

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

    if length >= 0:
        headers['Content-Length'] = str(length)

    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'text/plain'

    response(status, list(headers.items()))


def full_reply(status_code, response, body=b"", headers={}):
    "A full reply including body and content-length."
    start_reply(status_code, response, len(body), headers)
    return [body]


# pylint: disable=too-many-branches, too-many-locals
def application(environment, start_response):
    "WSGI Entrypoint"

    hostname = environment['HTTP_HOST']
    url = urlparse(environment['REQUEST_URI'])
    vod_conf_dir = environment['VOD_CONF_DIR']
    content_root = environment['CONTENT_ROOT']
    is_https = environment.get('wsgi.url_scheme', False) and environment['wsgi.url_scheme'] == 'https'
    path_parts = url.path.split('/')
    ext = splitext(path_parts[-1])[1]
    query = url.query if url.query else environment.get('QUERY_STRING', '')
    args = parse_qs(query)

    now = time()

    body = None

    if MAX_SESSION_LENGTH:  # Redirect and do limit sessions in time
        # Check if there is a sts_xxx parameter.
        start_time = None
        for part in path_parts:
            if part.startswith('sts_'):
                try:
                    start_time = int(part[4:])
                except Exception:
                    pass

        if ext == ".mpd" and start_time is None:
            new_url = 'https://' if is_https else 'http://'
            start_part = "sts_%d" % int(now)
            session_id_path = "sid_%s" % sessionid.generate_session_id()
            path_parts = (path_parts[:2] + [start_part] +
                          [session_id_path] + path_parts[2:])
            new_url += hostname + '/'.join(path_parts)
            if query:
                new_url += '?' + query
            body = b""
            start_reply(302, start_response, len(body), {'Location': new_url})
            body = b""
        elif start_time is None:
            body = b'No start_time in non-manifest request'
            start_reply(404, start_response, len(body))
        elif start_time == 314:
            pass  # Magic number hack to get through the system
        elif now > start_time + MAX_SESSION_LENGTH:
            msg = "Maximum session length %ds passed" % MAX_SESSION_LENGTH
            body = msg.encode('utf-8')
            start_reply(410, start_response, len(body))
        elif start_time > now + 5:  # Give some margin
            body = b'start_time is in future'
            start_reply(404, start_response, len(body))

    if body is not None:
        yield body
    else:
        range_line = None
        if 'HTTP_RANGE' in environment:
            range_line = environment['HTTP_RANGE']

        success = True
        mimetype = get_mime_type(ext)
        status_code = 200
        payload_in = None
        chunk = chunk_out = False

        try:
            dashProv = dash_proxy.createProvider(hostname, path_parts[1:], args,
                                                 vod_conf_dir, content_root, now,
                                                 None, is_https)
            cfg = dashProv.cfg
            ext = cfg.ext
            if ext == ".m4s":
                if cfg.chunk_duration_in_s is not None and cfg.chunk_duration_in_s > 0:
                    chunk = True
                response = dash_proxy.get_media(dashProv, chunk)
                if isinstance(response, ChunkedSegment):
                    chunk_out = True
            elif ext in (".mpd", ".period"):
                response = mpd_proxy.get_mpd(dashProv)
            elif ext == ".mp4":
                response = dash_proxy.get_init(dashProv)
            elif ext == ".jpg":
                response = dash_proxy.get_media(dashProv)
            if isinstance(response, bytes) or isinstance(response, str) or chunk_out:
                if isinstance(response, str):
                    response = response.encode('utf-8')
                payload_in = response
                if not payload_in:
                    success = False
            else:
                if not response['ok']:
                    success = False
                payload_in = response['pl']

        # pylint: disable=broad-except
        except Exception as exc:
            success = False
            traceback.print_exc()
            payload_in = "DASH Proxy Error: {0}\n URL={1}".format(exc, url)

        if not success:
            if not payload_in:
                payload_in = "Not found (now)"

            status_code = 404
            mimetype = "text/plain"

        if isinstance(payload_in, str):
            payload_in = payload_in.encode('utf-8')
        payload_out = payload_in

        # Setup response headers
        headers = {'Content-Type': mimetype}

        if status_code != 404:
            if range_line and not chunk_out:
                payload_out, range_out = handle_byte_range(payload_in, range_line)
                if range_out != "":  # OK
                    headers['Content-Range'] = range_out
                    status_code = 206
                else:  # Bad range, drop it
                    print("mod_dash_handler: Bad range {0}".format(range_line))

        if not chunk_out:
            start_reply(status_code, start_response, len(payload_out), headers)
            yield payload_out
        else:
            start_reply(status_code, start_response, -1, headers)
            now_float = now
            seg_start = payload_out.seg_start
            chunk_dur = cfg.chunk_duration_in_s
            margin = 0.1  # Make available 100ms before the formal time
            for i, chunk in enumerate(payload_out.chunks, start=1):
                now_float = time()  # Update time
                chunk_availability_time = seg_start + i * chunk_dur - margin
                time_until_available = chunk_availability_time - now_float
                # print("%d time_until_available %.3f" % (i, time_until_available))
                if time_until_available > 0:
                    # print("Sleeping for %.3f" % time_until_available)
                    sleep(time_until_available)
                yield chunk


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
        range_end = length - 1
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


def main():
    "Local stand-alone wsgi server for testing."
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("-d", "--config_dir", dest="vod_conf_dir", type=str,
                        help="configuration root directory", required=True)
    parser.add_argument("-c", "--content_dir", dest="content_dir", type=str,
                        help="content root directory", required=True)
    parser.add_argument("--host", dest="host", type=str, help="IPv4 host", default="0.0.0.0")
    parser.add_argument("--port", dest="port", type=int, help="IPv4 port", default=8059)
    args = parser.parse_args()

    def application_wrapper(env, resp):
        "Wrapper around application for local webserver."
        env['REQUEST_URI'] = env['PATH_INFO']  # Set REQUEST_URI from PATH_INFO
        env['VOD_CONF_DIR'] = args.vod_conf_dir
        env['CONTENT_ROOT'] = args.content_dir
        return application(env, resp)

    def run_local_webserver(wrapper, host, port):
        "Local webserver."
        from wsgiref.simple_server import make_server
        print('Waiting for requests at "{0}:{1}"'.format(host, port))
        httpd = make_server(host, port, wrapper)
        httpd.serve_forever()

    run_local_webserver(application_wrapper, args.host, args.port)


if __name__ == '__main__':
    main()
