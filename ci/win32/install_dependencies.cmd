
pushd .
cd /D "%~dp0"
cd ..\..\
pip-sync .\dev-requirements.txt .\requirements.txt
popd