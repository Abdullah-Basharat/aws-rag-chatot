#!/bin/bash
set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-chatbot"
VERSION_TAG="${1:-latest}"

echo "=========================================="
echo "Building RAG Chatbot Container"
echo "Region: $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"
echo "Version: $VERSION_TAG"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Are you in the project root?"
    exit 1
fi

# Authenticate Docker to ECR
echo ""
echo "Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

if [ $? -ne 0 ]; then
    echo "Error: Failed to login to ECR"
    exit 1
fi

# Create ECR repository if it doesn't exist
echo ""
echo "Checking ECR repository..."
aws ecr describe-repositories --repository-names rag-chatbot --region $AWS_REGION > /dev/null 2>&1 || \
    aws ecr create-repository --repository-name rag-chatbot --region $AWS_REGION

# Build the container
echo ""
echo "Building Docker image..."
docker build -t rag-chatbot:$VERSION_TAG .

if [ $? -ne 0 ]; then
    echo "Error: Docker build failed"
    exit 1
fi

# Tag for ECR
echo ""
echo "Tagging image for ECR..."
docker tag rag-chatbot:$VERSION_TAG $ECR_REPO:$VERSION_TAG
docker tag rag-chatbot:$VERSION_TAG $ECR_REPO:latest

# Push to ECR
echo ""
echo "Pushing to ECR..."
docker push $ECR_REPO:$VERSION_TAG
docker push $ECR_REPO:latest

if [ $? -ne 0 ]; then
    echo "Error: Failed to push to ECR"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ Build and Push Complete!"
echo "Image: $ECR_REPO:$VERSION_TAG"
echo "Image: $ECR_REPO:latest"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Deploy to App Runner: ./deploy.sh"
echo "2. Or manually create App Runner service with this image"