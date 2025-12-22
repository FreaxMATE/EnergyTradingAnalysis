from plot import create_dash_app
from config import DASH_HOST, DASH_PORT, DASH_DEBUG

app = create_dash_app()
server = app.server
app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)

