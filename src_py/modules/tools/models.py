from dataclasses import dataclass
from typing import Any, Literal, Optional, List, Union

PropertyType=Literal["string","number","boolean","object","array","integer"]

AIPlatformType=Literal["openai","anthropic"]

@dataclass
class ToolFunctionParameters:
    type:PropertyType
    properties:dict[str,dict[str,Any]]
    required:Optional[list[str]]=None

    def to_dict(self)->dict:
        return {
            "type":self.type,
            "properties":self.properties,
            "required":self.required
        }

@dataclass
class ToolFunction:
    name:str
    description:str
    parameters:ToolFunctionParameters
    required:Optional[list[str]]=None

    def to_dict(self)->dict:
        return {
            "name":self.name,
            "description":self.description,
            "parameters":self.parameters.to_dict()
        }

ServiceTool=List[ToolFunction]

@dataclass
class OpenAITool:
    type:Literal["function"]
    function:ToolFunction
    
    def to_dict(self)->dict:
        return {
            "type":self.type,
            "function":self.function.to_dict()
        }

@dataclass
class AnthropicTool:
    name:str
    description:str
    input_schema:ToolFunctionParameters

    def to_dict(self)->dict:
        return {
            "name":self.name,
            "description":self.description,
            "input_schema":self.input_schema.to_dict()
        }

AITool=List[Union[OpenAITool,AnthropicTool,dict]]
