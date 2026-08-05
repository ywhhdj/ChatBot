from abc import ABC, abstractmethod
from types import CoroutineType
from typing import Any
import numpy as np
from .models import CompressedMemory, Memory

class _MemoryStorageBase(ABC):
    @abstractmethod
    def add_memory(self,memory:Memory,vector:np.ndarray,importance:float=0.0) -> CoroutineType[Any,Any,int]:
        raise NotImplementedError

    @abstractmethod
    def retrieve_memory(self,query_vector: np.ndarray,limit:int=10)-> CoroutineType[Any,Any,list[dict[str,Any]]]:
        raise NotImplementedError
    
    @abstractmethod
    def delete_memory(self,memory_id:str) -> CoroutineType[Any,Any,None]:
        raise NotImplementedError
    
    @abstractmethod
    def get_short_term(self, session_id: str = "default", limit: int = 100) -> CoroutineType[Any,Any,list[dict[str, Any]]]:
        raise NotImplementedError
    
    @abstractmethod
    def get_long_term(self, session_id: str = "default", limit: int = 100) -> CoroutineType[Any,Any,list[dict[str, Any]]]:
        raise NotImplementedError
    
    @abstractmethod
    def get_detailed(self,memory_id:str)-> CoroutineType[Any,Any,list[dict[str, Any]]]:
        raise NotImplementedError
    
    @abstractmethod
    def close(self) -> CoroutineType[Any,Any,None]:
        raise NotImplementedError
    
    @abstractmethod
    def get_compressed(self) -> CoroutineType[Any,Any,list[CompressedMemory]]:
        raise NotImplementedError
    
    @abstractmethod
    def add_memories(self,memories:list[Memory]) -> CoroutineType[Any,Any,list[int]]:
        raise NotImplementedError
    
    @abstractmethod
    def start(self) -> CoroutineType[Any,Any,None]:
        raise NotImplementedError