import sys
import av

video_path, ts, out_path = sys.argv[1], float(sys.argv[2]), sys.argv[3]
container = av.open(video_path)
stream = container.streams.video[0]
target_pts = max(0, ts - 0.5)
container.seek(int(target_pts / stream.time_base), stream=stream)
last_frame = None
for frame in container.decode(stream):
    if float(frame.pts * stream.time_base) > ts:
        break
    last_frame = frame
last_frame.to_image().save(out_path)
print(f"saved {out_path} at ts~{ts}")
