import { BrainMetrics, SessionData, CorrelationData } from "./dashboard.model";

export namespace DashboardActions {
  export class FetchMetrics {
    static readonly type = '[Dashboard] Fetch Metrics';
    constructor(public dateRange?: { start: Date; end: Date }) {}
  }

  export class UpdateBrainMetrics {
    static readonly type = '[Dashboard] Update Brain Metrics';
    constructor(public metrics: BrainMetrics) {}
  }

  export class UpdateSessionData {
    static readonly type = '[Dashboard] Update Session Data';
    constructor(public sessionData: SessionData) {}
  }

  export class UpdateCorrelationData {
    static readonly type = '[Dashboard] Update Correlation Data';
    constructor(public correlationData: CorrelationData[]) {}
  }

  export class SetError {
    static readonly type = '[Dashboard] Set Error';
    constructor(public error: string) {}
  }
}
