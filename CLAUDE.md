# Project workflow

- Work on the `dev` branch by default, not `main`.
- Run Git pushes in the foreground. In this environment, background pushes failed with an authentication error while the same command succeeded in the foreground; do not assume the account needs reauthentication based on that error alone.
- GitHub account: `g-baskin`. A successful foreground push used the existing GitHub CLI login without changing Git configuration:

  ```sh
  git -c credential.helper= -c credential.https://github.com.helper= -c 'credential.https://github.com.helper=!/usr/local/bin/gh auth git-credential' push
  ```
