FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    tmate \
    nano \
    openssh-client \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSf https://sshx.io/get | sh
RUN ssh-keygen -q -t rsa -N '' -f /root/.ssh/id_rsa

RUN printf '#!/bin/sh\n\
tmate -S /tmp/tmate.sock new-session -d\n\
tmate -S /tmp/tmate.sock wait tmate-ready\n\
echo "--- TMATE SSH ---"\n\
tmate -S /tmp/tmate.sock display -p "#{tmate_ssh}"\n\
echo "--- SSHX URL ---"\n\
sshx & \n\
sleep infinity' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]