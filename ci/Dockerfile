FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client libssh-dev gcc ca-certificates \
        iputils-ping iproute2 net-tools dnsutils traceroute mtr-tiny \
        tcpdump netcat-openbsd telnet socat \
        curl wget jq \
        vim less tree file \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*


RUN pip install --no-cache-dir \
        ansible-core==2.17.* \
        ansible-pylibssh \
        "pyats[full]" \
        yamllint ansible-lint \
        pyyaml jinja2 requests \
        httpie \
        netmiko napalm

RUN pip install --no-cache-dir "pyats[full]"

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
