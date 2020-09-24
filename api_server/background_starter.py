import os
import webapp2

from google.appengine.ext.webapp import template


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.out.write('{"status":"OK"}')


app = webapp2.WSGIApplication([('/_ah/start', MainPage)], debug=True)
