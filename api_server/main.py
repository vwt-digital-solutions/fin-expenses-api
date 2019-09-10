import openapi_server
from flask import request, g
import logging

app = openapi_server.app


@app.app.before_request
def before_request():
    g.user = ''
    g.ip = ''
    g.token = {}


@app.app.after_request
def after_request_callback(response):
    if 'x-appengine-user-ip' in request.headers:
        g.ip = request.headers.get('x-appengine-user-ip')

    logging.basicConfig(level=logging.info())
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
