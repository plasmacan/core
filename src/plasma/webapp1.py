# import json
import os
import types


def main(response, request, json):
    response.data = json.dumps(dict(request.headers))


    #response.data = str(request.environ["apig_wsgi.context"].get_remaining_time_in_millis())
    #response.data = str(request.start_time)
    #response.data = f"{request.url} 1"

    response.headers["Cache-Control"] = "must-revalidate no-transform s-maxage=10 max-age=0"
    #"Cache-Control: no-store"
    return response

