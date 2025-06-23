# Pikud Haoref Real-Time Alert System - Docker Management
# Usage: make <command>

.PHONY: help build up down restart logs logs-app logs-mcp clean rebuild test status

# Default target
help:
	@echo "🚀 Pikud Haoref Alert System - Docker Commands"
	@echo ""
	@echo "📋 Available commands:"
	@echo "  make build     - Build all Docker containers"
	@echo "  make up        - Start all services"
	@echo "  make down      - Stop all services"
	@echo "  make restart   - Restart all services (down + build + up)"
	@echo "  make rebuild   - Force rebuild all containers (no cache)"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  make logs      - Show logs from all services"
	@echo "  make logs-app  - Show logs from FastAPI app only"
	@echo "  make logs-mcp  - Show logs from MCP server only"
	@echo "  make status    - Show container status"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test      - Run test suite"
	@echo "  make test-alert - Create a test Hebrew missile alert"
	@echo "  make test-alert-en - Create a test English earthquake alert"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  make clean     - Stop and remove POHA containers, networks, and volumes only"
	@echo "  make clean-all - Stop and remove ALL Docker resources (use with caution)"
	@echo ""
	@echo "🌐 Access URLs:"
	@echo "  FastAPI:      http://localhost:8000"
	@echo "  Swagger UI:   http://localhost:8000/docs"
	@echo "  MCP Server:   http://localhost:8001"

# Build containers
build:
	@echo "🔨 Building Docker containers..."
	cd docker && docker-compose build

# Start services
up:
	@echo "🚀 Starting services..."
	cd docker && docker-compose up -d
	@echo "✅ Services started!"
	@echo "📱 FastAPI: http://localhost:8000"
	@echo "📱 Swagger: http://localhost:8000/docs"
	@echo "📱 MCP Server: http://localhost:8001"

# Stop services
down:
	@echo "🛑 Stopping services..."
	cd docker && docker-compose down

# Quick restart (most common during development)
restart:
	@echo "🔄 Restarting services..."
	@make down
	@make build
	@make up

# Force rebuild without cache
rebuild:
	@echo "🔨 Force rebuilding all containers..."
	cd docker && docker-compose build --no-cache
	@make up

# Show all logs
logs:
	@echo "📋 Showing logs from all services..."
	cd docker && docker-compose logs -f

# Show app logs only
logs-app:
	@echo "📋 Showing FastAPI app logs..."
	cd docker && docker-compose logs -f app

# Show MCP server logs only
logs-mcp:
	@echo "📋 Showing MCP server logs..."
	cd docker && docker-compose logs -f mcp-server

# Show container status
status:
	@echo "📊 Container Status:"
	@docker ps --filter "name=poha" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@echo "📊 Resource Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" $(shell docker ps --filter "name=poha" --format "{{.Names}}" | tr '\n' ' ')

# Run tests
test:
	@echo "🧪 Running test suite..."
	cd docker && docker-compose exec app pytest -v

# Create test alerts for quick testing
test-alert:
	@echo "🚨 Creating test Hebrew missile alert..."
	@curl -X POST "http://localhost:8000/api/test/fake-alert" \
		-H "X-API-Key: poha-test-key-2024-secure" \
		-H "Content-Type: application/json" \
		-d '{"data": ["תל אביב - מרכז העיר", "רמת גן"], "cat": "1", "language": "he"}' \
		-s | jq '.'

test-alert-en:
	@echo "🌍 Creating test English earthquake alert..."
	@curl -X POST "http://localhost:8000/api/test/fake-alert" \
		-H "X-API-Key: poha-test-key-2024-secure" \
		-H "Content-Type: application/json" \
		-d '{"data": ["Jerusalem", "Haifa"], "cat": "3", "language": "en"}' \
		-s | jq '.'

test-alert-drill:
	@echo "📢 Creating test drill alert..."
	@curl -X POST "http://localhost:8000/api/test/fake-alert" \
		-H "X-API-Key: poha-test-key-2024-secure" \
		-H "Content-Type: application/json" \
		-d '{"data": ["כל הארץ"], "cat": "101", "language": "he"}' \
		-s | jq '.'

# Comprehensive cleanup - POHA containers only
clean:
	@echo "🧹 Cleaning up POHA Docker resources..."
	cd docker && docker-compose down -v --remove-orphans
	@echo "🗑️  Removing POHA Docker images..."
	@docker images --filter "reference=docker-*" -q | xargs -r docker rmi -f 2>/dev/null || echo "No POHA images to remove"
	@echo "✅ POHA cleanup complete (only POHA containers and images removed)!"

# Full system cleanup (use with caution)
clean-all:
	@echo "⚠️  WARNING: This will remove ALL Docker resources!"
	@echo "🧹 Cleaning up ALL Docker resources..."
	cd docker && docker-compose down -v --remove-orphans
	@echo "🗑️  Removing ALL unused Docker resources..."
	docker system prune -f
	@echo "✅ Full cleanup complete!"

# Development workflow shortcuts
dev: restart logs-app
	@echo "🔄 Development mode: containers restarted, showing app logs"

# Quick app-only restart (faster for code changes)
app-restart:
	@echo "🔄 Restarting FastAPI app only..."
	cd docker && docker-compose stop app
	cd docker && docker-compose build app
	cd docker && docker-compose start app
	@echo "✅ FastAPI app restarted!"

# Quick MCP-only restart
mcp-restart:
	@echo "🔄 Restarting MCP server only..."
	cd docker && docker-compose stop mcp-server
	cd docker && docker-compose build mcp-server
	cd docker && docker-compose start mcp-server
	@echo "✅ MCP server restarted!"

# Health check
health:
	@echo "🏥 Checking service health..."
	@echo "📱 FastAPI Health:"
	@curl -s http://localhost:8000/ | jq '.' || echo "❌ FastAPI not responding"
	@echo "📱 MCP Server Health:"
	@curl -s http://localhost:8001/ | head -1 || echo "❌ MCP Server not responding"

# Show recent app errors
errors:
	@echo "🚨 Recent errors from FastAPI app:"
	@cd docker && docker-compose logs app | grep -i error | tail -10 || echo "No recent errors found"

# Interactive shell into app container
shell-app:
	@echo "🐚 Opening shell in FastAPI app container..."
	cd docker && docker-compose exec app /bin/bash

# Interactive shell into MCP container
shell-mcp:
	@echo "🐚 Opening shell in MCP server container..."
	cd docker && docker-compose exec mcp-server /bin/bash