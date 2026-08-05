from ...runtime import RuntimePath

class LLMEmotionClassifier:
    def __init__(self):
        from emotion_classifier import EmotionClassifier
        self.emotion_classifier = EmotionClassifier(
            model_dir=RuntimePath.get_models_path("emotion"),
            backend="onnx",
            device="cpu",
        )
    def initialize(self):
        self.emotion_classifier.init()
    
    def classify(self, text: str) -> str:
        return self.emotion_classifier.predict_label(text)[0][0]
