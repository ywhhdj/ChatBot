class TokenCalculator:
    def __init__(self) -> None:
        self.token_ratio={
            "cn":1.5,
            "es":0.7
        }
        #可以根据需求适配各大模型供应商的token计算规则
    
    def extract_tokens(self, text: str) -> int:
        cn_chars=sum(1 for ch in text if "\u4e00" <= ch <= "\u9fa5")
        es_chars=len(text.split())-cn_chars
        return int(cn_chars/self.token_ratio["cn"]+es_chars/self.token_ratio["es"])