from pathlib import Path

import typer

app = typer.Typer(help="Human-task dataset pipeline (v0.1 synthetic spine)", no_args_is_help=True)


@app.command()
def synth(out: Path = typer.Option(..., "--out"), seed: int = 0, force: bool = False) -> None:
    """Generate a synthetic session."""
    from htdp.synth.generate import generate_session

    try:
        d = generate_session(out, seed=seed, force=force)
    except FileExistsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def ingest(
    xdf_file: Path,
    sidecar: Path,
    out: Path = typer.Option(..., "--out"),
    force: bool = False,
) -> None:
    """Ingest an LSL .xdf recording into a raw session folder."""
    from pydantic import ValidationError

    from htdp.ingest.mapping import MappingError
    from htdp.ingest.reader import IngestUnavailable
    from htdp.ingest.session import ingest_xdf

    try:
        d = ingest_xdf(xdf_file, sidecar, out, force=force)
    except (IngestUnavailable, MappingError, ValidationError, FileExistsError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def ingest_video(
    session_dir: Path,
    mp4_file: Path,
    sidecar: Path,
    force: bool = False,
) -> None:
    """Augment a raw session with a video file (registers it in device_config)."""
    from pydantic import ValidationError

    from htdp.ingest.video import VideoIngestError, ingest_video as _ingest_video

    try:
        d = _ingest_video(session_dir, mp4_file, sidecar, force=force)
    except (VideoIngestError, ValidationError, FileNotFoundError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def export_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a raw session to a BIDS dataset tree (Motion-BIDS + BrainVision EEG-BIDS)."""
    from htdp.export.bids import BidsExportError, export_motion_bids

    try:
        d = export_motion_bids(raw_dir, out_dir, force=force)
    except BidsExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a packaged release to a multi-subject BIDS dataset."""
    from htdp.export.bids import BidsExportError, export_release_bids as _export_release_bids

    try:
        d = _export_release_bids(release_dir, out_dir, force=force)
    except BidsExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def export_release_rosbag(release_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a packaged release to one rosbag2 (mcap) bag per session."""
    from htdp.export.rosbag import RosbagExportError, export_release_rosbag as _export

    try:
        d = _export(release_dir, out_dir, force=force)
    except RosbagExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")


@app.command()
def validate(raw_dir: Path) -> None:
    """Validate a raw session folder."""
    from htdp.validate import validate_session

    problems = validate_session(raw_dir)
    if problems:
        for p in problems:
            typer.echo(f"FAIL: {p}", err=True)
        raise typer.Exit(1)
    typer.echo("OK")


@app.command()
def process(raw_dir: Path) -> None:
    """Process a raw session into Parquet."""
    from htdp.processing.extract import process_session

    try:
        out = process_session(raw_dir, Path("data/processed"))
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {out}")


@app.command()
def qc(processed_dir: Path) -> None:
    """Generate a QC report."""
    from htdp.qc.checks import run_qc

    report = run_qc(processed_dir)
    typer.echo(f"overall: {report['overall']}")


@app.command()
def package(
    session_ids: list[str],
    release: str = typer.Option(...),
    profile: str = typer.Option(...),
) -> None:
    """Package a dataset release (consent-gated)."""
    from htdp.release.package import package_release, ConsentError
    from htdp.schemas.enums import ReleaseProfile

    try:
        out = package_release(
            session_ids,
            release,
            ReleaseProfile(profile),
            Path("data/raw"),
            Path("data/releases"),
        )
    except ConsentError as exc:
        typer.echo(f"CONSENT BLOCK: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"wrote {out}")


@app.command()
def replay(release_dir: Path) -> None:
    """Replay a packaged release in MuJoCo."""
    from htdp.replay.player import replay_release, ReplayUnavailable

    try:
        frames = replay_release(release_dir)
    except ReplayUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"stepped {frames} frames")


@app.command()
def replay_ik(
    release_dir: Path,
    max_steps: int = 50,
    out: Path | None = typer.Option(None, "--out"),
    force: bool = typer.Option(False, "--force"),
    orientation_cost: float = typer.Option(0.0, "--orientation-cost"),
) -> None:
    """Drive a robot arm along a release's wrist path via IK (headless)."""
    from htdp.replay.ik import IkUnavailable, replay_release_ik, write_ik_trajectory

    try:
        result = replay_release_ik(
            release_dir, max_steps=max_steps, orientation_cost=orientation_cost
        )
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"stepped {len(result.joint_trajectory)} steps, "
        f"max tracking error {result.max_error:.4f} m, "
        f"max orientation error {result.max_orientation_error:.4f} rad"
    )
    if out is not None:
        try:
            written = write_ik_trajectory(result, out, force=force)
        except FileExistsError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"wrote {written} ({len(result.joint_trajectory)} steps)")


@app.command(name="sim-task")
def sim_task(
    video: Path | None = typer.Option(None, "--video", help="write demo MP4 to this path"),
    force: bool = typer.Option(False, "--force", help="overwrite an existing video"),
) -> None:
    """Run the SO-ARM100 pick-and-place sim episode; print metrics, optionally render."""
    from htdp.replay.episode import run_episode
    from htdp.replay.ik import IkUnavailable

    try:
        result = run_episode()
        if video is not None:
            from htdp.replay.render import render_episode

            render_episode(video, force=force)
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    except FileExistsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"place_error_m={result.place_error:.4f} grasp_dist_m={result.grasp_dist:.4f} "
        f"frames={result.frames_stepped}"
    )
    if video is not None:
        typer.echo(f"wrote {video}")


