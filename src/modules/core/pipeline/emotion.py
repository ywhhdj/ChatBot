from emotion_classifier import EmotionClassifier
from ...runtime import RuntimePath

DEFAULT_EMOTION_ID=4

class Emotion:
    def __init__(self,):
        model_path = RuntimePath.get_models_path("emotion")
        self.emotion_classifier = EmotionClassifier(
            str(model_path),
            "rust",
        )
        self.id2label = {
            v: k 
            for k, v in self.emotion_classifier._label2id.items()
        }
        self.is_init = False
    
    @property
    def is_initialized(self):
        return self.is_init
    
    def predict(self, text):
        label=self.emotion_classifier.predict_label(text)
        emotion=label[0][0][0]
        emotion_id=self.emotion_classifier._label2id[emotion]
        return emotion_id
    
    def emotion_to_id(self, emotion: str):
        return self.emotion_classifier._label2id[emotion]
    
    def id_to_emotion(self, id: int)-> str:
        return self.emotion_classifier._id2label[id]
    
    def init(self):
        if self.is_initialized:
            return
        self.emotion_classifier.ensure_loaded()

_emotion = None

def get_emotion() -> Emotion:
    global _emotion
    if _emotion is None:
        _emotion = Emotion()
    return _emotion

def init():
    get_emotion().init()

def predict(text):
    return get_emotion().predict(text)

def emotion_to_id(emotion: str):
    return get_emotion().emotion_to_id(emotion)

def id_to_emotion(id: int)-> str:
    return get_emotion().id_to_emotion(id)