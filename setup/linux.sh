#!/bin/bash

echo "Mars Rover rendszer indul..."
cd MarsRover
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

cd dashboard
echo "Installing dashboard dependencies..."
npm install
cd ..

echo "Setup complete!"
echo ""
echo "To start development:"
echo "  - For dashboard: cd dashboard && npm run dev"
echo "  - For backend: cd MarsRover && source venv/bin/activate && python Main.py"
