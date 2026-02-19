@echo off

echo Mars Rover rendszer indul...
cd MarsRover
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
deactivate
cd ..

echo Mars Rover Dashboard indul...
cd dashboard
npm install
cd ..

echo Done.
pause
