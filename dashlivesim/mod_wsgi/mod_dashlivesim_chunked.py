"WSGI Module for dash-live-source-simulator-chunked."

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2020, Dash Industry Forum.
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
from collections.abc import Generator
from os.path import splitext
from urllib.parse import urlparse, parse_qs
from time import time

from dashlivesim.dashlib import dash_proxy_gen, sessionid
from dashlivesim import SERVER_AGENT

MAX_SESSION_LENGTH = 0  # If non-zero,  limit sessions via redirect

# Helper for HTTP responses
# pylint: disable=dangerous-default-value

status_string = {
    200: 'OK',
    206: 'Partial Content',
    302: 'Found',
    404: 'Not Found',
    410: 'Gone'
    }

chunk_hdrs = [('Pragma', 'no-cache'),
              ('Cache-Control', 'no-cache'),
              ('Expires', '-1'),
              ('DASH-Live-Simulator', SERVER_AGENT),
              ('Access-Control-Allow-Headers', 'origin,accept-encoding,referer'),
              ('Access-Control-Allow-Methods', 'GET,HEAD,OPTIONS'),
              ('Access-Control-Allow-Origin', '*'),
              ('Access-Control-Expose-Headers', 'Server,Content-Length,Date')]


def add_headers(status_code, resp, extra_headers={}):
    "Add HTTP status and headers to resp."
    status = "%d %s" % (status_code, status_string[status_code])

    headers = chunk_hdrs[:]
    for key, value in extra_headers.items():
        headers.append((key, value))

    resp(status, headers)


# pylint: disable=too-many-branches, too-many-locals
def application(environment, start_response):
    "WSGI Entrypoint"

    hostname = environment['HTTP_HOST']
    url = urlparse(environment['REQUEST_URI'])
    vod_conf_dir = environment['VOD_CONF_DIR']
    content_root = environment['CONTENT_ROOT']
    is_https = environment.get('HTTPS', 0)
    path_parts = url.path.split('/')
    ext = splitext(path_parts[-1])[1]
    query = url.query if url.query else environment.get('QUERY_STRING', '')
    args = parse_qs(query)

    now = time()

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
            add_headers(302, start_response, {'Location': new_url})
            return
        elif start_time is None:
            add_headers(404, start_response)
            return b'No start_time in non-manifest request'
        else:
            if now > start_time + MAX_SESSION_LENGTH:
                add_headers(410, start_response)
                return ("Maximum session length %ds passed" % MAX_SESSION_LENGTH).encode('utf-8')
            elif start_time > now + 5:  # Give some margin
                add_headers(404, start_response)
                return b'start_time is in future'

    success = True
    mime_type = get_mime_type(ext)
    payload = None

    try:
        response = dash_proxy_gen.handle_request(hostname, path_parts[1:], args,
                                                 vod_conf_dir, content_root, now,
                                                 None, is_https)
    # pylint: disable=broad-except
    except Exception as exc:
        traceback.print_exc()
        add_headers(500, start_response, {'Content-Type': "text/plain"})
        yield "DASH Proxy Error: {0}\n URL={1}".format(exc, url).encode('utf-8')
        return

    for part_nr, response_chunk in enumerate(response):
        if isinstance(response_chunk, bytes) or isinstance(response_chunk, str):
            payload = response_chunk
            if not payload:
                success = False
        elif isinstance(response_chunk, dict):
            if not response_chunk['ok']:
                success = False
            payload = response_chunk['pl']

        if not success:
            if not payload:
                payload = "Not found (now)"
            add_headers(404, start_response, {'Content-Type': "text/plain"})
            yield payload.encode('utf-8')
            return

        if part_nr == 0:
            add_headers(200, start_response, {'Content-Type': mime_type})

        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        # print("Time passed for part %d is %.3fs" % (part_nr, time() - now))
        yield payload
    # print("Time passed after last is %.3fs" % (time() - now))


def get_mime_type(ext):
    "Get mime-type depending on extension."
    if ext == ".mpd":
        return "application/dash+xml"
    elif ext == ".m4s":
        return "video/iso.segment"
    elif ext == ".mp4":
        return "video/mp4"

    return "text/plain"


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
