# Episode Save-to-Disk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recorded teleoperation episodes (two camera videos + a joint-samples metadata.json) currently dump into the browser's Downloads folder via three separate `<a download>` clicks. Make them save into a fixed, findable project location instead: `data/local/episodes/<timestamp>/`.

**Architecture:** Add a `POST /api/episodes` endpoint to the existing Express server (`server.ts`) using `multer` (memory storage) to receive the two video blobs plus a metadata JSON field in one multipart request, then write all three files to disk under `data/local/episodes/<sanitized-timestamp>/`. On the client, `GamepadVisionOverlay.tsx`'s `stopEpisodeRecording` POSTs there instead of triggering browser downloads, falling back to the original download behavior only if the request fails, so a recording is never silently lost.

**Tech Stack:** Express 4, multer (new dependency), TypeScript, React 19, native `fetch`/`FormData`.

## Global Constraints

- This repo has no test framework (no jest/vitest/pytest) — verification is `npm run lint` (`tsc --noEmit`), `npm run build`, and manual exercise, per `AGENTS.md`'s own Validation section. Tasks below use `tsc`/`curl`-based verification instead of unit tests to match this.
- Match existing `server.ts` conventions: try/catch route handlers, `res.status(n).json({ error })` on failure, dynamic `await (await import("node:fs/promises"))`-style fs access.
- Never commit files under `data/local/` — it must be gitignored, matching the existing `/data/external/` and `/data/experiments/` entries.
- Don't add authentication, retry queues, or transactional rollback on partial write failure — this is a single-user local dev tool; the client-side download fallback is the safety net, not server-side robustness.
- Follow the existing 2-space-indent, single-quote style already used in `server.ts` and `src/components/GamepadVisionOverlay.tsx`.

---

### Task 1: Add `multer` dependency

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json` (npm-managed, not hand-edited)

**Interfaces:**
- Produces: `multer` importable in `server.ts` as `import multer from "multer"`, with TypeScript types available via `@types/multer`.

- [ ] **Step 1: Install the runtime package**

Run: `npm install multer`

Expected: `package.json`'s `dependencies` gains a `"multer"` entry.

- [ ] **Step 2: Install the type definitions**

Run: `npm install --save-dev @types/multer`

Expected: `package.json`'s `devDependencies` gains a `"@types/multer"` entry, matching how `@types/express` sits alongside `express`.

- [ ] **Step 3: Verify install**

Run: `npm run lint`

Expected: passes with no new errors (multer isn't imported anywhere yet, so this just confirms the install didn't break anything).

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add multer for episode file uploads"
```

---

### Task 2: Add `POST /api/episodes` endpoint

**Files:**
- Modify: `server.ts:1` (imports)
- Modify: `server.ts` (add `episodeUpload` config near the other top-level consts, e.g. after `jointLimits`/`clamp`/`isRecord`, before `normalizeSequenceShape`)
- Modify: `server.ts:163-171` (insert the new route directly after the existing `/api/policy/preview` handler, before the `// AI Sequence Trajectory Generation Endpoint` comment)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `multer` from Task 1.
- Produces: `POST /api/episodes` accepting multipart fields `overview` (video file), `wrist` (video file), `metadata` (plain text field containing a JSON string with at least `startedAt: string`, `schemaVersion: number`, `observations`, `actions`). Responds `201 { episodeDir: string }` (a path relative to the repo root, e.g. `"data/local/episodes/2026-08-05T18-20-00-123Z"`) on success, or `4xx`/`500 { error: string }` on failure. Files land at `<episodeDir>/overview.<ext>`, `<episodeDir>/wrist.<ext>`, `<episodeDir>/metadata.json`, where `<ext>` is `mp4` or `webm` based on each file's actual mimetype.

- [ ] **Step 1: Add the `multer` import**

In `server.ts`, the current imports are:

```ts
import express from "express";
import path from "path";
import dotenv from "dotenv";
import { createServer as createViteServer } from "vite";
import { jsonrepair } from "jsonrepair";
```

Change to:

```ts
import express from "express";
import path from "path";
import dotenv from "dotenv";
import { createServer as createViteServer } from "vite";
import { jsonrepair } from "jsonrepair";
import multer from "multer";
```

- [ ] **Step 2: Add the multer upload config**

Find this block (the top-level consts before `normalizeSequenceShape`):

```ts
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
```

Add directly after it:

```ts

// Episode video uploads are buffered in memory, then written to disk in the
// /api/episodes handler once the request is fully parsed — this sidesteps
// multer's field-ordering requirement for disk-storage destination callbacks.
const episodeUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 512 * 1024 * 1024 } // 512MB/file cap — generous safety net for short local clips
});
```

