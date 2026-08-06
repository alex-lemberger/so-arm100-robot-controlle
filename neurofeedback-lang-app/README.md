# NeurofeedbackLangApp

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 19.0.6.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Karma](https://karma-runner.github.io) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Database Recommendations

### Current State
The app currently uses Firebase/Firestore for data storage, handling user sessions, brain metrics, and learning progress.

### Recommended Alternatives

#### **PostgreSQL** (Recommended)
**Best for:** Real-time brain metrics, complex analytics, GDPR compliance
- **Time-series support:** Native timestamptz and window functions for brain metrics
- **JSON flexibility:** JSONB for varying exercise data structures  
- **Real-time:** Built-in LISTEN/NOTIFY for live neurofeedback
- **Analytics:** Advanced aggregations for learning progress tracking
- **Hosting:** Supabase, Railway, or Neon for managed solutions

#### **InfluxDB + PostgreSQL** (Optimal)
**Best for:** High-frequency brain data with user management
- **InfluxDB:** Purpose-built for time-series brain metrics (focus/calm over time)
- **PostgreSQL:** User profiles, sessions, exercises, progress
- **Benefits:** Automatic downsampling, retention policies, fast queries
- **Hosting:** InfluxDB Cloud + Supabase

#### **MongoDB**
**Best for:** Rapid development with varied exercise formats
- **Document model:** Natural fit for exercises with different structures
- **Time-series collections:** Built-in optimization for brain metrics
- **Aggregation pipeline:** Rich analytics capabilities
- **Hosting:** MongoDB Atlas

#### Why Firebase might not fit:
- Limited complex queries for learning analytics
- Expensive for high-frequency brain data storage
- Real-time pricing scales poorly with continuous metrics
- Less flexibility for time-series optimizations

**Recommendation:** Start with **PostgreSQL via Supabase** - it gives you real-time capabilities, strong analytics, and easier migration path from Firebase while handling both structured user data and time-series brain metrics effectively.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
