// src/app/modules/capture/services/eeg-buffer.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subscription } from 'rxjs';
import { EegReading } from '../../../core/neurofeedback/brain-device';

@Injectable({ providedIn: 'root' })
export class EegBufferService {
  private buffers: number[][] = [[], [], [], []];
  private sub: Subscription | null = null;

  startRecording(rawEeg$: Observable<EegReading>): void {
    this.sub?.unsubscribe();
    this.buffers = [[], [], [], []];
    this.sub = rawEeg$.subscribe(reading => {
      if (reading.electrode >= 0 && reading.electrode < 4) {
        this.buffers[reading.electrode].push(...reading.samples);
      }
    });
  }

  stopRecording(): Float32Array | null {
    this.sub?.unsubscribe();
    this.sub = null;
    const total = this.buffers.reduce((sum, buf) => sum + buf.length, 0);
    if (total === 0) {
      this.buffers = [[], [], [], []];
      return null;
    }
    // Layout: [ch0_samples | ch1_samples | ch2_samples | ch3_samples]
    const result = new Float32Array(total);
    let offset = 0;
    for (const buf of this.buffers) {
      result.set(buf, offset);
      offset += buf.length;
    }
    this.buffers = [[], [], [], []];
    return result;
  }
}