// src/app/modules/language-learning/services/audio-recording.service.ts
import { Injectable, signal, Signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class AudioRecordingService {
  private mediaRecorder?: MediaRecorder;
  private audioChunks: Blob[] = [];

  private _recordingStatus = signal<boolean>(false);
  readonly recordingStatus: Signal<boolean> = this._recordingStatus.asReadonly();

  private _recordedAudio = signal<string | null>(null);
  readonly recordedAudio: Signal<string | null> = this._recordedAudio.asReadonly();

  async startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(stream);

      this.mediaRecorder.addEventListener('dataavailable', (event) => {
        this.audioChunks.push(event.data);
      });

      this.mediaRecorder.addEventListener('stop', () => {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
        const audioUrl = URL.createObjectURL(audioBlob);
        this._recordedAudio.set(audioUrl);
        this.audioChunks = [];
      });

      this.mediaRecorder.start();
      this._recordingStatus.set(true);
    } catch (error) {
      console.error('Error starting recording:', error);
      this._recordingStatus.set(false);
    }
  }

  stopRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
      this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
      this._recordingStatus.set(false);
    }
  }
}
