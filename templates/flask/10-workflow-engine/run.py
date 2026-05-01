try:
    from .app import create_app
except ImportError:
    from app import create_app  # pyright: ignore[reportImplicitRelativeImport]

create_app().run(debug=True)
