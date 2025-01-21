from flask import request

class StaticFileMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path in ['/revision.ico', '/revision.png', '/favicon.ico']:
            start_response('204 No Content', [('Content-Type', 'text/plain')])
            return [b'']  # empty response
        return self.app(environ, start_response)
