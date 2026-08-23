FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client libssh-dev gcc ca-certificates \
    && rm -rf /var/lib/apt/lists/*


RUN pip install --no-cache-dir \
        ansible-core==2.17.* \
        ansible-pylibssh \
        yamllint \
        ansible-lint \
        pyyaml \
        jinja2 \
        requests

RUN printf 'Host *\n\
    KexAlgorithms +diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1,diffie-hellman-group1-sha1\n\
    HostKeyAlgorithms +ssh-rsa\n\
    PubkeyAcceptedAlgorithms +ssh-rsa\n\
    Ciphers +aes128-cbc,aes192-cbc,aes256-cbc,3des-cbc\n\
    MACs +hmac-sha1\n' >> /etc/ssh/ssh_config

RUN ansible-galaxy collection install cisco.ios cisco.asa ansible.netcommon

RUN ansible-galaxy collection install cisco.ios cisco.asa ansible.netcommon ansible.posix

ENV ANSIBLE_HOST_KEY_CHECKING=False \
    PYTHONUNBUFFERED=1

WORKDIR /work
