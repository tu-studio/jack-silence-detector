# jack-silence-detector

## Installation
``` bash
python -m venv venv
source venv/bin/activate
pip install .
jack-silence-detector -h
```

# Releasing

Releases are published automatically when a tag is pushed to GitHub.

``` bash

# Set next version number
export RELEASE=x.x.x

git tag -a $RELEASE -m "Version $RELEASE"

# Push
git push --tags
```