- [ ] **Step 3: Add the route handler**

Find this block:

```ts
  app.get("/api/policy/preview", async (req, res) => {
    try {
      const previewPath = path.join(process.cwd(), "outputs", "policy-preview.json");
      const preview = JSON.parse(await (await import("node:fs/promises")).readFile(previewPath, "utf8"));
      res.json(preview);
    } catch {
      res.status(404).json({ error: "Generate the offline policy preview first." });
    }
  });

  // AI Sequence Trajectory Generation Endpoint
```

Change to:

```ts
  app.get("/api/policy/preview", async (req, res) => {
    try {
      const previewPath = path.join(process.cwd(), "outputs", "policy-preview.json");
      const preview = JSON.parse(await (await import("node:fs/promises")).readFile(previewPath, "utf8"));
      res.json(preview);
    } catch {
      res.status(404).json({ error: "Generate the offline policy preview first." });
    }
  });

  // Save a locally recorded teleoperation episode (two camera videos + a
  // commanded-joint-samples metadata.json) to disk. The client falls back to
  // browser downloads if this fails, so this stays simple: no transactional
  // rollback on a partial write failure.
  app.post(
    "/api/episodes",
    episodeUpload.fields([
      { name: "overview", maxCount: 1 },
      { name: "wrist", maxCount: 1 }
    ]),
    async (req, res) => {
      try {
        const files = req.files as Record<string, Express.Multer.File[]> | undefined;
        const overviewFile = files?.overview?.[0];
        const wristFile = files?.wrist?.[0];
        if (!overviewFile || !wristFile) {
          return res.status(400).json({ error: "Both overview and wrist video files are required." });
        }

        let metadata: Record<string, unknown>;
        try {
          metadata = JSON.parse(String(req.body.metadata));
        } catch {
          return res.status(400).json({ error: "metadata field must be valid JSON." });
        }
        if (
          typeof metadata.startedAt !== "string"
          || typeof metadata.schemaVersion !== "number"
          || !metadata.observations
          || !metadata.actions
        ) {
          return res.status(400).json({ error: "metadata is missing required fields (startedAt, schemaVersion, observations, actions)." });
        }

        const sanitized = (metadata.startedAt as string).replace(/[^a-zA-Z0-9-]/g, "-");
        const episodeName = sanitized.length > 0 ? sanitized : `episode-${Date.now()}`;
        const episodeDirRelative = path.join("data", "local", "episodes", episodeName);
        const episodeDirAbsolute = path.join(process.cwd(), episodeDirRelative);

        const fs = await import("node:fs/promises");
        await fs.mkdir(episodeDirAbsolute, { recursive: true });

        const writeEpisodeFile = async (label: string, filename: string, data: Buffer | string) => {
          try {
            await fs.writeFile(path.join(episodeDirAbsolute, filename), data);
          } catch (writeError) {
            throw new Error(`Failed to write ${label}: ${(writeError as Error).message}`);
          }
        };

        const extensionFor = (mimetype: string) => (mimetype.includes("mp4") ? "mp4" : "webm");
        await writeEpisodeFile("overview video", `overview.${extensionFor(overviewFile.mimetype)}`, overviewFile.buffer);
        await writeEpisodeFile("wrist video", `wrist.${extensionFor(wristFile.mimetype)}`, wristFile.buffer);
        await writeEpisodeFile("metadata.json", "metadata.json", JSON.stringify(metadata, null, 2));

        res.status(201).json({ episodeDir: episodeDirRelative });
      } catch (err: any) {
        console.error("Episode save error:", err);
        res.status(500).json({ error: err.message || "Failed to save episode to disk." });
      }
    }
  );

  // AI Sequence Trajectory Generation Endpoint
```

- [ ] **Step 4: Update `.gitignore`**

Current:

```
# Downloaded datasets and local experiment outputs
/data/external/
/data/experiments/
/outputs/
/.cache/
/.venv-lerobot/
```

Change to:

```
# Downloaded datasets and local experiment outputs
/data/external/
/data/experiments/
/data/local/
/outputs/
/.cache/
/.venv-lerobot/
```

- [ ] **Step 5: Typecheck**

Run: `npm run lint`

Expected: passes with no errors. If `Express.Multer.File` isn't recognized, confirm Task 1's `@types/multer` install actually completed (`grep multer package.json`).

- [ ] **Step 6: Manual verification — happy path**

Run: `npm run dev` (leave it running in one terminal), then in another terminal:

