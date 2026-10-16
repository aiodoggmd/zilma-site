"""Вертикальный ролик 1080×1920 (Reels, VK Клипы, Shorts) из слайдов карусели и озвучки.

    python tools\\instagram\\make_video.py <папка слайдов> <папка озвучки> <выход.mp4>

Слайд NN.png звучит фразой NN.wav: держится столько, сколько длится фраза, плюс 0,6 с,
медленно приближается (×1,04) и на стыках гаснет в фон за 0,25 с. Нужен ffmpeg в PATH.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

BG = '0xfaf6f0'
FPS = 30
TAIL = 0.6
FADE = 0.25


def dur(f):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def main():
    slides, audio, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    pairs = []
    for png in sorted(slides.glob('[0-9][0-9].png')):
        wav = audio / f'{png.stem}.wav'
        if not wav.exists():
            sys.exit(f'нет озвучки {wav.name} для слайда {png.name}')
        pairs.append((png, wav))
    if not pairs:
        sys.exit('нет слайдов NN.png')
    tmp = Path(tempfile.mkdtemp(prefix='zilma-video-'))
    parts = []
    for png, wav in pairs:
        d = dur(wav) + TAIL
        frames = int(d * FPS)
        part = tmp / f'{png.stem}.mp4'
        vf = (f'scale=2160:2700,zoompan=z=\'1+0.04*on/{frames}\':x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\''
              f':d={frames}:s=1080x1350:fps={FPS},'
              f'pad=1080:1920:0:285:color={BG},'
              f'fade=t=in:st=0:d={FADE}:color={BG},fade=t=out:st={d - FADE:.2f}:d={FADE}:color={BG},format=yuv420p')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-i', str(png), '-i', str(wav),
                        '-vf', vf, '-af', f'apad=pad_dur={TAIL}', '-t', f'{d:.2f}',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000',
                        str(part)], check=True)
        parts.append(part)
        print(f'{png.name}: {d:.1f} с')
    lst = tmp / 'list.txt'
    lst.write_text(''.join(f"file '{p.as_posix()}'\n" for p in parts), encoding='utf-8')
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy',
                    '-movflags', '+faststart', str(out)], check=True)
    print(f'готово: {out} · {dur(out):.1f} с')


if __name__ == '__main__':
    main()
