from fastapi import APIRouter
from ...utils import response
from ...logger import LogLevel,logger


logger_router=APIRouter(prefix="/logger")


ALLOWED_LEVELS=logger.get_logging_levels()

@logger_router.get('/levels')
def get_logger_levels() :
    return response.success({
        'current_level': logger.log_level,
        'levels': ALLOWED_LEVELS,
    })


# @logger_router.put('/level')
# def set_logger_level(payload: Dict[str, str]):
#     level = str(payload.get('level', '')).upper()
#     if level not in ALLOWED_LEVELS:
#         return response.not_found()
#     logger.set_log_level(level)
#     return response.success(True)


# @logger_router.get('/records')
# def get_logger_records(limit: int = 200):
#     return response.success(logger)


# @logger_router.delete('/records')
# def clear_logger_records():
#     logger.clear()
#     return response.success(True)



# @logger_router.post('/push')
# def push_logger_record(payload: Dict[str, str]):
#     level = str(payload.get('level', LogLevel.INFO)).upper()
#     message = payload.get('message', '')
#     logger_name = payload.get('logger', 'frontend')
#     logger.log(message,LogLevel(level),logger_name)
#     return response.success(True)
