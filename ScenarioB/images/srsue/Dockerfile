# Scenario B - srsUE 5G SA avec radio ZeroMQ (image telecom-lab-srsue:1.0)
#
# srsUE fait partie de srsRAN 4G. Compile depuis les sources avec le pilote ZMQ,
# sans aucune radio materielle. Seule la cible `srsue` est construite.
FROM ubuntu:24.04 AS build

ARG SRSRAN4G_REPO=https://github.com/srsran/srsRAN_4G.git
ARG SRSRAN4G_TAG=release_26_10
ARG NUM_JOBS=4

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates pkg-config \
        libfftw3-dev libmbedtls-dev libboost-program-options-dev libconfig++-dev \
        libsctp-dev libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 -b ${SRSRAN4G_TAG} ${SRSRAN4G_REPO} /srsran

RUN cd /srsran && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF \
        -DENABLE_BLADERF=OFF -DENABLE_SOAPYSDR=OFF -DENABLE_SKIQ=OFF -DENABLE_GUI=OFF \
        -DENABLE_HARDSIM=OFF -DENABLE_SRSENB=OFF -DENABLE_SRSEPC=OFF \
        -DENABLE_WERROR=OFF .. \
    && make -j${NUM_JOBS} srsue \
    && cp srsue/src/srsue /usr/local/bin/srsue \
    && mkdir -p /out/lib && find . -name "*.so*" -exec cp -a {} /out/lib/ \;

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfftw3-single3 libmbedtls14t64 libmbedcrypto7t64 libmbedx509-1t64 \
        libboost-program-options1.83.0 libconfig++9v5 libsctp1 libzmq5 \
        iproute2 iputils-ping iperf3 netcat-openbsd tcpdump procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/srsue /usr/local/bin/srsue
COPY --from=build /out/lib/ /usr/local/lib/
COPY --from=build /srsran/srsue/ue.conf.example /usr/local/share/srsue/ue.conf.example
RUN ldconfig && ldd /usr/local/bin/srsue | (! grep "not found")
CMD ["srsue", "/config/ue_zmq.conf"]
