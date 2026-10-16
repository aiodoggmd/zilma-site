"""Ролик «как в кино» из scenes.json: у каждой сцены своя реплика («say») и свой кадр.

    python tools\\instagram\\make_film.py <папка ролика>

В папке должны быть scenes.json и кадры frames\\NN.png (их рисует render_carousel.py).
Шаги: озвучка каждой реплики голосом vera (Яндекс, livetts; уже озвученные не трогает),
наезд камеры на каждом кадре, растворение 0,35 с между кадрами, голос стоит точно на своём кадре.
Выход: <папка>\\film.mp4 (1080×1920).
"""
import json
import subprocess
import sys
from pathlib import Path

TTS = Path(r'D:\Projects\мультики\tts_yandex.py')
PY = Path(r'D:\Projects\мультики\.venv\Scripts\python.exe')
BG = '0xfaf6f0'
FPS = 30
X = 0.35          # растворение между кадрами
LEAD = 0.25       # кадр появляется чуть раньше голоса
TAIL = 0.45       # и держится после реплики


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    root = Path(sys.argv[1])
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
            subprocess.run([str(PY), str(TTS), 'vera', '-', 'livetts', s['say'], str(wav)], check=True,
                           stdout=subprocess.DEVNULL)
        a = dur(wav)
        durs.append(LEAD + a + TAIL + X)          # X — запас на растворение в следующий кадр
        wavs.append(wav)
    # кадры с наездом
    for n, d in enumerate(durs, 1):
        frames = int(d * FPS)
        vf = (f"scale=2160:2700,zoompan=z='1+0.035*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s=1080x1350:fps={FPS},pad=1080:1920:0:285:color={BG},format=yuv420p")
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-t', f'{d:.3f}', '-i', str(root / 'frames' / f'{n:02d}.png'),
                        '-vf', vf, '-r', str(FPS), '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', str(clips / f'{n:02d}.mp4')],
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
        fc.append(f'{prev}[{n}:v]xfade=transition=dissolve:duration={X}:offset={starts[n]:.3f}{out}')
        prev = out
    # голос: каждая реплика на своём кадре
    k = len(durs)
    for n, w in enumerate(wavs):
        ins += ['-i', str(w)]
        fc.append(f'[{k + n}:a]adelay={int((starts[n] + LEAD) * 1000)}:all=1[a{n}]')
    fc.append(''.join(f'[a{n}]' for n in range(len(wavs))) + f'amix=inputs={len(wavs)}:normalize=0,apad[aout]')
    out = root / 'film.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', *ins, '-filter_complex', ';'.join(fc),
                    '-map', prev, '-map', '[aout]', '-t', f'{total:.3f}',
                    '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', str(out)], check=True)
    print(f'готово: {out} · {dur(out):.1f} с, сцен {len(durs)}')


if __name__ == '__main__':
    main()
