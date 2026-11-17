"""Word(맥)로 docx 쪽수 확인: python3 scripts/tools/word_pages.py a.docx [b.docx ...]
주의: Word에 다른 문서가 열려 있으면 'active document'가 엉뚱한 문서를 가리킨다 → 모두 닫고 이름으로 지정해 센다."""
import shutil, subprocess, sys, pathlib
D = pathlib.Path.home() / 'Library/Containers/com.microsoft.Word/Data/Documents'
subprocess.run(['osascript', '-e', 'tell application "Microsoft Word" to close every document saving no'], capture_output=True)
for a in sys.argv[1:]:
    src = pathlib.Path(a).resolve(); shutil.copy(src, D / src.name)
    scr = f'''tell application "Microsoft Word"
open POSIX file "{D / src.name}"
delay 6
set p to compute statistics document "{src.name}" statistic statistic pages
close document "{src.name}" saving no
return p
end tell'''
    print(src.name, subprocess.run(['osascript', '-e', scr], capture_output=True, text=True).stdout.strip(), '쪽')
