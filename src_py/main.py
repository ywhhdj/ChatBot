import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def main() -> int:
    from modules import create_app
    app = create_app("ChatBot",True)
    app.init()
    return app.run()


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("[Main] interrupted by user")
        sys.exit(130)
    except SystemExit:
        print("[App] [Main] exited")
        sys.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
