# AGENTS.md

## Project overview

This repository contains a Vite + React + TypeScript interface for controlling and monitoring an SO-ARM100 robot. The UI includes joint controls, kinematics/IK tools, sequence editing, telemetry, gamepad/vision overlays, and a 3D arm view.

## Development

- Install dependencies with `npm install`.
- Start the local development server with `npm run dev`.
- Run the TypeScript check with `npm run lint`.
- Create a production build with `npm run build`.
- Use Node.js and keep API keys in local environment files such as `.env.local`; never commit secrets.

## Code conventions

- Keep components in `src/components/` and shared types in `src/types.ts`.
- Put reusable robot math and transformation logic in `src/utils/`.
- Prefer small, typed React components and existing project patterns.
- Keep UI styling consistent with the existing design system in `src/index.css`.
- Avoid changing robot-control behavior without checking limits, units, and failure states.

## Validation

Before handing off changes, run `npm run lint` and, when relevant, `npm run build`. For changes to controls, kinematics, networking, or telemetry, manually exercise the affected flow in the development app.

## Git hygiene

- Make focused commits with clear messages.
- Do not commit `.env.local`, API keys, generated `dist/` output, or dependency directories.
