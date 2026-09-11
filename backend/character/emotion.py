import re

expression_presets = {
    "normal": {
        "MouthSmile": 0.2,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.5,
        "BrowRightY": 0.5,
        "EyeOpenLeft": 1.0,
        "EyeOpenRight": 1.0,
        "CheekPuff": 0.0,
        "FaceAngleZ": 0.0,
        "FaceAngleY": 0.0,
    },


    "happy": {
        "MouthSmile": 0.8,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.7,
        "BrowRightY": 0.7,
        "EyeOpenLeft": 0.85,
        "EyeOpenRight": 0.85,
        "CheekPuff": 0.0,
        "FaceAngleZ": 0.0,
        "FaceAngleY": 0.0,
    },

    "sad": {
        "MouthSmile": 0.0,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.25,
        "BrowRightY": 0.25,
        "EyeOpenLeft": 0.55,
        "EyeOpenRight": 0.55,
        "CheekPuff": 0.0,
        "FaceAngleZ": 0.0,
        "FaceAngleY": -8.0,
    },

    "angry": {
        "MouthSmile": 0.0,
        "FaceAngry": 0.8,
        "BrowLeftY": 0.2,
        "BrowRightY": 0.2,
        "EyeOpenLeft": 0.9,
        "EyeOpenRight": 0.9,
        "CheekPuff": 0.0,
        "FaceAngleZ": -4.0,
        "FaceAngleY": 0.0,
    },

    "confused": {
        "MouthSmile": 0.1,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.7,
        "BrowRightY": 0.3,
        "EyeOpenLeft": 0.85,
        "EyeOpenRight": 0.85,
        "EyeLeftX": -0.25,
        "EyeRightX": -0.25,
        "CheekPuff": 0.0,
        "FaceAngleZ": 8.0,
        "FaceAngleY": 0.0,
    },

    "embarrassed": {
        "MouthSmile": 0.4,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.45,
        "BrowRightY": 0.45,
        "EyeOpenLeft": 0.65,
        "EyeOpenRight": 0.65,
        "EyeLeftX": 0.25,
        "EyeRightX": 0.25,
        "CheekPuff": 0.5,
        "FaceAngleZ": -6.0,
        "FaceAngleY": 0.0,
    },

    "bored": {
        "MouthSmile": 0.1,
        "FaceAngry": 0.0,
        "BrowLeftY": 0.3,
        "BrowRightY": 0.3,
        "EyeOpenLeft": 0.35,
        "EyeOpenRight": 0.35,
        "CheekPuff": 0.0,
        "FaceAngleZ": 0.0,
        "FaceAngleY": -5.0,
    }
}

def detect_emotion(user_text, ai_text):
    text = user_text + " " + ai_text

    if any(word in text for word in ["짜증", "화나", "화났", "열받", "빡쳐", "화를", "화가"]):
        return "angry"
    elif any(word in text for word in ["좋은 일", "좋아", "기뻐", "다행", "축하", "재밌"]):
        return "happy"
    elif any(word in text for word in ["힘들", "슬퍼", "미안", "괜찮아", "위로"]):
        return "sad"
    elif any(word in text for word in ["왜 이렇게", "이게 왜", "어라", "이상해", "모르겠", "왜 자꾸"]):
        return "confused"
    elif any(word in text for word in ["부끄", "민망", "당황", "어색"]):
        return "embarrassed"
    elif any(word in text for word in ["귀찮", "하기 싫", "별로"]):
        return "bored"
    else:
        return "normal"

def clean_for_tts(text):
    text = re.sub(r"[^\w\s가-힣ぁ-んァ-ン一-龥。、！？,.!?~]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def limit_text(text, max_len=80):
    return text[:max_len]

def apply_emotion_to_tts(text, emotion):
    if emotion == "happy":
        return text + "!", 1.2
    elif emotion == "sad":
        return text.replace("!", "."), 0.9
    elif emotion == "angry":
        return text + "!", 1.3
    elif emotion == "confused":
        return text + "?", 1.0
    elif emotion == "embarrassed":
        return text + "...", 0.95
    elif emotion == "bored":
        return text, 0.85
    else:
        return text, 1.1
    
    