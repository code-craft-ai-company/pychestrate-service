import logging
import os
import sys

from automojo.webworks.webapplication import establish_webapp_persona
from automojo.webworks.asgi.application import create_asgi_application
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import HTMLResponse

DIR_THIS = os.path.dirname(__file__)

logger = logging.getLogger("scms")

app = establish_webapp_persona(
    name="pychestrate",
    logger_name="scms",
    log_basename="pychestrate"
)

@app.attach_route("/", methods=["GET"])
def hello_world(request: Request) -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pychestrate SCM</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f5f7fa; color: #333; }
            header { background-color: #2c3e50; color: white; padding: 1rem 2rem; }
            .container { padding: 2rem; max-width: 1200px; margin: 0 auto; }
            .card { background: white; border-radius: 8px; padding: 2rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            h1 { margin-top: 0; }
        </style>
    </head>
    <body>
        <header>
            <h1>⚙️ Pychestrate SCM</h1>
        </header>
        <div class="container">
            <div class="card">
                <h2>Welcome to Pychestrate</h2>
                <p>The Software Configuration Management system powered by Automation Mojo WebWorks.</p>
                <p>This is the initial web interface scaffolding.</p>
                <hr>
                <p><em>Status:</em> Online and Orchestrating.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Export the ASGI application for uvicorn/gunicorn
asgi_app = create_asgi_application(app)

def pychestrate_website_main():
    import uvicorn
    # When run directly for development
    uvicorn.run(asgi_app, host="0.0.0.0", port=8888)

if __name__ == "__main__":
    pychestrate_website_main()
