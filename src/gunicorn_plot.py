from plot import create_dash_app

app = create_dash_app()
server = app.server

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)