import logging

from flask import request, g


class AuditLog(object):
    def __init__(self, app=None):
        if app is not None:
            self._app = app.app
            self.__init_app()

    def __init_app(self):
        def before_request():
            g.user = ''
            g.ip = ''
            g.token = {}

        def after_request_callback(response):
            if 'x-appengine-user-ip' in request.headers:
                g.ip = request.headers.get('x-appengine-user-ip')

            # enforce log level
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

        self._app.before_request(before_request)
        self._app.after_request(after_request_callback)
