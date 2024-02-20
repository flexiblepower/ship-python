
pushd .
cd /D "%~dp0"
pip-compile --output-file=..\..\requirements.txt ..\..\pyproject.toml
pip-compile --extra=dev --output-file=..\..\dev-requirements.txt ..\..\pyproject.toml
popd