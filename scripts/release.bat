@REM release package

python -m pip install --upgrade pip setuptools build wheel twine
python -m build
python -m twine check dist/*
python -m twine upload --verbose --repository pypi dist/*
@REM after this manually enter PYPI token

rmdir /s /q .\dist\
rmdir /s /q .\build\
rmdir /s /q .\src\robotframework_events.egg-info\