@app.command(name="render-physics")
def render_physics(
    video: Path = typer.Option(..., "--video", help="write the MP4 to this path"),
    x: float = typer.Option(0.50, "--x", help="cube start x"),
    y: float = typer.Option(-0.15, "--y", help="cube start y"),
    camera: str = typer.Option("front", "--camera", help="named scene camera"),
    force: bool = typer.Option(False, "--force", help="overwrite an existing video"),
) -> None:
    """Render the physics friction-grasp episode from a named camera to an MP4."""
    from htdp.replay.ik import IkUnavailable

    try:
        from htdp.replay.render import render_physics_episode

        render_physics_episode(video, cube_xy=(x, y), camera=camera, force=force)
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    except FileExistsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {video}")


@app.command(name="gen-demos")
def gen_demos(
    out: Path = typer.Option(..., "--out", help="dataset output directory"),
    n_train: int = typer.Option(100, "--n-train"),
    n_test: int = typer.Option(25, "--n-test"),
    seed: int = typer.Option(0, "--seed"),
    domain_randomize: bool = typer.Option(
        False, "--domain-randomize", help="C1: perturb light/table/camera/cube per episode"
    ),
) -> None:
    """Generate randomized physics pick-place demos (friction grasp) in LeRobotDataset format."""
    try:
        from htdp.learn.dataset import generate_demos

        generate_demos(
            out, n_train=n_train, n_test=n_test, seed=seed, domain_randomize=domain_randomize
        )
    except (ImportError, ModuleNotFoundError) as exc:
        from htdp.learn.errors import LearnUnavailable

        typer.echo(f"error: {LearnUnavailable()}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote demos to {out} (train={n_train} test={n_test})")


