import sys
sys.stdout = sys.stderr
from dashlivesim import SERVER_AGENT
from os.path import splitext
from time import time
from dashlivesim.dashlib.dash_proxy import handle_request
from collections import defaultdict


mime_map = defaultdict(lambda: 'text/plain', {'.mpd': 'application/dash+xml',
                                              '.m4s': 'video/iso.segment',
                                              '.mp4': 'video/mp4'})


headers = [('Accept-Ranges', 'bytes'),
           ('Pragma', 'no-cache'),
           ('Cache-Control', 'no-cache'),
           ('Expires', '-1'),
           ('DASH-Live-Simulator', SERVER_AGENT),
           ('Access-Control-Allow-Headers', 'origin,range,accept-encoding,referer'),
           ('Access-Control-Allow-Methods', 'GET,HEAD,OPTIONS'),
           ('Access-Control-Allow-Origin', '*'),
           ('Access-Control-Expose-Headers', 'Server,range,Content-Length,Content-Range,Date')]


def application(environment, start_response):

    path_parts = environment['REQUEST_URI'].split('/')
    ext = splitext(path_parts[-1])[1]
    headers.append(('Content-Type', mime_map[ext]))

    host_name = environment['HTTP_HOST']
    url_parts = path_parts[1:]
    args = None
    vod_conf_dir = environment['VOD_CONF_DIR']
    content_dir = environment['CONTENT_ROOT']
    now = time()
    req = None
    is_https = environment.get('HTTPS', 0)

    first_chunk = True
    for chunk in handle_request(host_name, url_parts, args, vod_conf_dir, content_dir, now, req, is_https):
        ok = True
        if isinstance(chunk, dict):
            ok, chunk = chunk['ok'], chunk['pl']
        if not isinstance(chunk,str):
            raise TypeError('sequence of byte string values expected for chunk: %s' % str(chunk)[:100])
        if first_chunk:
            first_chunk = False
            if ok:
                start_response('200 OK', headers)
            else:
                print chunk
                start_response('404 Not Found', headers)
                return
        yield chunk


def main():
    """Run stand-alone wsgi server for testing."""
    from wsgiref.simple_server import make_server
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
        """Wrapper around application for local web server."""
        env['REQUEST_URI'] = env['PATH_INFO'] # Set REQUEST_URI from PATH_INFO
        env['VOD_CONF_DIR'] = args.vod_conf_dir
        env['CONTENT_ROOT'] = args.content_dir
        return application(env, resp)

    httpd = make_server(args.host, args.port, application_wrapper)
    httpd.serve_forever()
    print 'Waiting for requests at "%s:%d"' % (args.host, args.port)


if __name__ == '__main__':
    main()