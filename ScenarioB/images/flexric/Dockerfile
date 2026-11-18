# Scenario B - FlexRIC Near-RT RIC + SDK xApp (image telecom-lab-flexric:1.0)
#
# Aucune image n'etant fournie par le cours, on compile depuis les sources.
# Branche br-flexric (variante BubbleRAN) : c'est elle qui contient l'exemple
# xapp_oran_moni et les fichiers conf (ric.conf, xapp_oran_sm.conf) cites par le sujet.
# E2AP v3 + KPM v3.00 pour correspondre a l'agent E2 d'OCUDU (ASN.1 E2AP v03.00).
FROM ubuntu:24.04

ARG FLEXRIC_REPO=https://gitlab.eurecom.fr/mosaic5g/flexric.git
ARG FLEXRIC_COMMIT=736508123fe4b5dc3db83fb5baf5f0a8e9b04fe8
ARG NUM_JOBS=4

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc-12 g++-12 cmake git ca-certificates pkg-config swig \
        libsctp-dev libconfig-dev libconfig++-dev libpcre2-dev python3 python3-dev \
        iproute2 iputils-ping netcat-openbsd tcpdump procps \
    && rm -rf /var/lib/apt/lists/*

RUN git clone ${FLEXRIC_REPO} /flexric && cd /flexric && git checkout ${FLEXRIC_COMMIT}

# Le README de FlexRIC deconseille gcc-11 ; gcc-12 est la version la plus proche
# de celle utilisee par ses auteurs (evite les nouveaux avertissements de gcc-13).
RUN cd /flexric && mkdir build && cd build \
    && CC=gcc-12 CXX=g++-12 cmake -DCMAKE_BUILD_TYPE=Release \
        -DE2AP_VERSION=E2AP_V3 -DKPM_VERSION=KPM_V3_00 \
        -DXAPP_DB=NONE_XAPP -DUNIT_TEST=OFF .. \
    && make -j${NUM_JOBS} && make install && ldconfig

WORKDIR /flexric/build
# Le RIC lit /config/ric.conf (monte depuis ScenarioB/config).
CMD ["/flexric/build/examples/ric/nearRT-RIC", "-c", "/config/ric.conf"]
