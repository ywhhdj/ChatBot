import asyncio
import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

if __name__ == "__main__":
    try:
        import os;
        print(os.getpid())
        from modules.app import create_app
        app=create_app(True)
        app.init()
        asyncio.run(app.run())
    except Exception:
        import os
        import signal
        import traceback
        traceback.print_exc()
        os.kill(os.getpid(), signal.SIGINT)
        raise SystemExit(1)
