import { CommonModule } from "@angular/common";
import { Component, Input, Output, EventEmitter } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatIconModule } from "@angular/material/icon";
import { ExerciseBase } from "../../../../shared/models/exercise.model";
import { MinutesPipe } from "../../../../shared/pipes/minutes.pipe";

@Component({
  selector: 'app-exercise-base',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule, MinutesPipe],
  templateUrl: './exercise-base.component.html',
  styleUrls: ['./exercise-base.component.scss']
})
export class ExerciseBaseComponent {
  @Input() exercise: ExerciseBase | null = null;
  @Output() onPause = new EventEmitter<void>();
  @Output() onPrevious = new EventEmitter<void>();
  @Output() onNext = new EventEmitter<void>();
  @Output() onExit = new EventEmitter<void>();
}
