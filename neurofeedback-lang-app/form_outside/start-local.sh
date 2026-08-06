#!/bin/bash
# Local dev startup for liability-frontend feature work
# Run from anywhere: ~/liability/start-local.sh

set -e

ROOT="/Users/alexanderlemberger/liability"

echo "🚀 Starting liability local dev environment..."

# 1. liability-ios (port 8082) — profiles: dev,local
echo ""
echo "▶ Starting liability-ios (port 8082)..."
osascript -e "tell application \"Terminal\" to do script \"cd $ROOT/liability-ios && mvn spring-boot:run -Dspring-boot.run.profiles=dev,local\""

sleep 2

# 2. liability-application (port 8081) — profiles: dev,no-auth,local
echo "▶ Starting liability-application (port 8081)..."
osascript -e "tell application \"Terminal\" to do script \"cd $ROOT/liability-application && mvn -pl apps/liability spring-boot:run -Dspring-boot.run.profiles=dev,no-auth,local\""

sleep 2

# 3. Angular frontend
echo "▶ Starting Angular frontend..."
osascript -e "tell application \"Terminal\" to do script \"cd $ROOT/liability-frontend && npm start\""

echo ""
echo "⚠️  Don't forget to start Mockoon and enable:"
echo "   - Central Identifier  (port 18080)  → liability-ios/mockoon/CentralIdentifier.json"
echo "   - Partner             (port 8091)   → liability-application/mockoon/Partner.json"
echo ""
echo "✅ Done — check Terminal windows for startup progress"
