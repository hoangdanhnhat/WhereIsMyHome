#!/bin/sh
set -e

# Ensure the data directory exists and is writable by the tracker user.
# Bind-mounted volumes from the host are typically owned by root,
# so we fix ownership here (entrypoint runs as root).
mkdir -p /app/data
chown tracker:tracker /app/data

# Drop privileges and exec the main command as the non-root user.
exec gosu tracker "$@"
