// src/app/modules/capture/services/video-recorder.service.ts
import { Injectable, inject } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { CaptureModeService } from './capture-mode.service';

@Injectable({ providedIn: 'root' })
export class VideoRecorderService {
  private mode = inject(CaptureModeService);
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private stopResolve: ((blob: Blob) => void) | null = null;
  private recordingMimeType = 'video/webm';

  private cameraReady = new BehaviorSubject<boolean>(false);
  readonly cameraReady$ = this.cameraReady.asObservable();

  get previewStream(): MediaStream | null {
    return this.stream;
  }

  async requestCamera(): Promise<void> {
    if (this.mode.isMock()) {
      await new Promise(r => setTimeout(r, 500));
      this.cameraReady.next(true);
      return;
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
    this.cameraReady.next(true);
  }

  startRecording(): void {
    if (this.mode.isMock()) return;
    if (!this.stream) throw new Error('Camera not ready — call requestCamera() first');
    this.chunks = [];
    this.recordingMimeType = this.pickMimeType();
    this.recorder = new MediaRecorder(this.stream, { mimeType: this.recordingMimeType });
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start(1000); // collect a chunk every 1 s
  }

  stopRecording(): Promise<Blob> {
    if (this.mode.isMock()) return Promise.resolve(new Blob());
    if (!this.recorder) throw new Error('Video recorder is not running');
    return new Promise((resolve) => {
      this.stopResolve = resolve;
      this.recorder!.onstop = () => {
        const blob = new Blob(this.chunks, { type: this.recordingMimeType });
        this.stopResolve?.(blob);
      };
      this.recorder!.stop();
    });
  }

  releaseCamera(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.cameraReady.next(false);
  }

  private pickMimeType(): string {
    const candidates = [
      'video/mp4; codecs=avc1',
      'video/mp4',
      'video/webm; codecs=vp9',
      'video/webm; codecs=vp8',
      'video/webm',
    ];
    const supported = candidates.find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
    if (!supported) throw new Error('No supported video recording format found');
    return supported;
  }
}
