import faiss

class FAISS:
    def __init__(self,_index:int=768) -> None:
        self.index =faiss.IndexFlatL2(_index)
        self.index_dim = _index
    
    def save(self,path:str):
        faiss.write_index(self.index,path)
