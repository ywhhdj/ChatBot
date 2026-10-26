#管理所有模型的下载和删除

from typing import Literal, Optional
from models import ModelStatus
from ...runtime import RuntimePath

MODEL_CATEGORY=Literal["live2d","llm","ocr","emotion","tts","asr","image"]

class ModelManager:
    def __init__(self):
        self.models:dict[MODEL_CATEGORY,dict[str,ModelStatus]]={}
        self.scan_models()

    def scan_models(self):
        import os
        base_path=RuntimePath.get_user_data_path("models")
        for category in MODEL_CATEGORY.__args__:
            category_path=base_path/category
            if os.path.exists(category_path) and os.path.isdir(category_path):
                for model_id in os.listdir(category_path):
                    model_path=os.path.join(category_path,model_id)
                    if os.path.exists(model_path) and os.path.isdir(model_path):
                        self.add_model(category,model_id,download=True)
                    else:
                        self.add_model(category,model_id,download=False)

    def get_models(self,category:MODEL_CATEGORY,id:str):
        return self.models.get(category,{}).get(id)
    
    def add_model(self,category:MODEL_CATEGORY,id:str,download:bool=False,description:Optional[str]=None):
        if category not in self.models:
            self.models[category]={}
        if id not in self.models[category]:
            self.models[category][id]=ModelStatus(id=id,download=download,description=description)
            return True
        return False

    def remove_model(self,category:MODEL_CATEGORY,id:str):
        if category in self.models and id in self.models[category]:
            del self.models[category][id]
            return True
        return False