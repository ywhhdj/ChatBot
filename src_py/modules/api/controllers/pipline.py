from typing import Optional
from fastapi import APIRouter, Query

from ...pipeline.enum import AdapterType
from ...utils import response
from ...manager.pipeline import pipeline_manager
pipeline_router=APIRouter(prefix="/pipeline")

@pipeline_router.get("/supported")
async def get_supported_models(type:Optional[str]=Query(None,description="模型类型，如 llm, chatm 等")):
    if type:
        config=pipeline_manager.get_adapter_type_config(AdapterType(type))
        if config:
            return response.success(config)
        else:
            return response.error(f"Adapter type {type} not found")    
    else:
        return response.success(pipeline_manager.get_pipeline_all_configs())
        
        