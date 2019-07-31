#!/usr/bin/env python3

from api_server.openapi_server import app

if __name__ == '__main__':
    app.run(port=8080)