```bash
mkdir -p /tmp/episode-test
echo "fake video data" > /tmp/episode-test/overview.webm
echo "fake video data" > /tmp/episode-test/wrist.webm

curl -s -i -X POST http://localhost:3000/api/episodes \
  -F "overview=@/tmp/episode-test/overview.webm;type=video/webm" \
  -F "wrist=@/tmp/episode-test/wrist.webm;type=video/webm" \
  -F 'metadata={"schemaVersion":1,"startedAt":"2026-08-05T18:20:00.123Z","durationMs":1000,"observations":{},"actions":{}}'
```

Expected: `HTTP/1.1 201 Created` with body `{"episodeDir":"data/local/episodes/2026-08-05T18-20-00-123Z"}`.

Then run: `ls data/local/episodes/2026-08-05T18-20-00-123Z/`

Expected: `metadata.json  overview.webm  wrist.webm`, and `cat .../metadata.json` shows the JSON you posted.

- [ ] **Step 7: Manual verification — error paths**

```bash
# Missing a video file
curl -s -i -X POST http://localhost:3000/api/episodes \
  -F "overview=@/tmp/episode-test/overview.webm;type=video/webm" \
  -F 'metadata={"schemaVersion":1,"startedAt":"2026-08-05T18:21:00.000Z","durationMs":1000,"observations":{},"actions":{}}'
```
Expected: `HTTP/1.1 400`, body `{"error":"Both overview and wrist video files are required."}`.

```bash
# Invalid metadata JSON
curl -s -i -X POST http://localhost:3000/api/episodes \
  -F "overview=@/tmp/episode-test/overview.webm;type=video/webm" \
  -F "wrist=@/tmp/episode-test/wrist.webm;type=video/webm" \
  -F 'metadata=not-json'
```
Expected: `HTTP/1.1 400`, body `{"error":"metadata field must be valid JSON."}`.

Expected in both cases: the server process stays running (no crash) and `npm run dev`'s terminal shows no unhandled exception.

- [ ] **Step 8: Clean up test artifacts and commit**

```bash
rm -rf /tmp/episode-test data/local/episodes
git add server.ts .gitignore
git commit -m "feat: add POST /api/episodes endpoint to save recorded episodes to disk"
```

---

### Task 3: Rewire `GamepadVisionOverlay.tsx` to save via the server

**Files:**
- Modify: `src/components/GamepadVisionOverlay.tsx`

**Interfaces:**
- Consumes: `POST /api/episodes` contract from Task 2 (exact field names `overview`/`wrist`/`metadata`, response shape `{ episodeDir }` on 201, `{ error }` on failure).
- Produces: `saveStatus: 'idle' | 'saving' | 'saved' | 'error'` and `saveMessage: string | null` state, rendered in this component. No other component consumes these.

- [ ] **Step 1: Add save-status state**

Find:

```tsx
  const [isRecordingEpisode, setIsRecordingEpisode] = useState(false);
  const [recordingElapsedSeconds, setRecordingElapsedSeconds] = useState(0);
```

Change to:

```tsx
  const [isRecordingEpisode, setIsRecordingEpisode] = useState(false);
  const [recordingElapsedSeconds, setRecordingElapsedSeconds] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
```

- [ ] **Step 2: Reset save status when a new recording starts**

Find the start of `startEpisodeRecording`:

```ts
  const startEpisodeRecording = () => {
    const overview = cameraStreamsRef.current.overview;
    const wrist = cameraStreamsRef.current.wrist;
```

Change to:

```ts
  const startEpisodeRecording = () => {
    setSaveStatus('idle');
    setSaveMessage(null);
    const overview = cameraStreamsRef.current.overview;
    const wrist = cameraStreamsRef.current.wrist;
```

- [ ] **Step 3: Rewrite `stopEpisodeRecording`**

Find the whole current function:

