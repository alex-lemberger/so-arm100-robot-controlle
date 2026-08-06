// src/app/modules/capture/state/capture.actions.ts
export namespace CaptureActions {
  export class StartSetup {
    static readonly type = '[Capture] Start Setup';
  }

  export class SetWorker {
    static readonly type = '[Capture] Set Worker';
    constructor(public workerToken: string) {}
  }

  export class SetTask {
    static readonly type = '[Capture] Set Task';
    constructor(public taskType: string, public taskLabel: string) {}
  }

  export class StartRecording {
    static readonly type = '[Capture] Start Recording';
    constructor(public sessionId: string) {}
  }

  export class StopRecording {
    static readonly type = '[Capture] Stop Recording';
  }

  export class UploadProgress {
    static readonly type = '[Capture] Upload Progress';
    constructor(public progress: number) {}
  }

  export class UploadComplete {
    static readonly type = '[Capture] Upload Complete';
  }

  export class UploadFailed {
    static readonly type = '[Capture] Upload Failed';
    constructor(public error: string) {}
  }

  export class Reset {
    static readonly type = '[Capture] Reset';
  }

  export class AdvanceToTask {
    static readonly type = '[Capture] Advance To Task';
  }
}