from __future__ import annotations

import importlib

app_module = importlib.import_module("app")
app = app_module.create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