```ts
  const stopEpisodeRecording = async () => {
    const session = recordingSessionRef.current;
    if (!session) return;

    recordingSessionRef.current = null;
    window.clearInterval(session.sampleTimerId);
    window.clearInterval(session.elapsedTimerId);
    setIsRecordingEpisode(false);
    setRecordingElapsedSeconds(0);

    await Promise.all((Object.values(session.recorders) as MediaRecorder[]).map((recorder) => new Promise<void>((resolve) => {
      if (recorder.state === 'inactive') {
        resolve();
        return;
      }
      recorder.addEventListener('stop', () => resolve(), { once: true });
      recorder.stop();
    })));

    const filePrefix = `so-arm100-episode-${session.startedAtIso.replace(/[:.]/g, '-')}`;
    const videoFiles = (['overview', 'wrist'] as const).map((role) => {
      const recorder = session.recorders[role];
      const mimeType = recorder.mimeType || 'video/webm';
      const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
      const filename = `${filePrefix}-${role}.${extension}`;
      downloadBlob(new Blob(session.chunks[role], { type: mimeType }), filename);
      return { role, filename, mimeType };
    });

    const metadata = {
      schemaVersion: 1,
      startedAt: session.startedAtIso,
      durationMs: Math.round(performance.now() - session.startedAtPerformanceMs),
      observations: {
        overview: { file: videoFiles[0], settings: session.cameraSettings.overview },
        wrist: { file: videoFiles[1], settings: session.cameraSettings.wrist }
      },
      actions: {
        type: 'commanded_joint_target',
        unit: { base: 'degrees', shoulder: 'degrees', elbow: 'degrees', wristPitch: 'degrees', wristRoll: 'degrees', gripper: 'percent' },
        sampleRateHz: 20,
        samples: session.samples
      },
      note: 'Joint samples are commanded UI targets, not measured follower-arm position telemetry.'
    };
    downloadBlob(new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' }), `${filePrefix}-metadata.json`);
  };
```

Replace with:

```ts
  const stopEpisodeRecording = async () => {
    const session = recordingSessionRef.current;
    if (!session) return;

    recordingSessionRef.current = null;
    window.clearInterval(session.sampleTimerId);
    window.clearInterval(session.elapsedTimerId);
    setIsRecordingEpisode(false);
    setRecordingElapsedSeconds(0);
    setSaveStatus('saving');
    setSaveMessage('Saving episode to the server…');

    await Promise.all((Object.values(session.recorders) as MediaRecorder[]).map((recorder) => new Promise<void>((resolve) => {
      if (recorder.state === 'inactive') {
        resolve();
        return;
      }
      recorder.addEventListener('stop', () => resolve(), { once: true });
      recorder.stop();
    })));

    const filePrefix = `so-arm100-episode-${session.startedAtIso.replace(/[:.]/g, '-')}`;
    const videoBlobs = (['overview', 'wrist'] as const).map((role) => {
      const recorder = session.recorders[role];
      const mimeType = recorder.mimeType || 'video/webm';
      const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
      return { role, mimeType, extension, blob: new Blob(session.chunks[role], { type: mimeType }) };
    });

    const metadata = {
      schemaVersion: 1,
      startedAt: session.startedAtIso,
      durationMs: Math.round(performance.now() - session.startedAtPerformanceMs),
      observations: {
        overview: { file: `overview.${videoBlobs[0].extension}`, settings: session.cameraSettings.overview },
        wrist: { file: `wrist.${videoBlobs[1].extension}`, settings: session.cameraSettings.wrist }
      },
      actions: {
        type: 'commanded_joint_target',
        unit: { base: 'degrees', shoulder: 'degrees', elbow: 'degrees', wristPitch: 'degrees', wristRoll: 'degrees', gripper: 'percent' },
        sampleRateHz: 20,
        samples: session.samples
      },
      note: 'Joint samples are commanded UI targets, not measured follower-arm position telemetry.'
    };

    // Browser download is the fallback path now, not the primary one — used
    // only if the server save fails, so a recorded demonstration is never
    // silently lost.
    const fallbackToDownload = (reason: string) => {
      videoBlobs.forEach(({ role, extension, blob }) => {
        downloadBlob(blob, `${filePrefix}-${role}.${extension}`);
      });
      downloadBlob(new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' }), `${filePrefix}-metadata.json`);
      setSaveStatus('error');
      setSaveMessage(`Could not save to the server (${reason}). Downloaded to your browser's Downloads folder instead.`);
    };

    try {
      const formData = new FormData();
      // Do not set a Content-Type header manually — fetch derives the
      // multipart boundary from the FormData instance itself.
      formData.append('metadata', JSON.stringify(metadata));
      videoBlobs.forEach(({ role, extension, blob }) => {
        formData.append(role, blob, `${role}.${extension}`);
      });

      const response = await fetch('/api/episodes', { method: 'POST', body: formData });
      if (!response.ok) {
        const body = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
        throw new Error(body.error || `HTTP ${response.status}`);
      }
      const result = await response.json() as { episodeDir: string };
      setSaveStatus('saved');
      setSaveMessage(`Episode saved to ${result.episodeDir}`);
    } catch (error) {
      fallbackToDownload(error instanceof Error ? error.message : 'unknown error');
    }
  };
