#!/bin/bash
set -e

echo "=========================================="
echo "Starting RAG Chatbot Services"
echo "=========================================="

# Load environment variables if .env exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Start FastAPI backend in the background
echo "Starting FastAPI backend on port ${BACKEND_PORT:-8000}..."
uv run uvicorn Backend.main:app \
    --host ${BACKEND_HOST:-0.0.0.0} \
    --port ${BACKEND_PORT:-8000} \
    --log-level ${LOG_LEVEL:-info} &

BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
sleep 5

# Check if backend is responding
until curl -s http://localhost:${BACKEND_PORT:-8000}/docs > /dev/null 2>&1; do
    echo "Waiting for backend to respond..."
    sleep 2
done
echo "✓ Backend is ready!"

# Start Streamlit frontend in the background
echo "Starting Streamlit frontend on port ${FRONTEND_PORT:-8501}..."
uv run streamlit run Frontend/streamlit/pages/main.py \
    --server.port=${FRONTEND_PORT:-8501} \
    --server.address=${FRONTEND_HOST:-0.0.0.0} \
    --server.headless=true \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false &

FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

echo "=========================================="
echo "✓ All services started successfully!"
echo "Backend:  http://localhost:${BACKEND_PORT:-8000}"
echo "Frontend: http://localhost:${FRONTEND_PORT:-8501}"
echo "=========================================="

# Function to handle shutdown gracefully
shutdown() {
    echo ""
    echo "=========================================="
    echo "Shutting down services..."
    echo "=========================================="
    
    echo "Stopping frontend (PID: $FRONTEND_PID)..."
    kill -TERM $FRONTEND_PID 2>/dev/null || true
    
    echo "Stopping backend (PID: $BACKEND_PID)..."
    kill -TERM $BACKEND_PID 2>/dev/null || true
    
    # Wait for processes to terminate
    wait $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    
    echo "✓ Services stopped"
    exit 0
}

# Trap termination signals
trap shutdown SIGTERM SIGINT SIGQUIT

# Keep script running and wait for both processes
wait $BACKEND_PID $FRONTEND_PID
```