def __getattr__(name: str):
    if name == "ShellService":
        from .client import QQBotClient
        return QQBotClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")