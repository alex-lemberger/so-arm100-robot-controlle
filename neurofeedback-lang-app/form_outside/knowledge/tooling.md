# Tooling

## Local Development Setup

### Angular (frontend)

```bash
cd liability-frontend
npm install --include=optional      # Initial setup
npm ci                              # Clean install when node_modules is stale/corrupted after merge
npm start                           # Serve liability-app (local)
npm run start:property              # Serve property-app
npm run start:cyber                 # Serve cyber-app
npm run start:generic:no-auth       # Serve generic-app (no auth)
npx nx test <project>               # Unit tests (Jest)
npx nx lint <project>               # ESLint
npm run generate:<domain>           # Regenerate OpenAPI client (e.g. generate:openapi-cost-data)
```

### Spring Boot (backend)

```bash
cd liability-application
./mvnw clean install            # Full build
./mvnw spotless:apply           # Format code
# Local: use Spring profile "local", "noauth" to disable OAuth2, "partnermock" for mock partners
```

## Frontend Mocking Setup

- Local mocking via Mockoon (see `liability-application/mockoon/`)
- `--no-auth` profile disables OAuth2 auth in Angular and in backend services
- `npm run start:no-auth` is equivalent to `npm run start` with `NO_AUTH=true` env var

## E2E Tests

```bash
STAGE=local IS_HEADLESS=false npx playwright test
```

Tests use:
- Page Object Model pattern with reusable logic in `teststeps/`
- Test data in `testdata/`
- Custom helpers instead of Playwright's `input.fill()` for Angular compatibility

### Tags & Organization
- Tests tagged with `@property`, `@liability`, or `@shared` as appropriate.
- Organized into: `tests/e2e/` (happy paths), `tests/regression/`, `tests/sanity/`, `tests/smoke/`, `tests/icp/`

## Azure DevOps API Access

The UWWB project uses Azure DevOps for CI/CD with several important considerations:
1. The pipeline configuration files are located in `liability-application/pipelines/`
2. For accessing Azure DevOps APIs directly, we use the `az` CLI tool.
3. Authentication is done via service principal, which requires a token for API access.

### Common Commands
```bash
# List projects
az devops project list

# Get build definition details (for pipeline setup)
az pipelines show --id <pipeline-id>

# Get build logs
az pipelines build log show --build-id <build-id>
```

## grep Limitation

**The project's grep configuration contains a blindspot for finding Angular component selectors.**

For example, running:
```bash
grep -r "selector.*my-component" .
```
will not find the selector that lives in a component like:
```ts
@Component({
  selector: 'app-my-component',
  ...
})
export class MyComponent {}
```

This is due to the current grep setup. When searching for component selectors or Angular directives, we should use a more targeted approach.