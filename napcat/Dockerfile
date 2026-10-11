# syntax=docker/dockerfile:1

# NapCat (QQ + OneBot v11) with a start wrapper that writes the reverse WebSocket
# connection to NoneBot, token included, from the environment on every start.
#
# The deploy tags this image with napcat/'s git tree hash and copies it to Huawei SWR
# only when that tag is new: a NapCat update is a slow (30–90 minute) upload, and it
# restarts QQ, so it happens only when this folder changes. Dependabot proposes
# updates monthly; read NapCat's release notes before merging one.
FROM mlikiowa/napcat-docker:v4.18.37
COPY --chmod=755 start.sh /usr/local/bin/chatbot-napcat-start
ENTRYPOINT ["chatbot-napcat-start"]
