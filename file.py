import kagglehub, os, shutil

# 1) 다운로드 (캐시로 받아짐)
src = kagglehub.dataset_download("giovannimonco/wadi-data")
print("캐시 경로:", src)
print("파일 목록:", os.listdir(src))

# 2) 프로젝트 폴더로 복사
dst = r"C:\Users\정기흔\PROJECT_ELEC\wadi"
os.makedirs(dst, exist_ok=True)
for root, _, files in os.walk(src):
    for f in files:
        shutil.copy2(os.path.join(root, f), os.path.join(dst, f))

print("복사 완료 →", dst)
print("최종 파일:", os.listdir(dst))