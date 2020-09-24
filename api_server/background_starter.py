import webapp2


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.out.write('{"status":"OK"}')


app = webapp2.WSGIApplication([('/_ah/start', MainPage)], debug=True)