@app.command(name="train-policy")
def train_policy(
    demos: Path = typer.Option(..., "--demos", help="dataset directory from gen-demos"),
    out: Path = typer.Option(..., "--out", help="checkpoint path (policy.pt)"),
    steps: int = typer.Option(3000, "--steps"),
) -> None:
    """Train the ACT imitation policy on generated demos."""
    try:
        from htdp.learn.train import pick_device, train
    except ImportError as exc:
        from htdp.learn.errors import LearnUnavailable

        typer.echo(f"error: {LearnUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    train(demos, out, steps=steps)
    typer.echo(f"trained on {pick_device()}; wrote {out}")


@app.command(name="eval-policy")
def eval_policy(
    demos: Path = typer.Option(..., "--demos", help="dataset dir (for test_positions.json)"),
    policy: Path = typer.Option(..., "--policy", help="checkpoint path"),
    out: Path | None = typer.Option(None, "--out", help="optional report JSON path"),
    n_positions: int | None = typer.Option(
        None,
        "--n-positions",
        help="evaluate at N freshly sampled positions instead of test_positions.json",
    ),
    eval_seed: int = typer.Option(2000, "--eval-seed", help="seed for --n-positions sampling"),
) -> None:
    """Roll out the policy on held-out positions; report success-rate vs scripted baseline."""
    try:
        from htdp.learn.eval import eval_positions, evaluate
    except ImportError as exc:
        from htdp.learn.errors import LearnUnavailable

        typer.echo(f"error: {LearnUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    positions = eval_positions(demos, n_positions, eval_seed=eval_seed)
    report = evaluate(policy, positions, out_path=out)
    p, b = report["policy"], report["baseline"]
    typer.echo(
        f"policy: success={p['success_rate']:.2f} ci95=[{p['ci95'][0]:.2f},{p['ci95'][1]:.2f}] "
        f"place_err={p['mean_place_error']:.4f} n={p['n']} | "
        f"baseline: success={b['success_rate']:.2f} place_err={b['mean_place_error']:.4f}"
    )


@app.command(name="train-visuomotor")
def train_visuomotor_cmd(
    demos: Path = typer.Option(..., "--demos", help="dataset directory from gen-demos"),
    out: Path = typer.Option(..., "--out", help="checkpoint path (vm.pt)"),
    steps: int = typer.Option(6000, "--steps"),
) -> None:
    """Train the visuomotor ACT policy (front image + proprio, no privileged cube/target xyz)."""
    try:
        from htdp.learn.train import pick_device, train_visuomotor
    except ImportError as exc:
        from htdp.learn.errors import LearnUnavailable

        typer.echo(f"error: {LearnUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    train_visuomotor(demos, out, steps=steps)
    typer.echo(f"trained on {pick_device()}; wrote {out}")


@app.command(name="eval-visuomotor")
def eval_visuomotor_cmd(
    demos: Path = typer.Option(..., "--demos", help="dataset dir (for test_positions.json)"),
    policy: Path = typer.Option(..., "--policy", help="visuomotor checkpoint path"),
    out: Path | None = typer.Option(None, "--out", help="optional report JSON path"),
    n_positions: int | None = typer.Option(
        None,
        "--n-positions",
        help="evaluate at N freshly sampled positions instead of test_positions.json",
    ),
    eval_seed: int = typer.Option(2000, "--eval-seed", help="seed for --n-positions sampling"),
    domain_randomize: bool = typer.Option(
        False,
        "--domain-randomize",
        help="C1: eval under novel per-position scene randomization (light/table/camera/cube)",
    ),
    dr_seed_base: int = typer.Option(
        5000, "--dr-seed-base", help="base seed for --domain-randomize (position i uses base+i)"
    ),
) -> None:
    """Roll out the visuomotor policy on held-out positions vs the physics baseline."""
    try:
        from htdp.learn.eval import eval_positions, evaluate_visuomotor
    except ImportError as exc:
        from htdp.learn.errors import LearnUnavailable

        typer.echo(f"error: {LearnUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    positions = eval_positions(demos, n_positions, eval_seed=eval_seed)
    report = evaluate_visuomotor(
        policy,
        positions,
        out_path=out,
        domain_randomize=domain_randomize,
        dr_seed_base=dr_seed_base,
    )
    p, b = report["policy"], report["baseline"]
    typer.echo(
        f"visuomotor: success={p['success_rate']:.2f} ci95=[{p['ci95'][0]:.2f},{p['ci95'][1]:.2f}] "
        f"place_err={p['mean_place_error']:.4f} n={p['n']} | "
        f"baseline: success={b['success_rate']:.2f} place_err={b['mean_place_error']:.4f}"
    )


@app.command()
def catalog(sessions_dir: Path, out_path: Path) -> None:
    """Build a multi-session Parquet catalog from a raw sessions directory."""
    import polars as pl

    from htdp.catalog import CatalogError, build_catalog

    try:
        out = build_catalog(sessions_dir, out_path)
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    n = pl.read_parquet(out).height
    typer.echo(f"wrote {out} ({n} sessions)")


@app.command()
def catalog_releases(releases_dir: Path, out_path: Path) -> None:
    """Build a one-row-per-release Parquet inventory from a directory of releases."""
    import polars as pl

    from htdp.catalog import CatalogError, build_release_catalog

    try:
        out = build_release_catalog(releases_dir, out_path)
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    n = pl.read_parquet(out).height
    typer.echo(f"wrote {out} ({n} releases)")


@app.command()
def catalog_query(
    catalog_path: Path,
    protocol: str | None = typer.Option(None, "--protocol"),
    qc: str | None = typer.Option(None, "--qc"),
    participant: str | None = typer.Option(None, "--participant"),
    processing_status: str | None = typer.Option(None, "--processing-status"),
    modality: str | None = typer.Option(None, "--modality"),
    start_after: float | None = typer.Option(None, "--start-after"),
    start_before: float | None = typer.Option(None, "--start-before"),
) -> None:
    """Print session_ids from a catalog matching the given filters (AND)."""
    from htdp.catalog import CatalogError, query_catalog

    try:
        ids = query_catalog(
            catalog_path,
            protocol=protocol,
            qc_status=qc,
            participant=participant,
            processing_status=processing_status,
            modality=modality,
            start_after=start_after,
            start_before=start_before,
        )
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for session_id in ids:
        typer.echo(session_id)


@app.command(name="shapesort-eval-report")
def shapesort_eval_report(
    trials: Path = typer.Option(
        ..., "--trials", help="JSONL file, one {outcome, used_fallback} object per line"
    ),
    out: Path = typer.Option(..., "--out", help="report JSON path"),
) -> None:
    """Aggregate R2 shape-sort trial logs into a success-rate + Wilson-CI report."""
    try:
        from htdp.shapesort.eval import TrialLog, aggregate
    except ImportError as exc:
        from htdp.shapesort.errors import ShapesortUnavailable

        typer.echo(f"error: {ShapesortUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    import json

    logs = []
    for line in trials.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        logs.append(TrialLog(outcome=row["outcome"], used_fallback=row["used_fallback"]))

    report = aggregate(logs)
    out.write_text(json.dumps(report, indent=2))
    typer.echo(f"n={report['n']} success_rate={report['success_rate']:.3f} ci95={report['ci95']}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    data_dir: Path = typer.Option(Path("."), "--data-dir"),
) -> None:
    """Run the read-only + job-runner dashboard server (optional extra: serve)."""
    try:
        import uvicorn

        from htdp.serve.app import create_app
    except ImportError as exc:
        typer.echo("error: install the serve extra: uv sync --extra serve", err=True)
        raise typer.Exit(1) from exc

    uvicorn.run(create_app(data_dir.resolve()), host=host, port=port)
