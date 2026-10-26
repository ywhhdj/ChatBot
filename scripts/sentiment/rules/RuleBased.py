import re
from typing import TypedDict, Union
from jieba import cut
import numpy as np
from typing import Literal
import os

SentimentType=Literal["neutral","positive","negative","中性","正面","负面"]
class types:
    class SentimentWords(TypedDict):
        stop: list[str]
        intensifiers: dict[str,float]
        positive: list[str]
        negative: list[str]

    class SentimentResultBase(TypedDict):
        sentiment: SentimentType

    class SentimentOneResult(SentimentResultBase,TypedDict):
        words: list[str]
        score: float

    #整体的情感分析结果
    class SentimentOverallResult(SentimentResultBase,TypedDict):
        trend: Literal['improving', 'degrading', 'stable', 'insufficient']

class RuleBasedSentimentAnalyzer:
    def __init__(self,positive_threshold:float=0.2,negative_threshold:float=-0.2) -> None:
        from ...modules.utils.file import read_json
        self.words:types.SentimentWords=read_json("sentiment_words.json",encoding="utf-8")
        #阈值
        self.positive_threshold=positive_threshold
        self.negative_threshold=negative_threshold
        self.en_to_cn_map:dict[str,SentimentType]={
            "neutral": "中性",
            "positive": "正面",
            "negative": "负面",
        }

    def preprocess(self, text: str):
        text=re.sub(r"[^\w\s\u4e00-\u9fa5]", "", text)
        words=cut(text)
        words=[word for word in words if word not in self.words["stop"]]
        return words
    
    def analyze(self, text: str,is_cn:bool=True)->types.SentimentOneResult:
        words=self.preprocess(text)
        sentiment_score=0
        intensity=1.0
        negation=False
        for index,word in enumerate(words):
            if word in self.words["intensifiers"]:
                intensity=self.words["intensifiers"][word]
                continue
            words_score=0.0
            if word in self.words["positive"]:
                words_score=1.0
            elif word in self.words["negative"]:
                words_score=-1.0
            if words_score!=0.0:
                adjusted_score=words_score*intensity
                if negation:
                    adjusted_score=-adjusted_score
                    negation=False
                sentiment_score+=adjusted_score
                intensity=1.0
        neutral_score=np.tanh(sentiment_score)
        
        if neutral_score<self.negative_threshold:
            sentiment= "negative"
        elif neutral_score>self.positive_threshold:
            sentiment= "positive"
        else:
            sentiment= "neutral"
        if is_cn:
            return types.SentimentOneResult(
                sentiment=self.en_to_cn_map[sentiment],
                score=float(neutral_score),
                words=words,
            )
        return types.SentimentOneResult(
                sentiment=sentiment,
                score=float(neutral_score),
                words=words,
            )
    
    def analyze_conversation(self, messages: Union[list[str],list[dict]],is_cn:bool=True)->types.SentimentOverallResult:
        sentiment_scores=[]
        for message in messages:
            if message:
                if isinstance(message, str):
                    message=message
                else:
                    message=message["content"]
                result=self.analyze(message)
                sentiment_scores.append(result["score"])
        if not sentiment_scores:
            return types.SentimentOverallResult(
                sentiment="neutral",
                trend="insufficient",
            )
        avg_score=np.mean(sentiment_scores)
        if avg_score<self.negative_threshold:
            sentiment= "negative"
        elif avg_score>self.positive_threshold:
            sentiment= "positive"
        else:
            sentiment= "neutral"
        if len(sentiment_scores)>3:
            recent_scores=sentiment_scores[-3:]
            trend_slope=np.polyfit(range(len(recent_scores)), recent_scores, 1)[0]
            if trend_slope<0.1:
                trend="improving" #趋势上升
            elif trend_slope>-0.1:
                trend="degrading" #趋势下降
            else:
                trend="stable" #趋势稳定
        else:
            trend="insufficient" #数据不足
        if is_cn:
            return types.SentimentOverallResult(
                sentiment=self.en_to_cn_map[sentiment],
                trend=trend,
            )
        return types.SentimentOverallResult(
                sentiment=sentiment,
                trend=trend,
            )

