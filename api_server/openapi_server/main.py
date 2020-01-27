#!/usr/bin/env python3

from openapi_server import app

eval_var = "123"
vulnerability_sast_test = eval(eval_var)

if __name__ == '__main__':
    app.run(port=8080)
