import { Injectable } from '@angular/core';
import { State, Action, StateContext, Selector } from '@ngxs/store';
import { tap, catchError } from 'rxjs/operators';
import { DashboardActions } from './dashboard.actions';
import { DashboardStateModel } from './dashboard.model';
import { DashboardService } from '../../../../dashboard/services/dashboard.service';


@State<DashboardStateModel>({
  name: 'dashboard',
  defaults: {
    brainMetrics: null,
    sessionData: null,
    correlationData: [],
    focusData: [],
    loading: false,
    error: null,
    lastUpdated: null
  }
})
@Injectable()
export class DashboardState {
  constructor(private dashboardService: DashboardService) {}

  @Selector()
  static getBrainMetrics(state: DashboardStateModel) {
    return state.brainMetrics;
  }

  @Selector()
  static getSessionData(state: DashboardStateModel) {
    return state.sessionData;
  }

  @Selector()
  static getCorrelationData(state: DashboardStateModel) {
    return state.correlationData;
  }

  @Selector()
  static getFocusData(state: DashboardStateModel) {
    return state.focusData;
  }

  @Selector()
  static isLoading(state: DashboardStateModel) {
    return state.loading;
  }

  @Selector()
  static getError(state: DashboardStateModel) {
    return state.error;
  }

  @Action(DashboardActions.FetchMetrics)
  fetchMetrics(
    { patchState, dispatch }: StateContext<DashboardStateModel>,
    { dateRange }: DashboardActions.FetchMetrics
  ) {
    patchState({ loading: true });

    const userId = 'someUserId'; // Replace with actual user ID
    return this.dashboardService.fetchMetrics(userId, dateRange).pipe(
      tap(metrics => {
        dispatch(new DashboardActions.UpdateBrainMetrics(metrics));
      }),
      catchError(error => {
        dispatch(new DashboardActions.SetError(error.message));
        throw error;
      })
    );
  }

  @Action(DashboardActions.UpdateBrainMetrics)
  updateBrainMetrics(
    { patchState }: StateContext<DashboardStateModel>,
    { metrics }: DashboardActions.UpdateBrainMetrics
  ) {
    patchState({
      brainMetrics: metrics,
      loading: false,
      lastUpdated: new Date()
    });
  }

  @Action(DashboardActions.UpdateSessionData)
  updateSessionData(
    { patchState }: StateContext<DashboardStateModel>,
    { sessionData }: DashboardActions.UpdateSessionData
  ) {
    patchState({
      sessionData,
      lastUpdated: new Date()
    });
  }

  @Action(DashboardActions.UpdateCorrelationData)
  updateCorrelationData(
    { patchState }: StateContext<DashboardStateModel>,
    { correlationData }: DashboardActions.UpdateCorrelationData
  ) {
    patchState({
      correlationData,
      lastUpdated: new Date()
    });
  }

  @Action(DashboardActions.SetError)
  setError(
    { patchState }: StateContext<DashboardStateModel>,
    { error }: DashboardActions.SetError
  ) {
    patchState({
      error,
      loading: false
    });
  }
}
