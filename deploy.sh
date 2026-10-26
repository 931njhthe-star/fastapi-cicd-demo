#!/usr/bin/env bash
set -euo pipefail

IMAGE_URI="${1:?Usage: deploy.sh <image-uri>}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
REGISTRY="${IMAGE_URI%%/*}"

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"

cd /opt/myapp
IMAGE_URI="$IMAGE_URI" docker compose pull app
IMAGE_URI="$IMAGE_URI" docker compose up -d app

curl --fail --silent --show-error \
  --retry 10 --retry-delay 2 --retry-connrefused \
  http://127.0.0.1:8000/health
