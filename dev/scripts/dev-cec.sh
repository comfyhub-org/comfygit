#!/bin/bash
# dev/dev-cec.sh
# Development script for testing CEC in containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Export UID/GID for docker-compose
export USER_UID=$(id -u)
export USER_GID=$(id -g)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  setup       Set up test environment directories"
    echo "  build       Build the CEC development container"
    echo "  shell       Enter the CEC dev container shell"
    echo "  test        Run CEC tests in container"
    echo "  scan        Scan a test ComfyUI installation"
    echo "  recreate    Recreate from a manifest file"
    echo "  clean       Clean up containers and volumes"
    echo ""
    echo "Examples:"
    echo "  $0 setup                                    # Set up test directories"
    echo "  $0 build                                    # Build container"
    echo "  $0 shell                                    # Enter dev shell"
    echo "  $0 scan /test-comfyui/default               # Scan test installation"
    echo "  $0 recreate /manifests/example-manifest.json /env/environments/recreated"
}

# Ensure docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}docker-compose or docker compose is required but not installed.${NC}"
    exit 1
fi

# Use docker compose v2 if available, otherwise fall back to docker-compose
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

cd "$SCRIPT_DIR"

case "$1" in
    setup)
        echo -e "${GREEN}Setting up test environment...${NC}"
        if [ -f "./scripts/setup-test-environments.sh" ]; then
            bash ./scripts/setup-test-environments.sh
        else
            # Create the setup script if it doesn't exist
            mkdir -p scripts
            cat > ./scripts/setup-test-environments.sh << 'SETUP_SCRIPT'
#!/bin/bash
# Sets up the test environment directory structure for CEC testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_DIR="$(dirname "$SCRIPT_DIR")"
TEST_ENV_DIR="$DEV_DIR/test-environments"

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Setting up test environment structure...${NC}"

# Create main directories
mkdir -p "$TEST_ENV_DIR/env/uv_cache"
mkdir -p "$TEST_ENV_DIR/env/uv/python"
mkdir -p "$TEST_ENV_DIR/env/environments"
mkdir -p "$TEST_ENV_DIR/env/comfygit_cache/custom_nodes/store"
mkdir -p "$TEST_ENV_DIR/manifests"
mkdir -p "$TEST_ENV_DIR/test-comfyui/default/ComfyUI/custom_nodes"

# Create cache files
echo '{}' > "$TEST_ENV_DIR/env/comfygit_cache/github_cache.json"
echo '{}' > "$TEST_ENV_DIR/env/comfygit_cache/registry_cache.json"
echo '{"nodes": {}}' > "$TEST_ENV_DIR/env/comfygit_cache/custom_nodes/index.json"

echo -e "${GREEN}Test environment structure created successfully!${NC}"
SETUP_SCRIPT
            chmod +x ./scripts/setup-test-environments.sh
            bash ./scripts/setup-test-environments.sh
        fi
        ;;
    
    build)
        echo -e "${GREEN}Building CEC development container...${NC}"
        $DOCKER_COMPOSE -f ../docker-compose.yml build cec-dev
        ;;
    
    shell)
        echo -e "${GREEN}Starting CEC development shell...${NC}"
        echo -e "${BLUE}Container paths:${NC}"
        echo "  /workspace/cec  - CEC source code (live mount)"
        echo "  /env            - Environment storage"
        echo "    manifests/      - Manifest files"
        echo "    environments/   - Test ComfyUI installations"
        echo ""
        $DOCKER_COMPOSE -f ../docker-compose.yml run --rm --service-ports cec-dev
        ;;
    
    test)
        echo -e "${GREEN}Running CEC tests in container...${NC}"
        $DOCKER_COMPOSE -f ../docker-compose.yml run --rm cec-dev \
            bash -c "cd /workspace/cec && uv sync && uv run pytest tests/ -v"
        ;;
    
    scan)
        TARGET="${2:-/test-comfyui/default}"
        OUTPUT="${3:-/manifests/scanned-$(date +%Y%m%d-%H%M%S).json}"
        
        echo -e "${GREEN}Scanning ComfyUI installation...${NC}"
        echo -e "  Source: $TARGET"
        echo -e "  Output: $OUTPUT"
        
        $DOCKER_COMPOSE -f ../docker-compose.yml run --rm cec-dev \
            bash -c "cd /workspace/cec && uv sync && uv run python -m comfyui_detector scan --path '$TARGET' --output '$OUTPUT'"
        ;;
    
    recreate)
        MANIFEST="${2:-/manifests/example-manifest.json}"
        TARGET="${3:-/env/environments/recreated-$(date +%Y%m%d-%H%M%S)}"
        
        echo -e "${GREEN}Recreating environment...${NC}"
        echo -e "  Manifest: $MANIFEST"
        echo -e "  Target: $TARGET"
        
        $DOCKER_COMPOSE -f ../docker-compose.yml run --rm cec-dev \
            bash -c "cd /workspace/cec && uv sync && uv run python -m comfyui_detector recreate --manifest '$MANIFEST' --target '$TARGET' --verbose"
        ;;
    
    clean)
        echo -e "${YELLOW}Cleaning up development containers...${NC}"
        $DOCKER_COMPOSE -f ../docker-compose.yml down -v
        echo -e "${YELLOW}Remove test environments? (y/N)${NC}"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            rm -rf ./test-environments
            echo -e "${GREEN}Test environments removed.${NC}"
        fi
        ;;
    
    *)
        print_usage
        exit 1
        ;;
esac