// src/app/modules/capture/services/capture-upload.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SupabaseCaptureService } from './supabase-capture.service';

export interface UploadPaths {
  videoPath: string;
  imuLeftPath: string;
  imuRightPath: string;
  eegPath: string | null;
}

@Injectable({ providedIn: 'root' })
export class CaptureUploadService {
  private progressSubject = new BehaviorSubject<number>(0);
  readonly progress$ = this.progressSubject.asObservable();

  constructor(private supabaseCapture: SupabaseCaptureService) {}

  async uploadSession(
    sessionId: string,
    video: Blob,
    imuLeft: Float32Array,
    imuRight: Float32Array,
    eeg: Float32Array | null,
  ): Promise<UploadPaths> {
    this.progressSubject.next(0);

    const videoExtension = video.type.includes('webm') ? 'webm' : 'mp4';
    const videoPath = `captures/${sessionId}/video.${videoExtension}`;
    const imuLeftPath = `captures/${sessionId}/imu_left.bin`;
    const imuRightPath = `captures/${sessionId}/imu_right.bin`;
    const eegPath = eeg ? `captures/${sessionId}/eeg.bin` : null;

    let videoBytes = 0, imuLeftBytes = 0, imuRightBytes = 0, eegBytes = 0;
    const totalBytes = video.size + imuLeft.byteLength + imuRight.byteLength + (eeg?.byteLength ?? 0);

    const updateProgress = () => {
      const done = videoBytes + imuLeftBytes + imuRightBytes + eegBytes;
      this.progressSubject.next(totalBytes === 0 ? 100 : Math.round((done / totalBytes) * 100));
    };

    const uploads: Promise<void>[] = [
      this.supabaseCapture.uploadFile(videoPath, video,
        n => { videoBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuLeftPath, new Blob([imuLeft]),
        n => { imuLeftBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuRightPath, new Blob([imuRight]),
        n => { imuRightBytes = n; updateProgress(); }),
    ];

    if (eeg && eegPath) {
      uploads.push(
        this.supabaseCapture.uploadFile(eegPath, new Blob([eeg]),
          n => { eegBytes = n; updateProgress(); }),
      );
    }

    await Promise.all(uploads);
    this.progressSubject.next(100);
    return { videoPath, imuLeftPath, imuRightPath, eegPath };
  }
}