```

- [ ] **Step 4: Render the save status and update the button label**

Find:

```tsx
      {cameraError && (
        <div className="flex items-start gap-2 rounded-sm border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
          <span>{cameraError}</span>
        </div>
      )}
      <div className="flex flex-col gap-3 rounded-sm border border-zinc-800 bg-zinc-950 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wider text-zinc-100">Demonstration Recorder</span>
            {isRecordingEpisode && <span className="bg-rose-500/15 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-300">REC {recordingElapsedSeconds}s</span>}
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">Records both videos and commanded joint targets at 20 Hz. It does not move the robot.</p>
        </div>
        <button
          onClick={isRecordingEpisode ? () => void stopEpisodeRecording() : startEpisodeRecording}
          disabled={!isRecordingEpisode && !cameraActive}
          className={`px-4 py-2 text-xs font-black uppercase tracking-tight transition disabled:cursor-not-allowed disabled:opacity-50 ${
            isRecordingEpisode
              ? 'border border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
              : 'border border-amber-400/40 bg-amber-400 text-zinc-950 hover:bg-amber-300'
          }`}
        >
          {isRecordingEpisode ? 'Stop & Download Episode' : 'Record Episode'}
        </button>
      </div>
    </div>
  );
};
```

Change to:

```tsx
      {cameraError && (
        <div className="flex items-start gap-2 rounded-sm border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
          <span>{cameraError}</span>
        </div>
      )}
      {saveStatus !== 'idle' && saveMessage && (
        <div className={`flex items-start gap-2 rounded-sm border px-3 py-2 text-xs ${
          saveStatus === 'error'
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-200'
            : saveStatus === 'saving'
            ? 'border-zinc-700 bg-zinc-900 text-zinc-300'
            : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
        }`}>
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{saveMessage}</span>
        </div>
      )}
      <div className="flex flex-col gap-3 rounded-sm border border-zinc-800 bg-zinc-950 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wider text-zinc-100">Demonstration Recorder</span>
            {isRecordingEpisode && <span className="bg-rose-500/15 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-300">REC {recordingElapsedSeconds}s</span>}
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">Records both videos and commanded joint targets at 20 Hz. It does not move the robot.</p>
        </div>
        <button
          onClick={isRecordingEpisode ? () => void stopEpisodeRecording() : startEpisodeRecording}
          disabled={!isRecordingEpisode && !cameraActive}
          className={`px-4 py-2 text-xs font-black uppercase tracking-tight transition disabled:cursor-not-allowed disabled:opacity-50 ${
            isRecordingEpisode
              ? 'border border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
              : 'border border-amber-400/40 bg-amber-400 text-zinc-950 hover:bg-amber-300'
          }`}
        >
          {isRecordingEpisode ? 'Stop & Save Episode' : 'Record Episode'}
        </button>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Typecheck and build**

Run: `npm run lint`

Expected: passes with no errors.

Run: `npm run build`

Expected: succeeds (this also catches issues the dev-only Vite path might not).

- [ ] **Step 6: Commit**

```bash
git add src/components/GamepadVisionOverlay.tsx
git commit -m "feat: save recorded episodes to the server instead of browser downloads"
```

---

### Task 4: Manual end-to-end verification (human-only, not agent-automatable)

This task cannot be completed by an agent — it requires two physical cameras attached and a person operating the UI. Do not mark this done based on Task 2/3's automated checks alone.

**Files:** None (verification only).

- [ ] **Step 1: Start the app**

Run: `npm run dev`, open the app in Chrome, go to the **Wireless Tele-Op & Vision** tab (`controlTab === 'teleop'`).

- [ ] **Step 2: Record a short real episode**

Click "Start Both Cameras", confirm both video feeds show live. Click "Record Episode", wait a few seconds, click "Stop & Save Episode".

Expected: the status box under the camera feeds shows "Saving episode to the server…" then updates to "Episode saved to data/local/episodes/…" — no browser download prompt should appear.

- [ ] **Step 3: Confirm the files on disk**

Run: `ls -la data/local/episodes/` and open the newest folder.

Expected: `overview.webm` (or `.mp4`), `wrist.webm` (or `.mp4`), and `metadata.json` are all present, the videos play, and `metadata.json` contains a non-empty `actions.samples` array.

- [ ] **Step 4: Confirm the fallback still works**

Stop the `npm run dev` server (so the POST will fail), record another short episode, and click "Stop & Save Episode" again.

Expected: the status box turns to the error style and explains it fell back to a browser download; three files should appear in the browser's actual Downloads folder, confirming no demonstration data is lost when the server is unreachable.
