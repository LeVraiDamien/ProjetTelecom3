# Scenario B - xApps du projet, compilees dans l'arbre FlexRIC de l'image de base
# (image telecom-lab-flexric-xapps:1.0). Contexte de build = ScenarioB/.
FROM telecom-lab-flexric:1.0

COPY xapps/kpm/xapp_kpm_csv.c /flexric/examples/xApp/c/monitor/xapp_kpm_csv.c
RUN cd /flexric && printf '%s\n' \
      '' '# xapp_kpm_csv (Projet 3, Phase 7)' \
      'add_executable(xapp_kpm_csv xapp_kpm_csv.c ${CMAKE_SOURCE_DIR}/src/util/alg_ds/alg/defer.c)' \
      'target_link_libraries(xapp_kpm_csv PUBLIC e42_xapp $<TARGET_OBJECTS:e2_time_obj> -pthread -lsctp -ldl)' \
      >> examples/xApp/c/monitor/CMakeLists.txt \
    && cd build && cmake .. > /dev/null && make -j4 xapp_kpm_csv \
    && cp examples/xApp/c/monitor/xapp_kpm_csv /usr/local/bin/xapp_kpm_csv
RUN mkdir -p /data
