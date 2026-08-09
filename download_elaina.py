import os
import soundfile as sf
from datasets import load_dataset

# 1. 저장할 폴더 세팅
output_dir = "elaina_dataset"
wav_dir = os.path.join(output_dir, "wavs")
os.makedirs(wav_dir, exist_ok=True)
list_file_path = os.path.join(output_dir, "esd.list")

# 2. 허깅페이스에서 일레이나 데이터셋 다운로드
print("허깅페이스에서 데이터를 다운로드 중입니다. (인터넷 속도에 따라 몇 분 걸릴 수 있습니다)")
dataset = load_dataset("yeeko/Elaina_WanderingWitch_audio_JA", split="train")

# 3. 오디오 파일 저장 및 대본(esd.list) 작성
print("오디오 파일을 자르고 대본을 만드는 중...")
with open(list_file_path, "w", encoding="utf-8") as f:
    for i, item in enumerate(dataset):
        # 허깅페이스 오디오 데이터 로드
        audio = item["audio"]
        # 데이터셋에 존재하는 키(컬럼) 목록을 확인하여 알맞은 대본 데이터를 가져옵니다.
        available_keys = item.keys()

        if "text" in available_keys:
            text = item["text"]
        elif "sentence" in available_keys:
            text = item["sentence"]
        elif "transcription" in available_keys:
            text = item["transcription"]
        else:
            # 예상치 못한 이름일 경우, 현재 존재하는 모든 키를 화면에 출력하고 스크립트를 종료합니다.
            print(f"❌ 대본 데이터를 찾을 수 없습니다! 현재 존재하는 데이터 항목: {available_keys}")
            exit()  # 대본 텍스트
        
        # 파일 이름 만들기 (예: elaina_0001.wav)
        wav_filename = f"elaina_{i:04d}.wav"
        wav_filepath = os.path.join(wav_dir, wav_filename)
        
        # 오디오를 wav 파일로 저장
        sf.write(wav_filepath, audio["array"], audio["sampling_rate"])
        
        # SBV2 양식에 맞춰서 한 줄 쓰기: 파일명|화자이름|언어(JP)|대사
        # (원래 일본어 데이터이므로 언어 태그는 반드시 JP로 해야 합니다)
        line = f"{wav_filename}|Elaina|JP|{text}\n"
        f.write(line)

print(f"완료되었습니다! '{output_dir}' 폴더 안에 wavs 폴더와 esd.list 파일이 생성되었습니다.")