@echo off

echo Mars Rover rendszer indul...
cd MarsRover
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
cd ..

cd dashboard
echo Installing dashboard dependencies...
npm install
cd ..

echo Setup complete!