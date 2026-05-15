import os
os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'
import pickle
from utils.video_reader import VideoReader
from evs.event_detector import EventDetector, DVSCoordinate
from evs.event_encoder import EventEncoder
from evs.event_decoder import EventFrameReconstructor
from h264.encoder import InMemoryH264Encoder

print('Testing Stage 6 file save/load...')

with VideoReader(source='video_test.mp4', target_size=(640, 480)) as reader:
    width, height = reader.target_size
    fps = int(reader.fps)
    detector = EventDetector(threshold=20.0, min_area=0, use_adaptive_threshold=False, blur_kernel=1, use_log_space=True, compare_with_previous=True, refractory_period=0.005, is_dvs_mode=True)
    h264_encoder = InMemoryH264Encoder(width, height, fps=fps)
    event_encoder = EventEncoder(width, height)
    
    packets = []
    frame_idx = 0
    
    for frame in reader.get_frames(max_frames=5):
        frame_idx += 1
        current_time = frame_idx / fps
        is_keyframe = (frame_idx == 1)
        events = detector.detect(frame, current_time=current_time, frame_idx=frame_idx)
        
        if is_keyframe:
            h264_data = h264_encoder.encode_i_frame(frame)
            packet = event_encoder.encode_keyframe(frame, frame_idx=frame_idx, i_frame_data=h264_data, timestamp_ms=int(current_time * 1000))
            label = "KEYFRAME"
        else:
            packet = event_encoder.encode_events(events, frame, include_aer=True, timestamp_ms=int(current_time * 1000))
            label = "EVENT"
        
        packets.append(packet)
        print(f'  Frame {frame_idx}: {label}, events={len(packet.dvs_events)}')
    
    data = {'width': width, 'height': height, 'packets': packets}
    with open('test_output.evs', 'wb') as f:
        pickle.dump(data, f)
    size = os.path.getsize('test_output.evs')
    print(f'  Saved: test_output.evs, size={size} bytes')

print('\n  Loading...')
with open('test_output.evs', 'rb') as f:
    loaded_data = pickle.load(f)

reconstructor = EventFrameReconstructor(width=loaded_data['width'], height=loaded_data['height'], log_threshold=20.0 / 255.0)
reconstructed = None

for i, packet in enumerate(loaded_data['packets']):
    if packet.is_keyframe:
        reconstructed = reconstructor.decode_keyframe(packet.i_frame_data)
        shape = reconstructed.shape if reconstructed is not None else None
        print(f'  Frame {packet.frame_idx}: KEYFRAME decoded, shape={shape}')
    else:
        if reconstructed is not None and packet.dvs_events:
            dvs_coords = [DVSCoordinate(x=e['x'], y=e['y'], event_type=e['event_type']) for e in packet.dvs_events]
            reconstructed = reconstructor.reconstruct_frame(prev_frame=reconstructed, events=dvs_coords, reconstruction_mode='log_space')
            print(f'  Frame {packet.frame_idx}: EVENT reconstructed, shape={reconstructed.shape}')

os.remove('test_output.evs')
print('\nStage 6 file save/load test PASSED!')
