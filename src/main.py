"""应用入口"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _parse_args(argv: list[str]) -> tuple[bool, str]:
    debug = os.environ.get("CHATBOT_DEBUG", "").strip().lower() in _TRUE_VALUES
    ui_mode = os.environ.get("CHATBOT_UI_MODE", "auto").strip().lower() or "auto"
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--debug":
            debug = True
        elif arg == "--no-debug":
            debug = False
        elif arg == "--ui-mode" and i + 1 < len(argv):
            ui_mode = argv[i + 1].strip().lower() or "auto"
            i += 1
        elif arg.startswith("--ui-mode="):
            ui_mode = arg.split("=", 1)[1].strip().lower() or "auto"
        i += 1
    if ui_mode not in ("auto", "desktop", "web"):
        ui_mode = "auto"
    os.environ["CHATBOT_UI_MODE"] = ui_mode
    return debug, ui_mode


def main(argv: list[str] | None = None) -> int:
    debug, ui_mode = _parse_args(list(sys.argv[1:] if argv is None else argv))
    from modules import create_app

    app = create_app("ChatBot", debug)
    app.init()
    if debug or ui_mode != "auto":
        print(f"[Main] debug={debug} ui_mode={ui_mode}")
    return app.run()


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("[Main] interrupted by user")
        sys.exit(130)
    except SystemExit:
        print("[App] [Main] exited")
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
