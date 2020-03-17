#!/usr/bin/env bash
docker run --rm -v "${PWD}":/local openapitools/openapi-generator-cli generate \
  --skip-overwrite \
  -i /local/openapi_server/openapi/openapi.yaml \
  -g python-flask \
  -o /local