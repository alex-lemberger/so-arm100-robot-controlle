import { CommonModule } from '@angular/common';
import { Component, Input, signal, computed, effect, OnDestroy, Signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, Params } from '@angular/router';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs/operators';
import {
  SpeakingExercise,
  ExerciseType,
} from '../../../../shared/models/exercise.model';
import { AudioRecordingService } from '../../services/audio-recording.service';
import { ExerciseActions, ExerciseState } from '../../state/exercise.state';
import { ExerciseBaseComponent } from '../exercise-base/exercise-base.component';

@Component({
  selector: 'app-speaking-exercise',
  standalone: true,
  imports: [
    CommonModule,
    ExerciseBaseComponent,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './speaking-exercise.component.html',
  styleUrls: ['./speaking-exercise.component.scss'],
})
export class SpeakingExerciseComponent implements OnDestroy {
  @Input() exerciseId = signal<string | undefined>(undefined);

  isRecording: Signal<boolean>;
  isPlaying = signal(false);
  recordedAudioUrl: Signal<string | null>;
  recordingDuration = signal(0);
  currentPlayingAudioUrl = signal<string | null>(null);

  exercise: Signal<SpeakingExercise | null>;
  loading: Signal<boolean>;
  error: Signal<string | null>;

  currentExerciseForBase: Signal<SpeakingExercise | null> = computed(() => {
    const ex = this.exercise();
    if (ex) {
      return ex;
    }
    return null;
  });

  private recordingInterval?: ReturnType<typeof setInterval>;
  private audioElement?: HTMLAudioElement;
  private routeId: Signal<string | undefined>;

  constructor(
    private audioRecordingService: AudioRecordingService,
    private store: Store,
    private route: ActivatedRoute,
    private router: Router
  ) {
    this.exercise = toSignal(this.store.select(ExerciseState.speakingExercise), { initialValue: null });
    this.loading = toSignal(this.store.select(ExerciseState.isLoading), { initialValue: false });
    this.error = toSignal(this.store.select(ExerciseState.error), { initialValue: null });

    this.isRecording = this.audioRecordingService.recordingStatus;
    this.recordedAudioUrl = this.audioRecordingService.recordedAudio;
    this.routeId = toSignal(this.route.params.pipe(map((params: Params) => params['id'])), { initialValue: undefined });

    // Effect to handle exerciseId input and route params
    effect(() => {
      const id = this.exerciseId();
      const routeParamId = this.routeId();

      const currentId = id || routeParamId;

      if (currentId) {
        this.store.dispatch(new ExerciseActions.FetchById(currentId as string));
      } else {
        console.warn('No exercise ID provided, initializing default exercise.');
        this.initDefaultExercise();
      }
    });

    // Effect to manage recording timer
    effect(() => {
      if (this.isRecording()) {
        this.startRecordingTimer();
      } else {
        this.stopRecordingTimer();
      }
    });

    // Effect to manage audio playback
    effect(() => {
      const url = this.currentPlayingAudioUrl();
      if (url) {
        this.isPlaying.set(true);
        this.audioElement = new Audio(url);

        const onEnded = () => {
          this.isPlaying.set(false);
          this.currentPlayingAudioUrl.set(null); // Clear the URL when ended
          this.audioElement?.removeEventListener('ended', onEnded);
          this.audioElement?.removeEventListener('error', onError);
          this.audioElement = undefined;
        };

        const onError = (e: Event) => {
          console.error('Error playing audio:', e);
          this.isPlaying.set(false);
          this.currentPlayingAudioUrl.set(null); // Clear the URL on error
          this.audioElement?.removeEventListener('ended', onEnded);
          this.audioElement?.removeEventListener('error', onError);
          this.audioElement = undefined;
        };

        this.audioElement.addEventListener('ended', onEnded);
        this.audioElement.addEventListener('error', onError);

        this.audioElement.play().catch(error => {
          console.error('Error playing audio promise:', error);
          this.isPlaying.set(false);
          this.currentPlayingAudioUrl.set(null); // Clear the URL on promise rejection
          this.audioElement?.removeEventListener('ended', onEnded);
          this.audioElement?.removeEventListener('error', onError);
          this.audioElement = undefined;
        });
      } else {
        // If URL becomes null, stop and clean up any playing audio
        if (this.audioElement) {
          this.audioElement.pause();
          this.isPlaying.set(false);
          this.audioElement = undefined;
        }
      }
    });
  }

  playExample() {
    if (this.exercise() && this.exercise()?.audioUrl) {
      this.currentPlayingAudioUrl.set(this.exercise()!.audioUrl || null);
    } else {
      console.warn('Cannot play example: No audio URL available');
    }
  }

  startRecording() {
    this.audioRecordingService.startRecording();
  }

  playRecording() {
    if (this.recordedAudioUrl()) {
      this.currentPlayingAudioUrl.set(this.recordedAudioUrl()!);
    }
  }

  stopRecording() {
    this.audioRecordingService.stopRecording();
  }

  handlePause() {
    if (this.isRecording()) {
      this.stopRecording();
    }
    // If audio is playing, stop it by clearing the currentPlayingAudioUrl signal
    if (this.isPlaying()) {
      this.currentPlayingAudioUrl.set(null);
    }
    if (this.exercise() && this.exercise()?.id) {
      this.store.dispatch(new ExerciseActions.Pause(this.exercise()!.id));
    }
  }

  handlePrevious() {
    if (this.exercise() && this.exercise()?.id) {
      this.store.dispatch(
        new ExerciseActions.NavigateToPrevious(this.exercise()!.id)
      );
    }
  }

  handleNext() {
    if (this.exercise() && this.exercise()?.id) {
      this.store.dispatch(new ExerciseActions.NavigateToNext(this.exercise()!.id));
    }
  }

  navigateBack() {
    this.router.navigate(['/exercises']);
  }

  private startRecordingTimer() {
    this.recordingDuration.set(0);
    this.recordingInterval = setInterval(() => {
      this.recordingDuration.update(val => val + 1);
    }, 1000);
  }

  private stopRecordingTimer() {
    if (this.recordingInterval) {
      clearInterval(this.recordingInterval);
      this.recordingDuration.set(0);
    }
  }

  ngOnDestroy() {
    this.stopRecordingTimer();

    if (this.audioElement) {
      this.audioElement.pause();
      this.audioElement = undefined;
    }
  }

  // Helper method to initialize a default exercise for development/testing
  private initDefaultExercise(): void {
    const defaultExercise: SpeakingExercise = {
      id: 'default',
      title: 'Basic Verbs',
      type: ExerciseType.SPEAKING,
      duration: 900, // 15 minutes
      progress: {
        current: 1,
        total: 12,
      },
      focusLevel: 85,
      phrase: 'Ich möchte einen Kaffee, bitte.',
      audioUrl: '/assets/audio/sample.mp3',
      status: 'active',
    };

    // Set the default exercise in state
    this.store.dispatch(
      new ExerciseActions.SetCurrent(defaultExercise)
    );
  }
}