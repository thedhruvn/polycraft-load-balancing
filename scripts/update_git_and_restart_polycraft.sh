#!/bin/bash

# $1 - the git directory to check
# $2 - the target directory to move the mod
# $3 - the world name to run with polycraft

pull_and_copy() {
  # Check if $1 is a git repository
  if [[ -d $1 ]]; then
    cd $1; echo "Checking if $PWD is a git directory";
    git status --porcelain || return 1; # A fatal error if $PWD is not a git repo
    if [[ git pull | grep -q "Already up to date" ]]; then
      echo "repo is up to date";
      return 1
    fi
    if [[ -d $1/scripts/ ]] && [[ -d $2/mods/ ]]; then
      rm -f $2/mods/*.jar
      cp $1/scripts/*.jar $2/mods/
      return 0
    else
      echo "Error! scripts doesn't exist or $2 is not valid";

    fi
  else
    echo "Error: input is not a directory!";
  fi
  return 1;

}



temp1 = [ $(git rev-parse HEAD) = $(git ls-remote $(git rev-parse --abbrev-ref @{u} | \
sed 's/\// /g') | cut -f1) ] && echo up to date || pull_and_copy $1 $2;

# Check if the previous result was 0 (successful pull) or not
# Confirm that there is a 3rd input argument to run polycraft no pp.
if [[ temp1 -eq 0 ]] && [[ $# -gt 2 ]]; then
  bash run_polycraft_no_pp.sh $3
fi
