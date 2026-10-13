#!/bin/bash
# Script to run tests with various options

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Running Scholarmap Tests ===${NC}\n"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Install it with: pip install pytest pytest-cov"
    exit 1
fi

# Parse command line arguments
TEST_TYPE=${1:-all}

case $TEST_TYPE in
    unit)
        echo -e "${YELLOW}Running unit tests only...${NC}"
        python3 -m pytest src/tests -m "not integration" -v
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests (requires API key)...${NC}"
        python3 -m pytest src/tests -m integration -v
        ;;
    coverage)
        echo -e "${YELLOW}Running tests with coverage report...${NC}"
        python3 -m pytest src/tests --cov=src --cov-report=html --cov-report=term-missing
        echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    fast)
        echo -e "${YELLOW}Running fast tests only...${NC}"
        python3 -m pytest src/tests -m "not slow and not integration" -v
        ;;
    all|*)
        echo -e "${YELLOW}Running all tests...${NC}"
        python3 -m pytest src/tests -v
        ;;
esac

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
else
    echo -e "\n${RED}✗ Some tests failed${NC}"
fi

exit $EXIT_CODE
