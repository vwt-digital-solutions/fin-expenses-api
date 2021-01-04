#!/usr/bin/env python3

import connexion

from openapi_server import encoder


def main():
    print("[DEBUG] [CONNEXION] PRE INIT")
    app = connexion.App(__name__, specification_dir='./openapi/')
    app.app.json_encoder = encoder.JSONEncoder
    app.add_api('openapi.yaml',
                arguments={'title': 'Expenses API'},
                pythonic_params=True)
    app.run(port=8080)
    print("[DEBUG] [CONNEXION] POST INIT")


if __name__ == '__main__':
    main()
