import asyncio, json, re, os, hashlib, glob
import edge_tts

# 사용법: python3 interview/_build/build_audio.py
# 탭 하나 = 덱 하나. 모든 덱을 interview/index.html 한 페이지로 만든다.
import sys
ROOT, TPL = "interview", os.path.join(os.path.dirname(__file__), "template.html")
DECKS = [  # (탭 키, 탭 이름, ROOT 기준 MD 경로, ROOT 기준 음성 폴더)
    ("kakao", "카카오뱅크", "interview.md", "audio"),
    ("shinhan", "신한은행", "shinhan/interview.md", "shinhan/audio"),
]
VOICES = {"interviewer": ("ko-KR-SunHiNeural", "+0%"), "me": ("ko-KR-InJoonNeural", "-3%")}
# 발음 보정 (화면 텍스트는 그대로, 음성만)
FIX = [("OpenAI API", "오픈에이아이 에이피아이"), ("SOL LINK", "쏠 링크"), ("SOL", "쏠"), ("DAU", "디에이유"), ("PO", "피오"), ("3%p", "3퍼센트포인트"), ("A/B", "에이비"), ("M/L", "엠엘"), ("v1.0", "버전 일 점 영"),
       ("1~2주", "일에서 이 주"), ("UID", "유아이디"), ("GUI", "지유아이"), ("UX", "유엑스"), ("UI", "유아이"),
       ("B2B", "비투비"), ("FGI", "에프지아이"), ("FGD", "에프지디"), ("UT", "유티"), ("SQL", "에스큐엘"), ("LLM", "엘엘엠"),
       ("MAU", "엠에이유"), ("LTV", "엘티브이"), ("PV", "피브이"), ("2030", "이공삼공"), ("Vertical", "버티컬"), ("UV", "유브이"), ("QA", "큐에이"), ("PM", "피엠"), ("PL", "피엘"), ("Flow", "플로우"), ("GPT", "지피티"), ("Cowork", "코워크"), ("1주일", "일 주일"),
       ("SK플래닛", "에스케이플래닛"), ("OK캐쉬백", "오케이캐쉬백"), ("e금", "이금"),
       ("11년", "십일 년"), ("5년", "오 년"), ("26주", "이십육 주"), ("1회", "일 회"), ("3개월", "삼 개월"), ("1개월", "일 개월"), ("AI", "에이아이")]

def tts_text(t):
    for a, b in FIX: t = t.replace(a, b)
    t = re.sub(r"(\d+(?:\.\d+)?)%p", r"\1퍼센트포인트", t)
    return re.sub(r"(\d+(?:\.\d+)?)%", r"\1퍼센트", t).replace("\n", " ")

def parse(MD):
    items, cur, spk, buf = [], None, None, []
    def flush():
        nonlocal buf, spk
        if spk and buf: cur["turns"].append({"speaker": spk, "text": "\n".join(buf).strip()})
        buf, spk = [], None
    for line in open(MD, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^## (?:질문 (\d+)|역질문)\. (.+)", line)
        if m: flush(); cur = {"no": int(m[1]) if m[1] else None, "title": m[2], "turns": []}; items.append(cur); continue
        m = re.match(r"^\*\*(면접관|지원자)\*\*: (.*)", line)
        if m and cur: flush(); spk = "interviewer" if m[1] == "면접관" else "me"; buf = [m[2]]; continue
        if spk and line.strip(): buf.append(line.strip())
    flush()
    return items

async def main():
    decks, jobs = [], []
    for key, label, md, adir in DECKS:
        os.makedirs(f"{ROOT}/{adir}", exist_ok=True)
        items = parse(f"{ROOT}/{md}")
        for q in items:
            for t in q["turns"]:
                v, rate = VOICES[t["speaker"]]; say = tts_text(t["text"])
                t["audio"] = f"{adir}/{t['speaker']}_{hashlib.sha1((v+rate+say).encode()).hexdigest()[:10]}.mp3"
                jobs.append((t, v, rate, say))
        title = next(l[2:].strip() for l in open(f"{ROOT}/{md}", encoding="utf-8") if l.startswith("# ")).lstrip("🎧").strip()
        decks.append({"key": key, "label": label, "title": title, "questions": items})
    sem = asyncio.Semaphore(4); made = 0
    async def gen(t, v, rate, say):
        nonlocal made
        path = f"{ROOT}/{t['audio']}"
        if os.path.exists(path) and os.path.getsize(path) > 0: return
        async with sem:
            for _ in range(3):
                try: await edge_tts.Communicate(say, v, rate=rate).save(path); made += 1; return
                except Exception as e: print("retry", path, e); await asyncio.sleep(2)
    await asyncio.gather(*(gen(*j) for j in jobs))
    missing = [t["audio"] for t, *_ in jobs if not (os.path.exists(f"{ROOT}/{t['audio']}") and os.path.getsize(f"{ROOT}/{t['audio']}") > 0)]
    if missing: sys.exit(f"음성 생성 실패 {len(missing)}개, index.html을 갱신하지 않았습니다: {missing[:3]}")
    keep = {f"{ROOT}/{t['audio']}" for t, *_ in jobs}
    stale = [p for _, _, _, adir in DECKS for p in glob.glob(f"{ROOT}/{adir}/*.mp3") if p not in keep]
    for p in stale: os.remove(p)
    html = open(TPL, encoding="utf-8").read().replace("__DATA__", json.dumps(decks, ensure_ascii=False))
    open(f"{ROOT}/index.html", "w", encoding="utf-8").write(html)
    for d in decks: print(f"{d['label']}: {len(d['questions'])} questions, {sum(len(q['turns']) for q in d['questions'])} turns")
    print(f"{made} generated, {len(stale)} removed")
asyncio.run(main())
