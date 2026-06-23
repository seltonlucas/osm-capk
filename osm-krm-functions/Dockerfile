#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

FROM alpine:3.20

# Ensure compatibility with any script
RUN ln -s /usr/local/bin/bash /bin/bash

# Install packages available at Alpine repos
RUN apk add --no-cache \
    age \
    bash \
    curl \
    envsubst \
    git \
    kubectl \
    kustomize \
    rsync \
    sops \
    yq

# Install other dependencies
RUN (curl -s https://fluxcd.io/install.sh | bash) && \
    curl https://github.com/GoogleContainerTools/kpt/releases/download/v1.0.0-beta.44/kpt_linux_amd64 -Lo kpt && \
    chmod +x kpt && \
    mv kpt /usr/local/bin/

# Create new user and log in as it
RUN addgroup -g 10000 -S app && \
    adduser -h /app -s /bin/false -D -u 10000 -S -G app app
USER app
WORKDIR /app

# Add helper scripts
COPY --chown=app:app scripts/docker-entrypoint.sh /app/scripts/entrypoint.sh
COPY --chown=app:app scripts/library /app/scripts/library

ENTRYPOINT [ "/app/scripts/entrypoint.sh" ]

CMD ["bash"]
