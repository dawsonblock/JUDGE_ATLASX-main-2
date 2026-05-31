#!/bin/bash

# Source nvm and pyenv, set specific versions, then run environment check scripts

echo "Sourcing nvm and pyenv..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# Add pyenv to PATH and initialize
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
  eval "$(pyenv init -)"
fi

echo "Setting Node version to 22.22.3..."
nvm use 22.22.3 || nvm install 22.22.3

echo "Setting Python version to 3.11.9..."
pyenv shell 3.11.9 || pyenv install 3.11.9

echo "Current versions:"
echo "Node: $(node --version)"
echo "Python: $(python --version)"

echo "Running check_local_dev_environment.py..."
./scripts/check_local_dev_environment.py

echo "Running check_toolchain_versions.py --root ."
./scripts/check_toolchain_versions.py --root .

echo "Environment checks completed."