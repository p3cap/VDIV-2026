#!/bin/bash

echo "Mars Rover rendszer indul..."
cd MarsRover
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..

echo "Mars Rover Console indul..."
cd dashboard
npm install
npm run dev
cd ..

echo "Done."
