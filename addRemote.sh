#!/bin/bash
projectName=${1}
echo "projectName: ${projectName}"
if [[ ${projectName} == "" ]]; then
    echo provided empty project name
    exit 1
fi
git remote add  gitlab  "https://gitlab.dev.io/home-lab/${projectName}"
git remote add  origin  "https://github.com/greenCircuit/${projectName}"

git remote set-url --add --push origin https://gitlab.dev.io/home-lab/${projectName}
git remote set-url --add --push origin https://github.com/greenCircuit/${projectName}
git push --set-upstream origin main
# git remote -v

# git remote remove ${origin}