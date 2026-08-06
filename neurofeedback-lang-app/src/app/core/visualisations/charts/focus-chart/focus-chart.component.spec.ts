import { ComponentFixture, TestBed } from '@angular/core/testing';

import { FocusChartComponent } from './focus-chart.component';

describe('FocusChartComponent', () => {
  let component: FocusChartComponent;
  let fixture: ComponentFixture<FocusChartComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FocusChartComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(FocusChartComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
