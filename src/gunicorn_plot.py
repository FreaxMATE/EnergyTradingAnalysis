from plot import create_dash_app

app = create_dash_app()
server = app.server
app.run(debug=True)