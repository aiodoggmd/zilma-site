"""Ролик «как в кино» из scenes.json: у каждой сцены своя реплика («say») и свой кадр.

    python tools\\instagram\\make_film.py <папка ролика>

В папке должны быть scenes.json и кадры frames\\NN.png (их рисует render_carousel.py).
Шаги: озвучка каждой реплики голосом vera (Яндекс, livetts; уже озвученные не трогает),
наезд камеры на каждом кадре, плавное наложение 0,35 с между кадрами (fade; dissolve рассыпает картинку на точки), голос стоит точно на своём кадре.
Выход: <папка>\\film.mp4 (1080×1920).
"""
import json
import subprocess
import sys
from pathlib import Path

TTS = Path(r'D:\Projects\мультики\tts_yandex.py')
PY = Path(r'D:\Projects\мультики\.venv\Scripts\python.exe')
BG = '0xfaf6f0'
HEADER = Path(__file__).parent / 'video-header.png'
FPS = 30
X = 0.35          # растворение между кадрами
LEAD = 0.25       # кадр появляется чуть раньше голоса
TAIL = 0.45       # и держится после реплики


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    root = Path(sys.argv[1])
    animate = '--anim' in sys.argv          # оживление сцен (anim.py) и полоска прогресса
    scenes = json.loads((root / 'scenes.json').read_text(encoding='utf-8'))
    audio = root / 'audio'
    audio.mkdir(exist_ok=True)
    clips = root / 'clips'
    clips.mkdir(exist_ok=True)
    durs, wavs = [], []
    for n, s in enumerate(scenes, 1):
        wav = audio / f'{n:02d}.wav'
        if not wav.exists():
            if len(s['say']) > 250:
                sys.exit(f'сцена {n}: реплика длиннее 250 знаков — разделите на две сцены')
            for attempt in range(3):              # обрыв связи с Яндексом бывает (16.10.2026) — повторить
                r = subprocess.run([str(PY), str(TTS), 'vera', '-', 'livetts', s['say'], str(wav)],
                                   stdout=subprocess.DEVNULL)
                if r.returncode == 0 and wav.exists():
                    break
            else:
                sys.exit(f'сцена {n}: озвучка не удалась трижды')
        a = dur(wav)
        durs.append(LEAD + a + TAIL + X)          # X — запас на растворение в следующий кадр
        wavs.append(wav)
    # кадры с наездом
    for n, d in enumerate(durs, 1):
        if animate:
            s = scenes[n - 1]
            p = scenes[n - 2] if n > 1 else None
            # раскрытие внутри сцены: тот же тип и тот же заголовок (у прядей и вопроса заголовок может смениться)
            s['_same_as_prev'] = bool(p and p.get('type') == s.get('type') and
                                      (p.get('title') == s.get('title') or s.get('type') in ('versus', 'trio', 'question')))
            s['_seed'] = f'{root.name}-{n}'
            # круг пропорции — сам, если на кадре написано «1 : 1» или «1 : 2» (доля краски)
            import re as _re
            m = _re.match(r'\s*1\s*:\s*(\d)', s.get('note', '')) if s.get('wheel') is None else None
            if m:
                s['wheel'], s['wheel_label'] = round(100 / (1 + int(m.group(1)))), f'1 : {m.group(1)}'
            sys.path.insert(0, str(Path(__file__).parent))
            from anim import anim_frames, ANIM
            adir = root / 'anim' / f'{n:02d}'
            for old in adir.glob('*.png'):
                old.unlink()
            prev_png = root / 'frames' / f'{n - 1:02d}.png' if n > 1 else None
            cnt = anim_frames(root / 'frames' / f'{n:02d}.png', prev_png, s, adir, FPS)
            rest = max(0.1, d - cnt / FPS)
            vf = (f"[0:v][1:v]concat=n=2:v=1:a=0,fps={FPS},"
                  f"scale=w='1080*(1+0.035*t/{d:.3f})':h=-1:eval=frame,crop=1080:1350,"
                  f"pad=1080:1920:0:285:color={BG}[bg];[bg][2:v]overlay=0:0,format=yuv420p")
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(adir / '%03d.png'),
                            '-loop', '1', '-framerate', str(FPS), '-t', f'{rest:.3f}', '-i', str(adir / 'still.png'),
                            '-i', str(HEADER), '-filter_complex', vf, '-r', str(FPS), '-t', f'{d:.3f}',
                            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', str(clips / f'{n:02d}.mp4')], check=True)
            continue
        # наезд: масштаб растёт кадр за кадром, обрезка по центру. В 17 раз быстрее zoompan
        # (5 с против 90 с на сцену, замер 17.10.2026) при том же виде.
        # шапка ZILMA (как в каталоге сайта) — в верхнем поле, неподвижно: наезд камеры её не срезает
        vf = (f"[0:v]scale=w='1080*(1+0.035*t/{d:.3f})':h=-1:eval=frame,crop=1080:1350,"
              f"pad=1080:1920:0:285:color={BG}[bg];[bg][1:v]overlay=0:0,format=yuv420p")
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-t', f'{d:.3f}', '-i', str(root / 'frames' / f'{n:02d}.png'),
                        '-i', str(HEADER), '-filter_complex', vf, '-r', str(FPS), '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', str(clips / f'{n:02d}.mp4')],
                       check=True)
    # склейка с растворением: старт кадра n = сумма (d_i - X)
    starts, t = [], 0.0
    for d in durs:
        starts.append(t)
        t += d - X
    total = t + X
    ins = []
    for n in range(1, len(durs) + 1):
        ins += ['-i', str(clips / f'{n:02d}.mp4')]
    fc, prev = [], '[0:v]'
    for n in range(1, len(durs)):
        out = f'[v{n}]'
        fc.append(f'{prev}[{n}:v]xfade=transition=fade:duration={X}:offset={starts[n]:.3f}{out}')
        prev = out
    # голос: каждая реплика на своём кадре
    k = len(durs)
    for n, w in enumerate(wavs):
        ins += ['-i', str(w)]
        fc.append(f'[{k + n}:a]adelay={int((starts[n] + LEAD) * 1000)}:all=1[a{n}]')
    fc.append(''.join(f'[a{n}]' for n in range(len(wavs))) + f'amix=inputs={len(wavs)}:normalize=0,apad[aout]')
    if animate:                                   # полоска прогресса под шапкой: сколько осталось
        fc.append(f"{prev}drawbox=x=90:y=266:w='max(2,900*t/{total:.3f})':h=6:color=0xc8000f:t=fill[vp]")
        prev = '[vp]'
    out = root / 'film.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', *ins, '-filter_complex', ';'.join(fc),
                    '-map', prev, '-map', '[aout]', '-t', f'{total:.3f}',
                    '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', str(out)], check=True)
    print(f'готово: {out} · {dur(out):.1f} с, сцен {len(durs)}')


if __name__ == '__main__':
    main()
