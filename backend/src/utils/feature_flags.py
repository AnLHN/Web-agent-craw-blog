from fastapi import Request


def feature_enabled(request: Request, flag_name: str) -> bool:
    settings = request.app.state.settings
    return bool(getattr(settings, flag_name, False))
