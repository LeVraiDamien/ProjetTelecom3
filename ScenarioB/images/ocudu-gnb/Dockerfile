# Scenario B - gNB OCUDU avec radio ZeroMQ et agent E2 (image telecom-lab-ocudu-gnb:1.0)
#
# OCUDU = suite du projet srsRAN Project (Linux Foundation). Compile depuis les
# sources : pas d'image fournie par le cours. Seule la cible `gnb` est construite.
FROM ubuntu:24.04 AS build

ARG OCUDU_REPO=https://github.com/ocudu/ocudu.git
ARG OCUDU_TAG=release_26_10
ARG NUM_JOBS=4

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake make gcc g++ pkg-config git ca-certificates \
        libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 -b ${OCUDU_TAG} ${OCUDU_REPO} /ocudu

# ENABLE_EXPORT=ON est requis pour le pilote radio ZeroMQ ; pas d'UHD ni de DPDK
# (aucune radio materielle). -march par defaut = machine de build : l'image n'est
# pas portable vers un CPU plus ancien.
RUN cd /ocudu && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON \
        -DENABLE_UHD=OFF -DENABLE_DPDK=OFF -DENABLE_SIDEKIQ=OFF -DENABLE_DIFI=OFF \
        -DENABLE_MKL=OFF -DENABLE_FFTZ=OFF -DENABLE_ARMPL=OFF \
        -DBUILD_TESTING=OFF -DENABLE_WERROR=OFF .. \
    && make -j${NUM_JOBS} gnb \
    && cp apps/gnb/gnb /usr/local/bin/gnb

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfftw3-single3 libmbedtls14t64 libmbedcrypto7t64 libmbedx509-1t64 \
        libsctp1 libyaml-cpp0.8 libzmq5 \
        iproute2 iputils-ping netcat-openbsd tcpdump procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/gnb /usr/local/bin/gnb
COPY --from=build /ocudu/configs /usr/local/share/ocudu/configs
# Le sujet appelle le binaire `ocudu-gnb`.
RUN ln -s /usr/local/bin/gnb /usr/local/bin/ocudu-gnb && ldd /usr/local/bin/gnb | (! grep "not found")
CMD ["ocudu-gnb", "-c", "/config/gnb_zmq.yaml"]
