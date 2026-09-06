from fastapi import Request


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session
