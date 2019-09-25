import logging

from .utils import *


class CacheControl(object):
    def __init__(self, app=None, options=None):
        self._options = options if options is not None else DEFAULT_OPTIONS
        if 'resources' not in self._options:
            self._options['resources'] = DEFAULT_OPTIONS['resources']
        if app is not None:
            self.__init_app(app)

    def __init_app(self, app):
        def make_no_cache_header(resources):
            def handle_no_cache_header(resp):
                if resp.headers is not None and resp.headers.get('Cache-Control'):
                    logging.info('CacheControl headers already applied')
                    return resp

                from werkzeug.datastructures import Headers, MultiDict
                if (not isinstance(resp.headers, Headers)
                        and not isinstance(resp.headers, MultiDict)):
                    resp.headers = MultiDict(resp.headers)

                # cache results for 5 minutes
                # resp.headers.add('Cache-Control', 'max-age=300')
                for res in resources:
                    if try_match(request.path, res['pattern']):
                        logging.debug(
                            "Request to '%s' matches CacheControl resource '%s'. Using options: %s",
                            request.path, get_regexp_pattern(res['pattern']), res['action'])
                        resp.headers.add('Cache-Control', res['action'])
                        break
                else:
                    logging.debug('No CacheControl rule matches')
                return resp

            return handle_no_cache_header

        # logging.basicConfig(level=logging.DEBUG)
        # self._resources = parse_resources(self._options)
        app.app.after_request(make_no_cache_header(self._options['resources']))
