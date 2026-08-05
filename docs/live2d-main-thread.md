# Live2D Main-Thread Constraint

## Problem

When starting the Live2D service, the app could freeze and become unresponsive.
Typical logs:

- `Backend qtagg is interactive backend. Turning interactive mode on.`
- Live2D/OpenGL initialization messages followed by no UI response.

## Root Cause

`Live2D.start()` creates Qt/OpenGL objects (`QOpenGLWidget`, timers, window flags).  
These operations were executed through `TaskManager` worker threads (via `emit_service_async`), but Qt GUI objects must be created and controlled on the main UI thread.

## Fix

1. Mark `Live2D` as a main-thread-only service:
- `ChatBot/services/live2d/live2d.py`
- Added `require_main_thread = True`

2. Update service scheduling strategy:
- `ChatBot/manager/serviceManager.py`
- If a service has `require_main_thread = True`, `start/stop/close` run synchronously on the caller thread.
- If such service is started from a non-main thread, raise a clear error.

3. Update Qt bridge call path:
- `ui/desktop/qr_brige/Bridge.py`
- For main-thread-only services, call the service method directly in the Qt signal handler thread.
- Other services continue using `TaskManager` async dispatch.

## Result

- Live2D canvas creation stays on UI thread.
- No cross-thread Qt/OpenGL initialization for Live2D.
- Existing async dispatch behavior is preserved for non-UI services.

## Notes

- `Live2D` methods that touch canvas state should continue to be invoked from UI thread.
- If future services require GUI-thread access, reuse `require_main_thread = True`.
