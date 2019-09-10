import openapi_server
from flask import request, g
import logging


def make_no_cache_header():
    def handle_hon_cache_header(resp):
        if resp is not None and resp.headers is not None and resp.headers.get('Cache-Control'):
            logging.info('Cache control headers already applied')
            return resp

        from werkzeug.datastructures import Headers, MultiDict
        if (not isinstance(resp.headers, Headers)
                and not isinstance(resp.headers, MultiDict)):
            resp.headers = MultiDict(resp.headers)

        # cache results for 5 minutes
        # resp.headers.add('Cache-Control', 'max-age=300')
        resp.headers.add('Cache-Control', 'no-cache')
        return resp

    return handle_hon_cache_header


app = openapi_server.app
app.after_request(make_no_cache_header())


@app.app.before_request
def before_request():
    g.user = ''
    g.ip = ''
    g.token = {}


@app.app.after_request
def after_request_callback(response):
    if 'x-appengine-user-ip' in request.headers:
        g.ip = request.headers.get('x-appengine-user-ip')

    # enforce log level
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('auditlog')
    auditlog_list = list(filter(None, [
        f"Request Url: {request.url}",
        f"IP: {g.ip}",
        f"User-Agent: {request.headers.get('User-Agent')}",
        f"Response status: {response.status}",
        f"UPN: {g.user}"
    ]))

    logger.info(' | '.join(auditlog_list))

    return response
