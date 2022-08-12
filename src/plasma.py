import cylinder  # pip install cylinder
from apig_wsgi import make_lambda_handler  # pip install apig-wsgi


def triage(request):  # pylint: disable=unused-argument
    return "plasma", "webapp1"


app = cylinder.get_app(triage)
lambda_handler = make_lambda_handler(app)


def main():
    app.run(host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
